import asyncio
import base64
import re
from typing import Optional, Any
from nylas import Client
from nylas.models.messages import Message
from nylas.models.attachments import Attachment
from loguru import logger

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "live.com",
    "msn.com",
}

IMPORTANT_SUBJECT_KEYWORDS = (
    "urgent",
    "important",
    "action required",
    "asap",
    "deadline",
    "payment due",
    "security alert",
    "verify",
    "approval needed",
    "final notice",
)

AUTOMATED_MARKERS = (
    "no-reply",
    "noreply",
    "donotreply",
    "mailer-daemon",
    "notification",
    "notifications",
    "newsletter",
    "digest",
    "automated",
    "support@",
    "updates@",
    "alerts@",
)


class NylasService:
    """Wrapper for Nylas email API operations."""

    def __init__(self, api_key: str, grant_id: str):
        self.client = Client(
            api_key=api_key,
        )
        self.grant_id = grant_id

    def _build_message_query_params(
        self,
        query: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None,
        subject: Optional[str] = None,
        unread: Optional[bool] = None,
        received_after: Optional[int] = None,
        received_before: Optional[int] = None,
        in_folder: Optional[str] = None,
        limit: Optional[int] = None,
        page_token: Optional[str] = None,
        select: Optional[str] = None,
    ) -> dict[str, Any]:
        query_params: dict[str, Any] = {}

        if limit is not None:
            query_params["limit"] = limit
        if page_token:
            query_params["page_token"] = page_token
        if select:
            query_params["select"] = select
        if query:
            query_params["search_query_native"] = query
        if from_email:
            query_params["from"] = from_email
        if to_email:
            query_params["to"] = to_email
        if subject:
            query_params["subject"] = subject
        if unread is not None:
            query_params["unread"] = unread
        if received_after is not None:
            query_params["received_after"] = received_after
        if received_before is not None:
            query_params["received_before"] = received_before
        if in_folder:
            query_params["in"] = in_folder

        return query_params

    def _is_transient_error(self, error: Exception) -> bool:
        message = str(error).lower()
        transient_markers = (
            "429",
            "too many requests",
            "503",
            "504",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "max retries exceeded",
            "connection reset",
            "connection aborted",
            "connection pool",
        )
        return any(marker in message for marker in transient_markers)

    async def _list_messages_page(
        self,
        query_params: dict[str, Any],
        retries: int = 3,
        initial_backoff_seconds: float = 0.6,
    ):
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                return await asyncio.to_thread(
                    lambda: self.client.messages.list(
                        self.grant_id,
                        query_params=query_params,
                    )
                )
            except Exception as error:
                last_error = error
                is_transient = self._is_transient_error(error)
                if not is_transient or attempt >= retries - 1:
                    raise
                backoff = initial_backoff_seconds * (2 ** attempt)
                logger.warning(
                    f"Transient Nylas list error (attempt {attempt + 1}/{retries}): {error}. "
                    f"Retrying in {backoff:.1f}s"
                )
                await asyncio.sleep(backoff)
        if last_error:
            raise last_error

    async def _count_messages_paginated(self, base_query_params: dict[str, Any]) -> int:
        """Count all messages matching filters using cursor pagination."""
        total_count = 0
        next_cursor: Optional[str] = None

        while True:
            query_params = dict(base_query_params)
            query_params["limit"] = 200  # Nylas max page size
            query_params.setdefault("select", "id")
            if next_cursor:
                query_params["page_token"] = next_cursor

            page = await self._list_messages_page(query_params=query_params)

            page_data = page.data or []
            page_count = len(page_data)
            total_count += page_count
            next_cursor = page.next_cursor

            if not next_cursor or page_count == 0:
                break

        return total_count

    async def search_emails(
        self,
        query: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None,
        subject: Optional[str] = None,
        limit: int = 25,
        unread: Optional[bool] = None,
        received_after: Optional[int] = None,
        received_before: Optional[int] = None,
        in_folder: Optional[str] = None,
        include_total_count: bool = False,
    ) -> dict:
        """Search emails with filters and return sample + accurate total count."""
        logger.info(f"NylasService.search_emails called with limit={limit}, received_after={received_after}")
        sample_limit = max(1, min(int(limit or 25), 200))
        query_params = self._build_message_query_params(
            query=query,
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            unread=unread,
            received_after=received_after,
            received_before=received_before,
            in_folder=in_folder,
            limit=sample_limit,
        )

        logger.info(f"Nylas query_params: {query_params}")
        logger.info("Calling self.client.messages.list() in thread...")

        # Run synchronous Nylas SDK call in a thread to avoid blocking event loop
        messages = await self._list_messages_page(query_params=query_params)
        sample_messages = [self._format_message(msg) for msg in messages.data]
        logger.info(f"Formatted {len(sample_messages)} messages")

        total_count = len(messages.data)
        exact_count = False
        if include_total_count:
            base_query_params = self._build_message_query_params(
                query=query,
                from_email=from_email,
                to_email=to_email,
                subject=subject,
                unread=unread,
                received_after=received_after,
                received_before=received_before,
                in_folder=in_folder,
            )
            try:
                total_count = await self._count_messages_paginated(base_query_params)
                exact_count = True
                logger.info(f"Counted total matching messages: {total_count}")
            except Exception as error:
                logger.warning(
                    "Exact total_count failed during search_emails; "
                    f"continuing with sampled count only: {error}"
                )

        return {
            "total_count": total_count,
            "exact_count": exact_count,
            "returned_count": len(sample_messages),
            "has_more": bool(getattr(messages, "next_cursor", None)) or total_count > len(sample_messages),
            "emails": sample_messages,
        }

    async def count_emails(
        self,
        query: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None,
        subject: Optional[str] = None,
        unread: Optional[bool] = None,
        received_after: Optional[int] = None,
        received_before: Optional[int] = None,
        in_folder: Optional[str] = None,
    ) -> dict:
        """Count all emails matching filters using efficient id-only pagination."""
        logger.info(
            f"NylasService.count_emails called with received_after={received_after}, received_before={received_before}"
        )
        base_query_params = self._build_message_query_params(
            query=query,
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            unread=unread,
            received_after=received_after,
            received_before=received_before,
            in_folder=in_folder,
        )
        total_count = await self._count_messages_paginated(base_query_params)
        return {"total_count": total_count, "exact_count": True}

    async def get_email_details(self, message_id: str) -> dict:
        """Get full details of a specific email."""
        logger.info(f"Getting email details for message_id={message_id}")
        message = await asyncio.to_thread(
            lambda: self.client.messages.find(
                self.grant_id,
                message_id,
            )
        )
        logger.info("Email details retrieved")
        return self._format_message(message.data, include_body=True)

    async def list_unread(self, limit: int = 10) -> list[dict]:
        """Get unread emails."""
        result = await self.search_emails(unread=True, limit=limit, include_total_count=False)
        return result["emails"]

    def _extract_sender(self, msg: Any) -> tuple[str, str]:
        """Extract sender email/name from a message dict or object."""
        if isinstance(msg, dict):
            from_list = msg.get("from", []) or []
        else:
            from_list = getattr(msg, "from_", None) or getattr(msg, "from", []) or []

        if not from_list:
            return "", ""

        first = from_list[0]
        if isinstance(first, dict):
            return (first.get("email", "") or "").lower(), first.get("name", "") or ""

        return (
            (getattr(first, "email", "") or "").lower(),
            getattr(first, "name", "") or "",
        )

    def _extract_subject(self, msg: Any) -> str:
        if isinstance(msg, dict):
            return msg.get("subject", "") or ""
        return getattr(msg, "subject", "") or ""

    def _extract_unread(self, msg: Any) -> bool:
        if isinstance(msg, dict):
            return bool(msg.get("unread", False))
        return bool(getattr(msg, "unread", False))

    def _extract_starred(self, msg: Any) -> bool:
        if isinstance(msg, dict):
            return bool(msg.get("starred", False))
        return bool(getattr(msg, "starred", False))

    def _extract_folders(self, msg: Any) -> list[str]:
        if isinstance(msg, dict):
            folders = msg.get("folders", []) or []
        else:
            folders = getattr(msg, "folders", []) or []

        normalized: list[str] = []
        for folder in folders:
            value = ""
            if isinstance(folder, str):
                value = folder
            elif isinstance(folder, dict):
                value = (
                    folder.get("name")
                    or folder.get("display_name")
                    or folder.get("id")
                    or ""
                )
            else:
                value = (
                    getattr(folder, "name", None)
                    or getattr(folder, "display_name", None)
                    or getattr(folder, "id", "")
                )

            if value:
                normalized.append(str(value).lower())

        return normalized

    def _is_spam_message(self, folders: list[str]) -> bool:
        return any("spam" in folder or "junk" in folder for folder in folders)

    def _is_important_message(self, subject: str, starred: bool) -> bool:
        if starred:
            return True
        lower_subject = subject.lower()
        return any(keyword in lower_subject for keyword in IMPORTANT_SUBJECT_KEYWORDS)

    def _is_automated_message(self, sender_email: str, sender_name: str, subject: str) -> bool:
        haystack = f"{sender_email} {sender_name} {subject}".lower()
        if any(marker in haystack for marker in AUTOMATED_MARKERS):
            return True

        local_part = sender_email.split("@", 1)[0] if "@" in sender_email else sender_email
        return bool(
            re.search(
                r"(no-?reply|do-?not-?reply|mailer-daemon|notification|newsletter|digest|updates?)",
                local_part,
            )
        )

    def _is_personal_sender(self, sender_email: str) -> bool:
        if "@" not in sender_email:
            return False
        domain = sender_email.rsplit("@", 1)[-1].lower()
        return domain in FREE_EMAIL_DOMAINS

    def _categorize_message(self, msg: Any) -> tuple[str, bool, bool]:
        sender_email, sender_name = self._extract_sender(msg)
        subject = self._extract_subject(msg)
        folders = self._extract_folders(msg)
        starred = self._extract_starred(msg)
        unread = self._extract_unread(msg)

        is_spam = self._is_spam_message(folders)
        is_important = self._is_important_message(subject, starred)
        is_automated = self._is_automated_message(sender_email, sender_name, subject)
        is_personal = self._is_personal_sender(sender_email)

        if is_spam:
            category = "spam"
        elif is_important:
            category = "important"
        elif is_personal:
            category = "personal"
        elif is_automated:
            category = "automated"
        elif sender_email:
            category = "work"
        else:
            category = "other"

        return category, unread, starred

    async def get_email_breakdown(
        self,
        query: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None,
        subject: Optional[str] = None,
        unread: Optional[bool] = None,
        received_after: Optional[int] = None,
        received_before: Optional[int] = None,
        in_folder: Optional[str] = None,
        include_samples: bool = True,
        sample_per_category: int = 2,
    ) -> dict:
        """
        Build an exact category breakdown over all matching emails.

        Categories are exclusive: spam, important, personal, automated, work, other.
        """
        logger.info(
            "NylasService.get_email_breakdown called "
            f"received_after={received_after}, received_before={received_before}, in_folder={in_folder}"
        )

        base_query_params = self._build_message_query_params(
            query=query,
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            unread=unread,
            received_after=received_after,
            received_before=received_before,
            in_folder=in_folder,
            select="id,subject,from,date,unread,starred,folders",
        )

        counts = {
            "spam": 0,
            "important": 0,
            "personal": 0,
            "automated": 0,
            "work": 0,
            "other": 0,
        }
        secondary_counts = {
            "unread": 0,
            "starred": 0,
        }
        samples: dict[str, list[dict[str, Any]]] = {k: [] for k in counts.keys()}

        next_cursor: Optional[str] = None
        total_count = 0

        while True:
            query_params = dict(base_query_params)
            query_params["limit"] = 200
            if next_cursor:
                query_params["page_token"] = next_cursor

            page = await self._list_messages_page(query_params=query_params)

            page_data = page.data or []
            if not page_data:
                break

            for msg in page_data:
                category, is_unread, is_starred = self._categorize_message(msg)
                counts[category] += 1
                total_count += 1
                if is_unread:
                    secondary_counts["unread"] += 1
                if is_starred:
                    secondary_counts["starred"] += 1

                if include_samples and len(samples[category]) < max(0, sample_per_category):
                    if isinstance(msg, dict):
                        sample_entry = {
                            "id": msg.get("id"),
                            "subject": msg.get("subject"),
                            "from": msg.get("from", []),
                            "date": msg.get("date"),
                            "unread": bool(msg.get("unread", False)),
                            "starred": bool(msg.get("starred", False)),
                        }
                    else:
                        sample_entry = {
                            "id": getattr(msg, "id", None),
                            "subject": getattr(msg, "subject", None),
                            "from": [
                                {
                                    "name": getattr(p, "name", "") if not isinstance(p, dict) else p.get("name", ""),
                                    "email": getattr(p, "email", "") if not isinstance(p, dict) else p.get("email", ""),
                                }
                                for p in ((getattr(msg, "from_", None) or [])[:1])
                            ],
                            "date": getattr(msg, "date", None),
                            "unread": bool(getattr(msg, "unread", False)),
                            "starred": bool(getattr(msg, "starred", False)),
                        }
                    samples[category].append(sample_entry)

            next_cursor = page.next_cursor
            if not next_cursor:
                break

        percentages = {
            key: round((value / total_count * 100), 2) if total_count else 0.0
            for key, value in counts.items()
        }

        result: dict[str, Any] = {
            "total_count": total_count,
            "exact_count": True,
            "breakdown": counts,
            "percentages": percentages,
            "secondary_counts": secondary_counts,
            "time_window": {
                "received_after": received_after,
                "received_before": received_before,
            },
            "category_definitions": {
                "spam": "Messages in spam/junk folders.",
                "important": "Starred messages or messages with high-priority subject keywords.",
                "personal": "Messages from common personal mailbox domains (for example gmail.com, yahoo.com, outlook.com).",
                "automated": "Notifications/newsletters/no-reply style senders.",
                "work": "Non-spam, non-personal, non-automated messages from identifiable sender domains.",
                "other": "Messages that do not match the above rules.",
            },
        }

        if include_samples:
            result["samples"] = samples

        return result

    def _coerce_attachment_bytes(self, payload: Any) -> bytes:
        """Normalize attachment download payloads from different SDK return types."""
        if payload is None:
            raise TypeError("Attachment download returned None")

        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, bytearray):
            return bytes(payload)
        if isinstance(payload, memoryview):
            return payload.tobytes()

        # Common HTTP response objects (requests/httpx style)
        content = getattr(payload, "content", None)
        if isinstance(content, (bytes, bytearray, memoryview)):
            return bytes(content)

        # Some SDK wrappers return `.data`
        data = getattr(payload, "data", None)
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)

        # File-like objects
        read_fn = getattr(payload, "read", None)
        if callable(read_fn):
            read_data = read_fn()
            if isinstance(read_data, (bytes, bytearray, memoryview)):
                return bytes(read_data)

        # Iterables for chunked payloads
        iter_content_fn = getattr(payload, "iter_content", None)
        if callable(iter_content_fn):
            chunks = [chunk for chunk in iter_content_fn(chunk_size=65536) if chunk]
            if chunks:
                return b"".join(
                    chunk if isinstance(chunk, (bytes, bytearray)) else bytes(chunk)
                    for chunk in chunks
                )

        iter_bytes_fn = getattr(payload, "iter_bytes", None)
        if callable(iter_bytes_fn):
            chunks = [chunk for chunk in iter_bytes_fn() if chunk]
            if chunks:
                return b"".join(
                    chunk if isinstance(chunk, (bytes, bytearray)) else bytes(chunk)
                    for chunk in chunks
                )

        raise TypeError(
            f"Unsupported attachment payload type: {type(payload).__name__}"
        )

    async def get_attachment_metadata(self, message_id: str, attachment_id: str) -> dict:
        """Get attachment metadata."""
        logger.info(f"Getting attachment metadata for attachment_id={attachment_id}")
        attachment = await asyncio.to_thread(
            lambda: self.client.attachments.find(
                self.grant_id,
                attachment_id,
                query_params={"message_id": message_id},
            )
        )
        logger.info("Attachment metadata retrieved")
        return {
            "id": attachment.data.id,
            "filename": attachment.data.filename,
            "content_type": attachment.data.content_type,
            "size": attachment.data.size,
        }

    async def download_attachment(self, message_id: str, attachment_id: str) -> tuple[bytes, str, str]:
        """Download attachment and return (data, content_type, filename)."""
        logger.info(f"Downloading attachment attachment_id={attachment_id}")
        # Get metadata first
        metadata = await self.get_attachment_metadata(message_id, attachment_id)

        # Download the attachment in a thread
        attachment_payload = await asyncio.to_thread(
            lambda: self.client.attachments.download(
                self.grant_id,
                attachment_id,
                query_params={"message_id": message_id},
            )
        )
        attachment_data = self._coerce_attachment_bytes(attachment_payload)
        logger.info(
            "Attachment payload normalized: "
            f"payload_type={type(attachment_payload).__name__}, bytes={len(attachment_data)}"
        )
        logger.info("Attachment downloaded")

        return (
            attachment_data,
            metadata["content_type"],
            metadata["filename"],
        )

    async def send_reply(
        self,
        reply_to_message_id: str,
        body: str,
        send_immediately: bool = False,
    ) -> dict:
        """Create a reply to an email."""
        logger.info(f"Sending reply to message_id={reply_to_message_id}, send_immediately={send_immediately}")
        # Get the original message in a thread
        original_response = await asyncio.to_thread(
            lambda: self.client.messages.find(
                self.grant_id,
                reply_to_message_id,
            )
        )
        original = original_response.data

        # Build reply - handle both dict and object responses
        if isinstance(original, dict):
            from_ = original.get("from", [])
            subject = original.get("subject", "")
        else:
            from_ = original.from_ or []
            subject = original.subject or ""

        if from_:
            first_from = from_[0]
            if isinstance(first_from, dict):
                reply_to = first_from.get("email")
            else:
                reply_to = getattr(first_from, "email", None)
        else:
            reply_to = None

        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        draft_params = {
            "subject": subject,
            "body": body,
            "to": [{"email": reply_to}] if reply_to else [],
            "reply_to_message_id": reply_to_message_id,
        }

        if send_immediately:
            # Send directly in a thread
            result = await asyncio.to_thread(
                lambda: self.client.messages.send(
                    self.grant_id,
                    request_body=draft_params,
                )
            )
            logger.info(f"Email sent: {result.data.id}")
            return {"status": "sent", "message_id": result.data.id}
        else:
            # Create draft in a thread
            result = await asyncio.to_thread(
                lambda: self.client.drafts.create(
                    self.grant_id,
                    request_body=draft_params,
                )
            )
            logger.info(f"Draft created: {result.data.id}")
            return {"status": "draft_created", "draft_id": result.data.id}

    async def mark_as_read(self, message_id: str) -> dict:
        """Mark an email as read."""
        logger.info(f"Marking message as read: {message_id}")
        await asyncio.to_thread(
            lambda: self.client.messages.update(
                self.grant_id,
                message_id,
                request_body={"unread": False},
            )
        )
        logger.info("Message marked as read")
        return {"status": "marked_as_read", "message_id": message_id}

    def _format_message(self, msg: Message, include_body: bool = False) -> dict:
        """Format a Nylas message into a clean dict."""
        # Helper to extract name/email from either dict or object
        def format_participant(p):
            if isinstance(p, dict):
                return {"name": p.get("name", ""), "email": p.get("email", "")}
            return {"name": getattr(p, "name", ""), "email": getattr(p, "email", "")}

        def format_attachment(a):
            if isinstance(a, dict):
                return {
                    "id": a.get("id"),
                    "filename": a.get("filename"),
                    "content_type": a.get("content_type"),
                    "size": a.get("size"),
                }
            return {
                "id": getattr(a, "id", None),
                "filename": getattr(a, "filename", None),
                "content_type": getattr(a, "content_type", None),
                "size": getattr(a, "size", None),
            }

        # Handle msg being either dict or object
        if isinstance(msg, dict):
            msg_id = msg.get("id")
            subject = msg.get("subject")
            from_ = msg.get("from", []) or []
            to = msg.get("to", []) or []
            date = msg.get("date")
            unread = msg.get("unread")
            snippet = msg.get("snippet")
            thread_id = msg.get("thread_id")
            attachments = msg.get("attachments", []) or []
            body = msg.get("body")
        else:
            msg_id = msg.id
            subject = msg.subject
            from_ = msg.from_ or []
            to = msg.to or []
            date = msg.date
            unread = msg.unread
            snippet = msg.snippet
            thread_id = msg.thread_id
            attachments = msg.attachments or []
            body = getattr(msg, "body", None)

        result = {
            "id": msg_id,
            "subject": subject,
            "from": [format_participant(f) for f in from_],
            "to": [format_participant(t) for t in to],
            "date": date,
            "unread": unread,
            "snippet": snippet,
            "thread_id": thread_id,
            "attachments": [format_attachment(a) for a in attachments],
        }

        if include_body:
            result["body"] = body

        return result


# Singleton instance
_nylas_service: Optional[NylasService] = None
_nylas_service_config: Optional[tuple[str, str]] = None
_nylas_service_lock = asyncio.Lock()


async def get_nylas_service() -> NylasService:
    """Return a cached Nylas service for active profile credentials."""
    from app.services.profile_service import ProfileService

    credentials = await ProfileService.resolve_credentials()
    api_key = (credentials.get("nylas_api_key") or "").strip()
    grant_id = (credentials.get("nylas_grant_id") or "").strip()

    if not api_key or not grant_id:
        raise RuntimeError(
            "Missing Nylas credentials. Open Settings and set NYLAS_API_KEY and NYLAS_GRANT_ID."
        )

    config_key = (api_key, grant_id)

    global _nylas_service, _nylas_service_config
    async with _nylas_service_lock:
        if _nylas_service is None or _nylas_service_config != config_key:
            _nylas_service = NylasService(api_key=api_key, grant_id=grant_id)
            _nylas_service_config = config_key
        return _nylas_service
