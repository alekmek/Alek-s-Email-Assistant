import json
import re
import traceback

from loguru import logger
from pipecat.frames.frames import FunctionCallResultProperties
from pipecat.services.llm_service import FunctionCallParams

from app.services.nylas_service import get_nylas_service
from app.services.settings_service import SettingsService

MAX_LLM_EMAIL_SAMPLES = 6
MAX_UNREAD_SAMPLES = 6
MAX_SNIPPET_CHARS = 160
MAX_BODY_CHARS = 900


def _compact_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff\u034f]", "", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _compact_participants(value):
    if not isinstance(value, list):
        return []
    compact = []
    for item in value[:1]:
        if isinstance(item, dict):
            compact.append(
                {
                    "name": item.get("name", ""),
                    "email": item.get("email", ""),
                }
            )
    return compact


def _compact_email_for_llm(email: dict, include_body: bool = False) -> dict:
    result = {
        "id": email.get("id"),
        "subject": _compact_text(email.get("subject"), 200),
        "from": _compact_participants(email.get("from")),
        "to": _compact_participants(email.get("to")),
        "date": email.get("date"),
        "unread": bool(email.get("unread", False)),
        "snippet": _compact_text(email.get("snippet"), MAX_SNIPPET_CHARS),
        "thread_id": email.get("thread_id"),
        "attachments": [
            {
                "id": a.get("id"),
                "filename": a.get("filename"),
                "content_type": a.get("content_type"),
            }
            for a in (email.get("attachments") or [])[:5]
            if isinstance(a, dict)
        ],
    }

    if include_body:
        body = email.get("body") or ""
        body_compact = _compact_text(body, MAX_BODY_CHARS)
        result["body_excerpt"] = body_compact
        result["body_truncated"] = len(body_compact) < len(body)
        result["body_total_chars"] = len(body)

    return result


def _compact_search_result_for_llm(result: dict) -> dict:
    emails = result.get("emails") or []
    compact_emails = [
        _compact_email_for_llm(email)
        for email in emails[:MAX_LLM_EMAIL_SAMPLES]
        if isinstance(email, dict)
    ]
    return {
        "total_count": result.get("total_count", len(compact_emails)),
        "exact_count": bool(result.get("exact_count", False)),
        "returned_count": len(compact_emails),
        "has_more": bool(result.get("has_more", False) or len(emails) > len(compact_emails)),
        "emails": compact_emails,
    }


def _compact_email_detail_for_llm(result: dict) -> dict:
    return _compact_email_for_llm(result, include_body=True)


def _compact_list_unread_for_llm(results: list[dict]) -> list[dict]:
    return [
        _compact_email_for_llm(email)
        for email in results[:MAX_UNREAD_SAMPLES]
        if isinstance(email, dict)
    ]


