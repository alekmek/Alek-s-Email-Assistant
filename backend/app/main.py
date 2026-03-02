import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Keep service logs readable in normal operation.
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger.remove()
logger.add(sys.stderr, level="INFO")

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.transports.network.websocket_server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

from app.config import get_settings
from app.pipecat_bot.prompts.system_prompt import SYSTEM_PROMPT
from app.pipecat_bot.tools import get_all_tools, register_all_tools
from app.services.database import init_db, ConversationService
from app.services.profile_service import ProfileService
from app.services.settings_service import SettingsService


# Store active connections
active_connections: dict[str, WebSocket] = {}

# Conversation flow timeouts (seconds)
NO_ACTIVITY_AFTER_EOS_TIMEOUT = 4
TURN_RECOVERY_TIMEOUT = 75
FUNCTION_CALL_TIMEOUT = 120
REQUIRED_RUNTIME_CREDENTIALS = (
    "anthropic_api_key",
    "nylas_api_key",
    "nylas_grant_id",
    "deepgram_api_key",
    "cartesia_api_key",
)
REQUIRED_RUNTIME_MODEL_SETTING = "anthropic_model"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for voice email assistant."""
    logger.info("Starting Voice Email Assistant")
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Voice Email Assistant")


app = FastAPI(
    title="Voice Email Assistant",
    description="Voice-driven email assistant using Pipecat and Nylas",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_runtime_system_prompt() -> str:
    """Inject current time context so relative date filters stay accurate."""
    now_ts = int(time.time())
    now_iso_utc = datetime.now(timezone.utc).isoformat()
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Runtime Time Reference:\n"
        f"Current unix time: {now_ts}\n"
        f"Current UTC datetime: {now_iso_utc}\n"
        f"For relative time requests such as 'last 24 hours', calculate timestamps from this runtime value."
    )


async def get_runtime_credentials() -> dict:
    """Resolve runtime credentials and fail fast if required values are missing."""
    credentials = await ProfileService.resolve_credentials()
    missing = [key for key in REQUIRED_RUNTIME_CREDENTIALS if not credentials.get(key)]
    if missing:
        missing_pretty = ", ".join(missing)
        raise RuntimeError(
            f"Missing required credentials: {missing_pretty}. "
            "Open Settings and add provider credentials."
        )
    if not settings.anthropic_model:
        raise RuntimeError(
            f"Missing required model setting: {REQUIRED_RUNTIME_MODEL_SETTING}. "
            "Set it in backend/.env."
        )
    return credentials


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "voice-email-assistant"}


@app.get("/health")
async def health():
    """Detailed health check."""
    resolved_credentials = await ProfileService.resolve_credentials()
    return {
        "status": "healthy",
        "services": {
            "nylas": "configured" if resolved_credentials.get("nylas_api_key") else "not_configured",
            "anthropic": "configured" if resolved_credentials.get("anthropic_api_key") else "not_configured",
            "deepgram": "configured" if resolved_credentials.get("deepgram_api_key") else "not_configured",
            "cartesia": "configured" if resolved_credentials.get("cartesia_api_key") else "not_configured",
        },
    }


# Conversation API endpoints
@app.get("/api/conversations")
async def list_conversations(limit: int = 50, offset: int = 0):
    """List all conversations."""
    conversations = await ConversationService.list_conversations(limit=limit, offset=offset)
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in conversations
    ]


@app.post("/api/conversations")
async def create_conversation(title: str = None):
    """Create a new conversation."""
    conversation = await ConversationService.create_conversation(title=title)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a conversation by ID."""
    conversation = await ConversationService.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    """Get all messages for a conversation."""
    messages = await ConversationService.get_messages(conversation_id)
    return [
        {
            "id": m.id,
            "conversation_id": m.conversation_id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@app.post("/api/conversations/{conversation_id}/messages")
async def add_message(conversation_id: str, role: str, content: str):
    """Add a message to a conversation."""
    message = await ConversationService.add_message(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    if not message:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    deleted = await ConversationService.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


# Settings API endpoints
@app.get("/api/settings")
async def get_settings_endpoint():
    """Get user safety settings."""
    settings = await SettingsService.get_settings()
    return SettingsService.settings_to_dict(settings)


@app.put("/api/settings")
async def update_settings_endpoint(
    allow_send_emails: bool = None,
    require_confirmation_for_send: bool = None,
    allow_read_attachments: bool = None,
    allow_read_email_body: bool = None,
    allow_mark_as_read: bool = None,
    allow_delete_emails: bool = None,
    allow_archive_emails: bool = None,
    excluded_senders: str = None,  # JSON array string
    excluded_folders: str = None,  # JSON array string
    excluded_subjects: str = None,  # JSON array string
    hide_sensitive_content: bool = None,
    max_emails_per_search: int = None,
):
    """Update user safety settings."""
    import json as json_module

    kwargs = {}
    if allow_send_emails is not None:
        kwargs["allow_send_emails"] = allow_send_emails
    if require_confirmation_for_send is not None:
        kwargs["require_confirmation_for_send"] = require_confirmation_for_send
    if allow_read_attachments is not None:
        kwargs["allow_read_attachments"] = allow_read_attachments
    if allow_read_email_body is not None:
        kwargs["allow_read_email_body"] = allow_read_email_body
    if allow_mark_as_read is not None:
        kwargs["allow_mark_as_read"] = allow_mark_as_read
    if allow_delete_emails is not None:
        kwargs["allow_delete_emails"] = allow_delete_emails
    if allow_archive_emails is not None:
        kwargs["allow_archive_emails"] = allow_archive_emails
    if excluded_senders is not None:
        kwargs["excluded_senders"] = json_module.loads(excluded_senders)
    if excluded_folders is not None:
        kwargs["excluded_folders"] = json_module.loads(excluded_folders)
    if excluded_subjects is not None:
        kwargs["excluded_subjects"] = json_module.loads(excluded_subjects)
    if hide_sensitive_content is not None:
        kwargs["hide_sensitive_content"] = hide_sensitive_content
    if max_emails_per_search is not None:
        kwargs["max_emails_per_search"] = str(max_emails_per_search)

    settings = await SettingsService.update_settings(**kwargs)
    return SettingsService.settings_to_dict(settings)


@app.get("/api/profile")
async def get_profile_endpoint():
    """Get user profile metadata and credential status."""
    profile = await ProfileService.get_profile()
    return await ProfileService.profile_to_dict(profile)


@app.put("/api/profile")
async def update_profile_endpoint(display_name: str = None):
    """Update user profile metadata."""
    profile = await ProfileService.update_profile(display_name=display_name)
    return await ProfileService.profile_to_dict(profile)


@app.put("/api/profile/credentials")
async def update_profile_credentials_endpoint(
    anthropic_api_key: str = None,
    nylas_api_key: str = None,
    nylas_client_id: str = None,
    nylas_client_secret: str = None,
    nylas_grant_id: str = None,
    deepgram_api_key: str = None,
    cartesia_api_key: str = None,
):
    """Update provider credentials for the active user profile."""
    profile = await ProfileService.update_profile(
        anthropic_api_key=anthropic_api_key,
        nylas_api_key=nylas_api_key,
        nylas_client_id=nylas_client_id,
        nylas_client_secret=nylas_client_secret,
        nylas_grant_id=nylas_grant_id,
        deepgram_api_key=deepgram_api_key,
        cartesia_api_key=cartesia_api_key,
    )
    return await ProfileService.profile_to_dict(profile)


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for voice interaction.

    This endpoint handles the real-time voice communication between
    the browser and the Pipecat pipeline.
    """
    await websocket.accept()
    client_id = str(id(websocket))
    logger.info(f"WebSocket connection established: {client_id}")

    try:
        runtime_credentials = await get_runtime_credentials()

        # Create transport for this WebSocket connection
        transport = WebsocketServerTransport(
            params=WebsocketServerParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                vad_audio_passthrough=True,
            )
        )

        # Initialize services
        stt = DeepgramSTTService(
            api_key=runtime_credentials["deepgram_api_key"],
        )

        llm = AnthropicLLMService(
            api_key=runtime_credentials["anthropic_api_key"],
            model=settings.anthropic_model,
            function_call_timeout_secs=FUNCTION_CALL_TIMEOUT,
        )

        tts = CartesiaTTSService(
            api_key=runtime_credentials["cartesia_api_key"],
            voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",
        )

        # Register tools
        register_all_tools(llm)

        # Set up context
        tools = get_all_tools()
        context = OpenAILLMContext(
            messages=[{"role": "system", "content": build_runtime_system_prompt()}],
            tools=tools,
        )
        context_aggregator = llm.create_context_aggregator(context)

        # Create pipeline
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                context_aggregator.user(),
                llm,
                ParallelPipeline(
                    [tts, transport.output()],
                    [context_aggregator.assistant()],
                ),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
            ),
            idle_timeout_secs=None,
            cancel_on_idle_timeout=False,
        )

        # Run the pipeline
        runner = PipelineRunner()
        await runner.run(task)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {client_id}")
    except RuntimeError as e:
        logger.error(f"WebSocket runtime error: {e}")
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
            await websocket.close(code=1011)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if client_id in active_connections:
            del active_connections[client_id]


@app.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for audio streaming with Pipecat pipeline.

    Receives raw Int16 PCM audio at 16kHz and processes through
    STT -> LLM -> TTS pipeline, sending audio responses back.
    """
    logger.info("WebSocket connection attempt received")

    try:
        await websocket.accept()
        logger.info("WebSocket accepted")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket: {e}")
        return

    client_id = str(id(websocket))
    active_connections[client_id] = websocket
    logger.info(f"Audio WebSocket connected: {client_id}")

    try:
        # Send connection confirmation
        await websocket.send_json({"type": "state", "data": "idle"})
        logger.info("Sent initial state to client")
    except Exception as e:
        logger.error(f"Failed to send initial state: {e}")
        return

    try:
        runtime_credentials = await get_runtime_credentials()

        # Import Pipecat frames
        logger.info("Importing Pipecat modules...")
        from pipecat.frames.frames import (
            InputAudioRawFrame,
            OutputAudioRawFrame,
            TextFrame,
            TranscriptionFrame,
            TTSStartedFrame,
            TTSStoppedFrame,
            LLMFullResponseStartFrame,
            LLMFullResponseEndFrame,
        )
        from pipecat.pipeline.parallel_pipeline import ParallelPipeline
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
        logger.info("Pipecat modules imported")

        # Initialize services
        logger.info("Initializing STT service...")
        # Configure STT with explicit sample rate matching our input audio
        from deepgram import LiveOptions
        stt = DeepgramSTTService(
            api_key=runtime_credentials["deepgram_api_key"],
            sample_rate=16000,  # Explicit sample rate matching our audio
            live_options=LiveOptions(
                encoding="linear16",
                sample_rate=16000,
                channels=1,
                interim_results=True,
                punctuate=True,
                endpointing=1500,  # Wait 1.5s of silence before ending utterance
            ),
        )

        # Add event handlers to trace STT activity
        @stt.event_handler("on_transcription")
        async def on_transcription(service, frame):
            logger.info(f">>> STT TRANSCRIPTION: {frame.text}")

        @stt.event_handler("on_interim_transcription")
        async def on_interim_transcription(service, frame):
            logger.info(f">>> STT INTERIM: {frame.text}")

        logger.info("STT initialized with explicit sample_rate=16000")

        logger.info("Initializing LLM service...")
        llm = AnthropicLLMService(
            api_key=runtime_credentials["anthropic_api_key"],
            model=settings.anthropic_model,
            function_call_timeout_secs=FUNCTION_CALL_TIMEOUT,
        )
        logger.info("LLM initialized")

        logger.info("Initializing TTS service...")
        tts = CartesiaTTSService(
            api_key=runtime_credentials["cartesia_api_key"],
            voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",
        )
        logger.info("TTS initialized")

        # Register tools
        logger.info("Registering tools...")
        register_all_tools(llm)
        logger.info("Tools registered")

        # Set up context
        logger.info("Setting up context...")
        tools = get_all_tools()
        context = OpenAILLMContext(
            messages=[{"role": "system", "content": build_runtime_system_prompt()}],
            tools=tools,
        )
        # Use the default context aggregator - the deprecated one handles UserStoppedSpeakingFrame natively
        context_aggregator = llm.create_context_aggregator(context)
        logger.info("Context set up")

        # Import additional frame types for tool handling
        from pipecat.frames.frames import FunctionCallInProgressFrame, FunctionCallResultFrame, FunctionCallsStartedFrame, AudioRawFrame

        # Debug processor to trace all frames
        class DebugFrameProcessor(FrameProcessor):
            def __init__(self, name: str):
                super().__init__()
                self._name = name

            async def process_frame(self, frame, direction):
                await super().process_frame(frame, direction)
                # Log non-audio frames (audio frames are too frequent)
                if not isinstance(frame, (AudioRawFrame, InputAudioRawFrame, OutputAudioRawFrame)):
                    # Log extra details for function call frames
                    if isinstance(frame, FunctionCallResultFrame):
                        tool_call_id = getattr(frame, 'tool_call_id', 'N/A')
                        function_name = getattr(frame, 'function_name', 'N/A')
                        result_len = len(str(frame.result)) if hasattr(frame, 'result') and frame.result else 0
                        run_llm = getattr(frame, 'run_llm', 'N/A')
                        properties = getattr(frame, 'properties', None)
                        props_run_llm = properties.run_llm if properties else 'NO_PROPS'
                        logger.info(f">>> [{self._name}] FunctionCallResultFrame (dir={direction}) tool_call_id={tool_call_id}, function={function_name}, result_len={result_len}, run_llm={run_llm}, properties.run_llm={props_run_llm}")
                    elif isinstance(frame, FunctionCallsStartedFrame):
                        logger.info(f">>> [{self._name}] FunctionCallsStartedFrame (dir={direction})")
                    elif isinstance(frame, FunctionCallInProgressFrame):
                        tool_call_id = getattr(frame, 'tool_call_id', 'N/A')
                        function_name = getattr(frame, 'function_name', 'N/A')
                        logger.info(f">>> [{self._name}] FunctionCallInProgressFrame (dir={direction}) tool_call_id={tool_call_id}, function={function_name}")
                    elif "Context" in type(frame).__name__:
                        # Log context frames which trigger the LLM
                        logger.info(f">>> [{self._name}] {type(frame).__name__} (dir={direction}) - CONTEXT FRAME!")
                    else:
                        logger.info(f">>> [{self._name}] {type(frame).__name__} (dir={direction})")
                elif isinstance(frame, (InputAudioRawFrame, AudioRawFrame)):
                    # Log audio frames less frequently
                    if hasattr(frame, 'audio') and len(frame.audio) > 0:
                        logger.debug(f">>> [{self._name}] {type(frame).__name__}: {len(frame.audio)} bytes")
                await self.push_frame(frame, direction)

        # Shared state between processors for function call tracking
        class SharedState:
            def __init__(self):
                self.tool_call_ids: set[str] = set()
                self.completed_tool_call_ids: set[str] = set()
                self.turn_counter = 0
                self.turn_has_activity = False
                self.current_state = "idle"
                self.llm_responses_in_flight = 0
                self.no_activity_timeout_task: asyncio.Task | None = None
                self.turn_recovery_timeout_task: asyncio.Task | None = None
                self.disconnected = False

            async def send_json(self, payload: dict) -> bool:
                if self.disconnected:
                    return False
                try:
                    await asyncio.wait_for(websocket.send_json(payload), timeout=2.0)
                    return True
                except asyncio.TimeoutError:
                    logger.warning(
                        f"WebSocket send timed out for payload type={payload.get('type')}"
                    )
                    return False
                except Exception:
                    self.disconnected = True
                    return False

            async def send_state(self, state: str) -> None:
                self.current_state = state
                await self.send_json({"type": "state", "data": state})
                if state == "idle":
                    self.cancel_turn_timeouts()

            def cancel_turn_timeouts(self) -> None:
                current_task = asyncio.current_task()
                if (
                    self.no_activity_timeout_task
                    and not self.no_activity_timeout_task.done()
                    and self.no_activity_timeout_task is not current_task
                ):
                    self.no_activity_timeout_task.cancel()
                if (
                    self.turn_recovery_timeout_task
                    and not self.turn_recovery_timeout_task.done()
                    and self.turn_recovery_timeout_task is not current_task
                ):
                    self.turn_recovery_timeout_task.cancel()
                self.no_activity_timeout_task = None
                self.turn_recovery_timeout_task = None

            def mark_turn_activity(self) -> None:
                self.turn_has_activity = True
                current_task = asyncio.current_task()
                if (
                    self.no_activity_timeout_task
                    and not self.no_activity_timeout_task.done()
                    and self.no_activity_timeout_task is not current_task
                ):
                    self.no_activity_timeout_task.cancel()
                self.no_activity_timeout_task = None

            def on_llm_response_started(self) -> None:
                self.llm_responses_in_flight += 1

            def on_llm_response_ended(self) -> None:
                if self.llm_responses_in_flight > 0:
                    self.llm_responses_in_flight -= 1

            def start_turn_timeouts(self) -> None:
                self.cancel_turn_timeouts()
                self.turn_counter += 1
                turn_id = self.turn_counter
                self.turn_has_activity = False
                self.completed_tool_call_ids = set()
                self.no_activity_timeout_task = asyncio.create_task(
                    self._no_activity_timeout(turn_id)
                )
                self.turn_recovery_timeout_task = asyncio.create_task(
                    self._turn_recovery_timeout(turn_id)
                )

            def should_emit_tool_complete(self, tool_call_id: str | None) -> bool:
                if not tool_call_id:
                    return True
                if tool_call_id in self.completed_tool_call_ids:
                    return False
                self.completed_tool_call_ids.add(tool_call_id)
                return True

            async def _no_activity_timeout(self, turn_id: int) -> None:
                try:
                    await asyncio.sleep(NO_ACTIVITY_AFTER_EOS_TIMEOUT)
                    if (
                        self.disconnected
                        or turn_id != self.turn_counter
                        or self.turn_has_activity
                    ):
                        return
                    logger.warning(
                        "No transcription/activity after end_of_speech - returning to idle"
                    )
                    await self.send_state("idle")
                except asyncio.CancelledError:
                    pass

            async def _turn_recovery_timeout(self, turn_id: int) -> None:
                try:
                    await asyncio.sleep(TURN_RECOVERY_TIMEOUT)
                    if self.disconnected or turn_id != self.turn_counter:
                        return
                    if self.current_state in {"processing", "listening"}:
                        logger.warning(
                            "Turn recovery timeout reached - forcing idle state"
                        )
                        await self.send_state("idle")
                except asyncio.CancelledError:
                    pass

            def mark_disconnected(self) -> None:
                self.disconnected = True
                self.cancel_turn_timeouts()

        shared_state = SharedState()

        # Processor to capture LLM text output BEFORE TTS
        class LLMTextCaptureProcessor(FrameProcessor):
            def __init__(self, ws: WebSocket, state: SharedState):
                super().__init__()
                self._websocket = ws
                self._state = state
                self._accumulated_text = ""  # Accumulate full response
                self._disconnected = False
                self._max_email_cards = 25

            def _compact_email_data(self, result_data):
                if isinstance(result_data, dict):
                    # Tool responses may wrap sample messages as {"emails": [...], "total_count": N}
                    if isinstance(result_data.get("emails"), list):
                        result_data = result_data.get("emails", [])
                    else:
                        result_data = [result_data]

                if not isinstance(result_data, list):
                    return None

                if not result_data or not isinstance(result_data[0], dict) or "subject" not in result_data[0]:
                    return None

                compact = []
                for email in result_data[: self._max_email_cards]:
                    from_value = email.get("from", [])
                    if isinstance(from_value, list):
                        from_value = from_value[:1]
                    compact.append(
                        {
                            "id": email.get("id"),
                            "subject": email.get("subject"),
                            "from": from_value,
                            "date": email.get("date"),
                            "unread": email.get("unread"),
                            "snippet": (email.get("snippet") or "")[:240],
                        }
                    )
                return compact

            def mark_disconnected(self):
                self._disconnected = True

            async def process_frame(self, frame, direction):
                await super().process_frame(frame, direction)

                # Don't try to send if already disconnected
                if self._disconnected:
                    await self.push_frame(frame, direction)
                    return

                # FunctionCallResultFrame may not always reach the output processor branch.
                # Handle completion here so tool state consistently clears.
                if isinstance(frame, FunctionCallResultFrame):
                    logger.info(f">>> LLMTextCapture: FunctionCallResultFrame received (dir={direction})")
                    tool_call_id = getattr(frame, "tool_call_id", None)
                    if tool_call_id:
                        self._state.tool_call_ids.discard(tool_call_id)
                    self._state.mark_turn_activity()

                    if self._state.should_emit_tool_complete(tool_call_id):
                        tool_name = getattr(frame, "function_name", "tool")
                        try:
                            await self._state.send_json(
                                {
                                    "type": "tool_activity",
                                    "data": {"tool": tool_name, "status": "complete"},
                                }
                            )
                            if hasattr(frame, "result") and frame.result:
                                try:
                                    result_data = json.loads(frame.result) if isinstance(frame.result, str) else frame.result
                                    compact_email_data = self._compact_email_data(result_data)
                                    if compact_email_data:
                                        await self._state.send_json(
                                            {
                                                "type": "email_data",
                                                "data": compact_email_data,
                                            }
                                        )
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        except Exception:
                            pass

                # Only capture DOWNSTREAM frames (from LLM toward TTS)
                # Still push all frames through
                is_downstream = (direction == FrameDirection.DOWNSTREAM)

                if is_downstream and isinstance(frame, TextFrame):
                    text = frame.text
                    logger.debug(f"LLMTextCapture: '{text[:50] if len(text) > 50 else text}' (dir={direction})")

                    self._accumulated_text += text

                    try:
                        await self._websocket.send_json({
                            "type": "transcript",
                            "data": {"role": "assistant", "text": text}
                        })
                    except Exception:
                        self._disconnected = True

                elif is_downstream and isinstance(frame, LLMFullResponseEndFrame):
                    logger.debug(f"LLMTextCapture: Response ended, total len={len(self._accumulated_text)}")
                    self._accumulated_text = ""
                    self._state.on_llm_response_ended()
                    # Fallback: if synthesis didn't start for this response, do not
                    # leave the client stuck in processing.
                    if (
                        not self._state.tool_call_ids
                        and self._state.current_state != "speaking"
                        and self._state.llm_responses_in_flight == 0
                    ):
                        try:
                            await self._state.send_state("idle")
                        except Exception:
                            pass

                elif is_downstream and isinstance(frame, FunctionCallInProgressFrame):
                    self._state.mark_turn_activity()
                    tool_call_id = getattr(frame, "tool_call_id", None)
                    if tool_call_id:
                        self._state.tool_call_ids.add(tool_call_id)
                    try:
                        tool_name = frame.function_name if hasattr(frame, 'function_name') else 'tool'
                        await self._state.send_json({
                            "type": "tool_activity",
                            "data": {"tool": tool_name, "status": "running"}
                        })
                    except Exception:
                        pass

                elif is_downstream and isinstance(frame, LLMFullResponseStartFrame):
                    logger.info(">>> LLM RESPONSE STARTED")
                    self._accumulated_text = ""
                    self._state.on_llm_response_started()
                    self._state.mark_turn_activity()
                    try:
                        await self._state.send_state("processing")
                    except Exception:
                        pass

                # Always push frame through to next processor
                await self.push_frame(frame, direction)

        # Custom processor to send audio back to WebSocket
        class WebSocketOutputProcessor(FrameProcessor):
            def __init__(self, ws: WebSocket, state: SharedState):
                super().__init__()
                self._websocket = ws
                self._state = state
                self._disconnected = False
                self._max_email_cards = 25

            def _compact_email_data(self, result_data):
                """Return a smaller email payload to avoid stalling websocket writes."""
                if isinstance(result_data, dict):
                    # Tool responses may wrap sample messages as {"emails": [...], "total_count": N}
                    if isinstance(result_data.get("emails"), list):
                        result_data = result_data.get("emails", [])
                    else:
                        result_data = [result_data]

                if not isinstance(result_data, list):
                    return None

                if not result_data or not isinstance(result_data[0], dict) or "subject" not in result_data[0]:
                    return None

                compact = []
                for email in result_data[: self._max_email_cards]:
                    from_value = email.get("from", [])
                    if isinstance(from_value, list):
                        from_value = from_value[:1]
                    compact.append(
                        {
                            "id": email.get("id"),
                            "subject": email.get("subject"),
                            "from": from_value,
                            "date": email.get("date"),
                            "unread": email.get("unread"),
                            "snippet": (email.get("snippet") or "")[:240],
                        }
                    )

                if len(result_data) > self._max_email_cards:
                    logger.info(
                        f"Truncated email_data payload from {len(result_data)} to {self._max_email_cards} items"
                    )

                return compact

            def mark_disconnected(self):
                self._disconnected = True

            async def process_frame(self, frame, direction):
                await super().process_frame(frame, direction)

                # Don't try to send if already disconnected
                if self._disconnected:
                    await self.push_frame(frame, direction)
                    return

                if isinstance(frame, OutputAudioRawFrame):
                    # Send audio bytes to client
                    try:
                        await self._websocket.send_bytes(frame.audio)
                    except Exception as e:
                        # Mark as disconnected to stop spamming errors
                        self._disconnected = True
                        logger.debug(f"WebSocket disconnected, stopping audio send")

                elif isinstance(frame, TranscriptionFrame):
                    # Send transcription to client (user's speech)
                    logger.info(f">>> TRANSCRIPTION received: '{frame.text}'")
                    self._state.mark_turn_activity()
                    try:
                        await self._state.send_json({
                            "type": "transcript",
                            "data": {"role": "user", "text": frame.text}
                        })
                        # Also signal that we received the user's input
                        await self._state.send_state("processing")
                        logger.info(">>> Sent processing state to client")
                    except Exception as e:
                        logger.error(f">>> Error sending transcription: {e}")

                elif isinstance(frame, TTSStartedFrame):
                    logger.info("TTS Started - sending 'speaking' state")
                    self._state.mark_turn_activity()
                    try:
                        await self._state.send_state("speaking")
                    except Exception:
                        pass

                elif isinstance(frame, TTSStoppedFrame):
                    # Only send idle if no function call is in progress
                    if (
                        not self._state.tool_call_ids
                        and self._state.llm_responses_in_flight == 0
                    ):
                        logger.info("TTS Stopped - sending 'idle' state")
                        try:
                            await self._state.send_state("idle")
                        except Exception:
                            pass
                    else:
                        logger.info(
                            "TTS Stopped while tool call or LLM response still active - staying in processing state"
                        )

                elif isinstance(frame, (FunctionCallInProgressFrame, FunctionCallsStartedFrame)):
                    # Track that a function call is running
                    logger.info(f">>> Function call started: {type(frame).__name__}")
                    self._state.mark_turn_activity()
                    if isinstance(frame, FunctionCallsStartedFrame):
                        function_calls = getattr(frame, "function_calls", []) or []
                        for call in function_calls:
                            tool_call_id = getattr(call, "tool_call_id", None)
                            if tool_call_id:
                                self._state.tool_call_ids.add(tool_call_id)
                    else:
                        tool_call_id = getattr(frame, "tool_call_id", None)
                        if tool_call_id:
                            self._state.tool_call_ids.add(tool_call_id)
                    # Send processing state to keep UI showing activity
                    try:
                        await self._state.send_state("processing")
                    except Exception:
                        pass

                elif isinstance(frame, FunctionCallResultFrame):
                    # Tool finished - track state but DON'T send 'idle' yet
                    # The LLM will process the result and generate a follow-up response
                    result_size = len(str(frame.result)) if hasattr(frame, 'result') and frame.result else 0
                    logger.info(f">>> WebSocketOutput: Function call completed - result size: {result_size} chars")
                    logger.info(">>> Waiting for LLM to process result and generate follow-up response")
                    self._state.mark_turn_activity()
                    tool_call_id = getattr(frame, "tool_call_id", None)
                    if tool_call_id:
                        self._state.tool_call_ids.discard(tool_call_id)
                    tool_name = getattr(frame, "function_name", "tool")

                    try:
                        if self._state.should_emit_tool_complete(tool_call_id):
                            logger.info(">>> WebSocketOutput: sending tool_activity complete")
                            await self._state.send_json({
                                "type": "tool_activity",
                                "data": {"tool": tool_name, "status": "complete"}
                            })
                            logger.info(">>> WebSocketOutput: tool_activity complete send returned")

                            # Try to parse email data from tool result for structured display
                            if hasattr(frame, 'result') and frame.result:
                                try:
                                    logger.info(">>> WebSocketOutput: parsing tool result for email_data")
                                    result_data = json.loads(frame.result) if isinstance(frame.result, str) else frame.result
                                    compact_email_data = self._compact_email_data(result_data)
                                    if compact_email_data:
                                        logger.info(
                                            f">>> WebSocketOutput: sending email_data count={len(compact_email_data)}"
                                        )
                                        await self._state.send_json(
                                            {
                                                "type": "email_data",
                                                "data": compact_email_data,
                                            }
                                        )
                                        logger.info(">>> WebSocketOutput: email_data send returned")
                                except (json.JSONDecodeError, TypeError):
                                    pass

                        # DON'T send 'idle' here! The LLM will process the function result
                        # and generate a spoken response. Wait for TTSStopped from THAT response.
                    except Exception:
                        pass

                    logger.info(">>> WebSocketOutput: forwarding FunctionCallResultFrame downstream to assistant aggregator")

                await self.push_frame(frame, direction)

        llm_text_capture = LLMTextCaptureProcessor(websocket, shared_state)
        ws_output = WebSocketOutputProcessor(websocket, shared_state)
        logger.info("WebSocket processors created")

        # Create pipeline
        # Split post-LLM processing into parallel branches:
        # - one branch handles streaming/TTS/output
        # - one branch updates assistant context, including tool call results
        logger.info("Creating pipeline...")
        pipeline = Pipeline([
            stt,
            context_aggregator.user(),
            llm,
            ParallelPipeline(
                [llm_text_capture, tts, ws_output],
                [context_aggregator.assistant()],
            ),
        ])
        logger.info("Pipeline created")

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
            ),
            idle_timeout_secs=None,  # Disable idle timeout for push-to-talk mode
            cancel_on_idle_timeout=False,
        )
        logger.info("Pipeline task created")

        # Start pipeline in background
        logger.info("Starting pipeline runner...")
        runner = PipelineRunner()
        pipeline_task = asyncio.create_task(runner.run(task))

        # Add callback to catch pipeline errors
        def pipeline_done_callback(task_result):
            try:
                exc = task_result.exception()
                if exc:
                    logger.error(f">>> PIPELINE ERROR: {exc}")
                    import traceback as tb
                    tb.print_exception(type(exc), exc, exc.__traceback__)
            except asyncio.CancelledError:
                logger.info("Pipeline task was cancelled (expected on disconnect)")
            except asyncio.InvalidStateError:
                pass  # Task not done yet

        pipeline_task.add_done_callback(pipeline_done_callback)
        logger.info("Pipeline running in background, waiting for audio...")

        # Import frames for push-to-talk and interruption
        from pipecat.frames.frames import UserStartedSpeakingFrame, UserStoppedSpeakingFrame, BotStoppedSpeakingFrame, VADUserStoppedSpeakingFrame

        # Push-to-talk state - only process audio when user explicitly starts speaking
        is_listening = False

        # Process incoming audio and control messages
        try:
            while True:
                # Receive either bytes (audio) or text (control messages)
                message = await websocket.receive()

                if "bytes" in message:
                    # Only process audio when in listening mode (push-to-talk)
                    if not is_listening:
                        continue

                    data = message["bytes"]
                    logger.debug(f"Received {len(data)} bytes of audio")

                    # Create audio frame and queue it
                    audio_frame = InputAudioRawFrame(
                        audio=data,
                        sample_rate=16000,
                        num_channels=1
                    )
                    await task.queue_frame(audio_frame)

                elif "text" in message:
                    # Handle control messages
                    try:
                        control = json.loads(message["text"])
                        if control.get("type") == "start_listening":
                            logger.info("User started speaking - enabling audio processing")
                            is_listening = True
                            shared_state.cancel_turn_timeouts()
                            await shared_state.send_state("listening")
                            # Signal pipeline that user started speaking
                            await task.queue_frame(UserStartedSpeakingFrame())
                        elif control.get("type") == "end_of_speech":
                            logger.info("Received end_of_speech signal - finalizing transcription and triggering LLM")
                            is_listening = False  # Stop processing audio until next start_listening
                            shared_state.tool_call_ids.clear()
                            shared_state.start_turn_timeouts()
                            await shared_state.send_state("processing")
                            # Send VADUserStoppedSpeakingFrame to trigger STT finalization
                            # This is the frame type that DeepgramSTTService listens for to call finalize()
                            await task.queue_frame(VADUserStoppedSpeakingFrame())
                            # Send UserStoppedSpeakingFrame to trigger turn stop in the context aggregator
                            # This tells the ExternalUserTurnStopStrategy that the user's turn has ended,
                            # which causes the accumulated transcription to be pushed to the LLM
                            await task.queue_frame(UserStoppedSpeakingFrame())
                        elif control.get("type") == "interrupt":
                            logger.info("Received interrupt signal - stopping current response")
                            is_listening = False  # Also stop listening on interrupt
                            shared_state.cancel_turn_timeouts()
                            shared_state.tool_call_ids.clear()
                            # Queue a BotStoppedSpeakingFrame to signal the bot should stop
                            await task.queue_frame(BotStoppedSpeakingFrame())
                            # Send idle state back to client immediately
                            await shared_state.send_state("idle")
                        elif control.get("type") == "ping":
                            # Heartbeat ping - respond with pong
                            await websocket.send_json({"type": "pong"})
                        elif control.get("type") == "debug_text_query":
                            text = (control.get("text") or "").strip()
                            if text:
                                logger.info(f"Received debug_text_query: {text}")
                                is_listening = False
                                shared_state.tool_call_ids.clear()
                                shared_state.start_turn_timeouts()
                                await shared_state.send_state("processing")
                                from pipecat.utils.time import time_now_iso8601
                                await task.queue_frame(UserStartedSpeakingFrame())
                                await task.queue_frame(
                                    TranscriptionFrame(
                                        text=text,
                                        user_id="debug-user",
                                        timestamp=time_now_iso8601(),
                                        finalized=True,
                                    )
                                )
                                await task.queue_frame(UserStoppedSpeakingFrame())
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON control message: {message['text']}")

        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected")
        except RuntimeError as e:
            # Handle "Cannot call receive once a disconnect message has been received"
            if "disconnect" in str(e).lower():
                logger.info(f"Client {client_id} disconnected (RuntimeError)")
            else:
                raise
        finally:
            # Mark processors as disconnected BEFORE cancelling pipeline
            # This prevents them from trying to send data after WebSocket is closed
            llm_text_capture.mark_disconnected()
            ws_output.mark_disconnected()
            shared_state.mark_disconnected()

            pipeline_task.cancel()
            try:
                await pipeline_task
            except asyncio.CancelledError:
                pass

    except RuntimeError as e:
        logger.error(f"Audio WebSocket runtime error: {e}")
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
            await websocket.close(code=1011)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Audio WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client_id in active_connections:
            del active_connections[client_id]
        logger.info(f"Audio WebSocket disconnected: {client_id}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
