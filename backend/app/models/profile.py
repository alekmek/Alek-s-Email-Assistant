from sqlalchemy import Column, String, Text

from .base import Base, TimestampMixin


class UserProfile(Base, TimestampMixin):
    """Single-user profile and provider credentials."""

    __tablename__ = "user_profiles"

    id = Column(String(36), primary_key=True, nullable=False)
    display_name = Column(String(120), default="User", nullable=False)

    # Provider credentials (empty means fallback to environment variable).
    anthropic_api_key = Column(Text, default="", nullable=False)
    nylas_api_key = Column(Text, default="", nullable=False)
    nylas_client_id = Column(Text, default="", nullable=False)
    nylas_client_secret = Column(Text, default="", nullable=False)
    nylas_grant_id = Column(Text, default="", nullable=False)
    deepgram_api_key = Column(Text, default="", nullable=False)
    cartesia_api_key = Column(Text, default="", nullable=False)
