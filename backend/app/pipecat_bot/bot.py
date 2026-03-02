import asyncio
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
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


async def create_bot(websocket_client, client_id: str):
    """Create and run a Pipecat bot instance for a connected client."""
    settings = get_settings()

    logger.info(f"Creating bot for client: {client_id}")

    # Initialize services
    stt = DeepgramSTTService(
        api_key=settings.deepgram_api_key,
    )

    llm = AnthropicLLMService(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )

    tts = CartesiaTTSService(
        api_key=settings.cartesia_api_key,
        voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",  # Default voice
    )

    # Register tools with the LLM
    register_all_tools(llm)

    # Set up conversation context with system prompt and tools
    tools = get_all_tools()

    context = OpenAILLMContext(
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ],
        tools=tools,
    )

    context_aggregator = llm.create_context_aggregator(context)

    # Create the pipeline
    pipeline = Pipeline(
        [
            stt,                           # Speech to text
            context_aggregator.user(),     # Aggregate user messages
            llm,                           # LLM processing
            tts,                           # Text to speech
            context_aggregator.assistant() # Aggregate assistant messages
        ]
    )

    # Create pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    return task


async def run_websocket_server():
    """Run the Pipecat WebSocket server for handling voice connections."""
    settings = get_settings()

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
        api_key=settings.deepgram_api_key,
    )

    llm = AnthropicLLMService(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )

    tts = CartesiaTTSService(
        api_key=settings.cartesia_api_key,
        voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",
    )

    # Register tools
    register_all_tools(llm)

    # Set up context
    tools = get_all_tools()
    context = OpenAILLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
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
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected: {client}")
        # Send initial greeting
        await task.queue_frames(
            [
                # Could add initial TTS greeting here
            ]
        )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected: {client}")

    runner = PipelineRunner()

    logger.info(f"Starting WebSocket server on port {settings.port + 1}")
    await runner.run(task)
