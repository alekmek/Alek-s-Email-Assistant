import asyncio
import json

from loguru import logger
from pipecat.frames.frames import TTSSpeakFrame, FunctionCallResultProperties
from pipecat.services.llm_service import FunctionCallParams

from app.services.nylas_service import get_nylas_service
from app.services.attachment_processor import get_attachment_processor


# Threshold for "large" attachments that need special handling (5MB)
LARGE_ATTACHMENT_THRESHOLD = 5 * 1024 * 1024


def get_attachment_tools() -> list[dict]:
    """Return tool definitions for attachment operations."""
    return [
        {
            "name": "read_attachment",
            "description": "Download and analyze an email attachment. Can process PDFs, images, Word documents, Excel spreadsheets, and text files. Use this when the user asks about the contents of an attachment.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the email containing the attachment",
                    },
                    "attachment_id": {
                        "type": "string",
                        "description": "The ID of the attachment to read",
                    },
                    "question": {
                        "type": "string",
                        "description": "Optional specific question about the attachment content",
                    },
                },
                "required": ["message_id", "attachment_id"],
            },
        },
    ]


def register_attachment_tools(llm) -> None:
    """Register attachment tool handlers with the LLM service."""

    async def handle_read_attachment(params: FunctionCallParams):
        """Handle read_attachment tool call with long-running operation support."""
        args = params.arguments
        logger.info(f">>> handle_read_attachment called with args: {args}")

        nylas = await get_nylas_service()
        processor = get_attachment_processor()

        message_id = args["message_id"]
        attachment_id = args["attachment_id"]
        question = args.get("question", "")

        try:
            # First check attachment metadata to see if it's large
            metadata = await nylas.get_attachment_metadata(message_id, attachment_id)

            # For large attachments, inform the user we're working on it
            if metadata["size"] > LARGE_ATTACHMENT_THRESHOLD:
                # We'll still process it, but this helps set expectations
                pass

            # Download the attachment
            data, content_type, filename = await nylas.download_attachment(
                message_id, attachment_id
            )

            # Process the attachment
            processed = processor.process(data, content_type, filename)

            if processed["type"] == "unsupported":
                await params.result_callback(
                    {"status": "unsupported", "message": processed["message"]},
                    properties=FunctionCallResultProperties(run_llm=True)
                )
                return

            if processed["type"] == "error":
                await params.result_callback(
                    {"status": "error", "message": processed["message"]},
                    properties=FunctionCallResultProperties(run_llm=True)
                )
                return

            # For text-based content, return it directly
            if processed["type"] == "text":
                result = {
                    "status": "success",
                    "filename": filename,
                    "content_type": content_type,
                    "content": processed["content"],
                }
                if question:
                    result["user_question"] = question

                await params.result_callback(
                    result,
                    properties=FunctionCallResultProperties(run_llm=True)
                )
                return

            # For documents (PDF) and images, include structured payload
            # for the model to analyze
            if processed["type"] in ["document", "image"]:
                # Return the processed content for model analysis.
                result = {
                    "status": "success",
                    "filename": filename,
                    "content_type": content_type,
                    "analysis_type": processed["type"],
                    "content": processed,
                }
                if question:
                    result["user_question"] = question

                await params.result_callback(
                    result,
                    properties=FunctionCallResultProperties(run_llm=True)
                )
                return

        except Exception as e:
            logger.error(f">>> handle_read_attachment ERROR: {e}")
            await params.result_callback(
                {"status": "error", "message": f"Failed to process attachment: {str(e)}"},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    # Register the handler
    llm.register_function("read_attachment", handle_read_attachment)
