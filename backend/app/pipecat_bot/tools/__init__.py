# Tools module
from .email_tools import get_email_tools, register_email_tools
from .attachment_tools import get_attachment_tools, register_attachment_tools


def get_all_tools() -> list[dict]:
    """Get all tool definitions for the assistant."""
    return get_email_tools() + get_attachment_tools()


def register_all_tools(llm) -> None:
    """Register all tool handlers with the LLM service."""
    register_email_tools(llm)
    register_attachment_tools(llm)
