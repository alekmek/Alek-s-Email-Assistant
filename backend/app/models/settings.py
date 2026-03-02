from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.dialects.sqlite import JSON
import uuid

from .base import Base, TimestampMixin


def generate_uuid():
    return str(uuid.uuid4())


class UserSettings(Base, TimestampMixin):
    """User safety and preference settings for the AI assistant."""
    __tablename__ = "user_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    # Email sending permissions
    allow_send_emails = Column(Boolean, default=False, nullable=False)
    require_confirmation_for_send = Column(Boolean, default=True, nullable=False)

    # Reading permissions
    allow_read_attachments = Column(Boolean, default=True, nullable=False)
    allow_read_email_body = Column(Boolean, default=True, nullable=False)

    # Modification permissions
    allow_mark_as_read = Column(Boolean, default=True, nullable=False)
    allow_delete_emails = Column(Boolean, default=False, nullable=False)
    allow_archive_emails = Column(Boolean, default=True, nullable=False)

    # Exclusion lists (stored as JSON arrays)
    excluded_senders = Column(Text, default="[]", nullable=False)  # JSON array of email addresses
    excluded_folders = Column(Text, default="[]", nullable=False)  # JSON array of folder names
    excluded_subjects = Column(Text, default="[]", nullable=False)  # JSON array of subject keywords

    # Privacy settings
    hide_sensitive_content = Column(Boolean, default=True, nullable=False)  # Hide passwords, tokens, etc.
    max_emails_per_search = Column(String(10), default="25", nullable=False)