def get_email_tools() -> list[dict]:
    """Return tool definitions for email operations."""
    return [
        {
            "name": "search_emails",
            "description": "Search for emails in the inbox. Can filter by sender, recipient, subject, keywords, unread status, date range, and folder. Returns an object with exact total_count plus a bounded emails sample. Use received_after/received_before with Unix timestamps for date filtering.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "General search query to find in email content",
                    },
                    "from_email": {
                        "type": "string",
                        "description": "Filter by sender email address",
                    },
                    "to_email": {
                        "type": "string",
                        "description": "Filter by recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Filter by subject line",
                    },
                    "unread": {
                        "type": "boolean",
                        "description": "If true, only return unread emails",
                    },
                    "received_after": {
                        "type": "integer",
                        "description": "Unix timestamp - only return emails received after this time. For example, for emails from the last 24 hours, use current_time - 86400",
                    },
                    "received_before": {
                        "type": "integer",
                        "description": "Unix timestamp - only return emails received before this time",
                    },
                    "in_folder": {
                        "type": "string",
                        "description": "Filter by folder name (e.g., 'inbox', 'sent', 'drafts', 'trash', 'spam')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of email samples to return (default 6).",
                        "default": 6,
                    },
                    "include_total_count": {
                        "type": "boolean",
                        "description": "If true, compute exact total_count across all pages. This is slower; use count_emails for strict counting questions.",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
        {
            "name": "count_emails",
            "description": "Count all emails matching filters using efficient pagination and return exact total_count. Use this for accurate 'how many' questions across full result sets.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "General search query to find in email content",
                    },
                    "from_email": {
                        "type": "string",
                        "description": "Filter by sender email address",
                    },
                    "to_email": {
                        "type": "string",
                        "description": "Filter by recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Filter by subject line",
                    },
                    "unread": {
                        "type": "boolean",
                        "description": "If true, only count unread emails",
                    },
                    "received_after": {
                        "type": "integer",
                        "description": "Unix timestamp - only count emails received after this time",
                    },
                    "received_before": {
                        "type": "integer",
                        "description": "Unix timestamp - only count emails received before this time",
                    },
                    "in_folder": {
                        "type": "string",
                        "description": "Filter by folder name (e.g., 'inbox', 'sent', 'drafts', 'trash', 'spam')",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "get_email_breakdown",
            "description": "Compute an exact inbox breakdown over all matching emails, including categories like spam, important, personal, automated, work, and other. Use for questions that ask for category splits, not just totals.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "General search query to filter emails before categorization",
                    },
                    "from_email": {
                        "type": "string",
                        "description": "Filter by sender email address before categorization",
                    },
                    "to_email": {
                        "type": "string",
                        "description": "Filter by recipient email address before categorization",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Filter by subject line before categorization",
                    },
                    "unread": {
                        "type": "boolean",
                        "description": "If true, only categorize unread emails",
                    },
                    "received_after": {
                        "type": "integer",
                        "description": "Unix timestamp - only include emails received after this time",
                    },
                    "received_before": {
                        "type": "integer",
                        "description": "Unix timestamp - only include emails received before this time",
                    },
                    "in_folder": {
                        "type": "string",
                        "description": "Filter by folder name before categorization (e.g., 'inbox', 'spam')",
                    },
                    "include_samples": {
                        "type": "boolean",
                        "description": "Include a few example messages per category",
                        "default": True,
                    },
                    "sample_per_category": {
                        "type": "integer",
                        "description": "How many sample messages to include per category",
                        "default": 2,
                    },
                },
                "required": [],
            },
        },
        {
            "name": "get_email_details",
            "description": "Get the full details and body of a specific email by its ID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the email message to retrieve",
                    },
                },
                "required": ["message_id"],
            },
        },
        {
            "name": "list_unread",
            "description": "Get a list of unread emails in the inbox.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 10)",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
        {
            "name": "send_reply",
            "description": "Send a reply to an email or save it as a draft.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reply_to_message_id": {
                        "type": "string",
                        "description": "The ID of the email to reply to",
                    },
                    "body": {
                        "type": "string",
                        "description": "The body text of the reply",
                    },
                    "send_immediately": {
                        "type": "boolean",
                        "description": "If true, send immediately. If false, save as draft.",
                        "default": False,
                    },
                },
                "required": ["reply_to_message_id", "body"],
            },
        },
        {
            "name": "mark_as_read",
            "description": "Mark an email as read.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the email to mark as read",
                    },
                },
                "required": ["message_id"],
            },
        },
    ]


def register_email_tools(llm) -> None:
    """Register email tool handlers with the LLM service."""

    async def handle_search_emails(params: FunctionCallParams):
        """Handle search_emails tool call."""
        args = params.arguments
        logger.info(f">>> handle_search_emails called with args: {args}")
        logger.info(f">>> tool_call_id: {params.tool_call_id}, function_name: {params.function_name}")
        try:
            nylas = await get_nylas_service()
            settings = await SettingsService.get_settings()
            max_samples = max(1, int(settings.max_emails_per_search or "25"))
            requested_limit = int(args.get("limit", max_samples) or max_samples)
            sample_limit = max(1, min(requested_limit, max_samples, MAX_LLM_EMAIL_SAMPLES))
            include_total_count = bool(args.get("include_total_count", False))
            logger.info(">>> NylasService obtained, calling search_emails...")

            results = await nylas.search_emails(
                query=args.get("query"),
                from_email=args.get("from_email"),
                to_email=args.get("to_email"),
                subject=args.get("subject"),
                unread=args.get("unread"),
                received_after=args.get("received_after"),
                received_before=args.get("received_before"),
                in_folder=args.get("in_folder"),
                limit=sample_limit,
                include_total_count=include_total_count,
            )
            compact_results = _compact_search_result_for_llm(results)

            total_count = compact_results.get("total_count", 0)
            returned_count = compact_results.get("returned_count", 0)
            logger.info(
                f">>> search_emails returned sample_count={returned_count}, total_count={total_count}"
            )
            # Return the result as a dict/list, not JSON string - pipecat will serialize it
            # IMPORTANT: Set run_llm=True to ensure the LLM processes the result and responds
            logger.info(">>> Calling result_callback with paginated count + sample results, run_llm=True")
            await params.result_callback(
                compact_results,
                properties=FunctionCallResultProperties(run_llm=True)
            )
            logger.info(">>> result_callback completed successfully")
        except Exception as e:
            logger.error(f">>> search_emails ERROR: {e}")
            logger.error(traceback.format_exc())
            # Return error to the LLM so it can inform the user
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    async def handle_count_emails(params: FunctionCallParams):
        """Handle count_emails tool call."""
        args = params.arguments
        logger.info(f">>> handle_count_emails called with args: {args}")
        try:
            nylas = await get_nylas_service()
            result = await nylas.count_emails(
                query=args.get("query"),
                from_email=args.get("from_email"),
                to_email=args.get("to_email"),
                subject=args.get("subject"),
                unread=args.get("unread"),
                received_after=args.get("received_after"),
                received_before=args.get("received_before"),
                in_folder=args.get("in_folder"),
            )
            logger.info(f">>> count_emails total_count={result.get('total_count')}")
            await params.result_callback(
                result,
                properties=FunctionCallResultProperties(run_llm=True)
            )
            logger.info(">>> count_emails result_callback completed")
        except Exception as e:
            logger.error(f">>> count_emails ERROR: {e}")
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    async def handle_get_email_details(params: FunctionCallParams):
        """Handle get_email_details tool call."""
        args = params.arguments
        logger.info(f">>> handle_get_email_details called with args: {args}")
        try:
            nylas = await get_nylas_service()
            result = await nylas.get_email_details(args["message_id"])
            compact_result = _compact_email_detail_for_llm(result)
            await params.result_callback(
                compact_result,
                properties=FunctionCallResultProperties(run_llm=True)
            )
            logger.info(">>> get_email_details result_callback completed")
        except Exception as e:
            logger.error(f">>> get_email_details ERROR: {e}")
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    async def handle_get_email_breakdown(params: FunctionCallParams):
        """Handle get_email_breakdown tool call."""
        args = params.arguments
        logger.info(f">>> handle_get_email_breakdown called with args: {args}")
        try:
            nylas = await get_nylas_service()
            result = await nylas.get_email_breakdown(
                query=args.get("query"),
                from_email=args.get("from_email"),
                to_email=args.get("to_email"),
                subject=args.get("subject"),
                unread=args.get("unread"),
                received_after=args.get("received_after"),
                received_before=args.get("received_before"),
                in_folder=args.get("in_folder"),
                include_samples=bool(args.get("include_samples", True)),
                sample_per_category=int(args.get("sample_per_category", 2) or 2),
            )
            logger.info(
                ">>> get_email_breakdown total_count="
                f"{result.get('total_count')}, breakdown={result.get('breakdown')}"
            )
            await params.result_callback(
                result,
                properties=FunctionCallResultProperties(run_llm=True),
            )
            logger.info(">>> get_email_breakdown result_callback completed")
        except Exception as e:
            logger.error(f">>> get_email_breakdown ERROR: {e}")
            logger.error(traceback.format_exc())
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True),
            )

    async def handle_list_unread(params: FunctionCallParams):
        """Handle list_unread tool call."""
        args = params.arguments
        logger.info(f">>> handle_list_unread called with args: {args}")
        try:
            nylas = await get_nylas_service()
            requested_limit = int(args.get("limit", MAX_UNREAD_SAMPLES) or MAX_UNREAD_SAMPLES)
            limit = max(1, min(requested_limit, MAX_UNREAD_SAMPLES))
            results = await nylas.list_unread(limit=limit)
            compact_results = _compact_list_unread_for_llm(results)
            await params.result_callback(
                compact_results,
                properties=FunctionCallResultProperties(run_llm=True)
            )
            logger.info(">>> list_unread result_callback completed")
        except Exception as e:
            logger.error(f">>> list_unread ERROR: {e}")
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    async def handle_send_reply(params: FunctionCallParams):
        """Handle send_reply tool call."""
        args = params.arguments
        logger.info(f">>> handle_send_reply called with args: {args}")
        try:
            nylas = await get_nylas_service()
            result = await nylas.send_reply(
                reply_to_message_id=args["reply_to_message_id"],
                body=args["body"],
                send_immediately=args.get("send_immediately", False),
            )
            await params.result_callback(
                result,
                properties=FunctionCallResultProperties(run_llm=True)
            )
            logger.info(">>> send_reply result_callback completed")
        except Exception as e:
            logger.error(f">>> send_reply ERROR: {e}")
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    async def handle_mark_as_read(params: FunctionCallParams):
        """Handle mark_as_read tool call."""
        args = params.arguments
        logger.info(f">>> handle_mark_as_read called with args: {args}")
        try:
            nylas = await get_nylas_service()
            result = await nylas.mark_as_read(args["message_id"])
            await params.result_callback(
                result,
                properties=FunctionCallResultProperties(run_llm=True)
            )
            logger.info(">>> mark_as_read result_callback completed")
        except Exception as e:
            logger.error(f">>> mark_as_read ERROR: {e}")
            await params.result_callback(
                {"error": str(e)},
                properties=FunctionCallResultProperties(run_llm=True)
            )

    # Register all handlers
    llm.register_function("search_emails", handle_search_emails)
    llm.register_function("count_emails", handle_count_emails)
    llm.register_function("get_email_breakdown", handle_get_email_breakdown)
    llm.register_function("get_email_details", handle_get_email_details)
    llm.register_function("list_unread", handle_list_unread)
    llm.register_function("send_reply", handle_send_reply)
    llm.register_function("mark_as_read", handle_mark_as_read)
