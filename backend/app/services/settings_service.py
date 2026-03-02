import json
from sqlalchemy import select
from typing import Optional

from app.services.database import AsyncSessionLocal
from app.models import UserSettings


class SettingsService:
    """Service for managing user settings."""

    # Default settings ID (single user for now)
    DEFAULT_ID = "default"

    @staticmethod
    async def get_settings() -> UserSettings:
        """Get user settings, creating defaults if not exist."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.id == SettingsService.DEFAULT_ID)
            )
            settings = result.scalar_one_or_none()

            if not settings:
                # Create default settings
                settings = UserSettings(id=SettingsService.DEFAULT_ID)
                session.add(settings)
                await session.commit()
                await session.refresh(settings)

            return settings

    @staticmethod
    async def update_settings(**kwargs) -> UserSettings:
        """Update user settings."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.id == SettingsService.DEFAULT_ID)
            )
            settings = result.scalar_one_or_none()

            if not settings:
                settings = UserSettings(id=SettingsService.DEFAULT_ID)
                session.add(settings)

            # Update fields
            for key, value in kwargs.items():
                if hasattr(settings, key):
                    # Handle JSON fields
                    if key in ['excluded_senders', 'excluded_folders', 'excluded_subjects']:
                        if isinstance(value, list):
                            value = json.dumps(value)
                    setattr(settings, key, value)

            await session.commit()
            await session.refresh(settings)
            return settings

    @staticmethod
    def settings_to_dict(settings: UserSettings) -> dict:
        """Convert settings to dictionary."""
        return {
            "allow_send_emails": settings.allow_send_emails,
            "require_confirmation_for_send": settings.require_confirmation_for_send,
            "allow_read_attachments": settings.allow_read_attachments,
            "allow_read_email_body": settings.allow_read_email_body,
            "allow_mark_as_read": settings.allow_mark_as_read,
            "allow_delete_emails": settings.allow_delete_emails,
            "allow_archive_emails": settings.allow_archive_emails,
            "excluded_senders": json.loads(settings.excluded_senders or "[]"),
            "excluded_folders": json.loads(settings.excluded_folders or "[]"),
            "excluded_subjects": json.loads(settings.excluded_subjects or "[]"),
            "hide_sensitive_content": settings.hide_sensitive_content,
            "max_emails_per_search": int(settings.max_emails_per_search or "25"),
        }

    @staticmethod
    async def is_action_allowed(action: str) -> bool:
        """Check if a specific action is allowed by current settings."""
        settings = await SettingsService.get_settings()

        action_map = {
            "send_email": settings.allow_send_emails,
            "read_attachment": settings.allow_read_attachments,
            "read_body": settings.allow_read_email_body,
            "mark_as_read": settings.allow_mark_as_read,
            "delete_email": settings.allow_delete_emails,
            "archive_email": settings.allow_archive_emails,
        }

        return action_map.get(action, True)

    @staticmethod
    async def is_sender_excluded(sender_email: str) -> bool:
        """Check if a sender is in the exclusion list."""
        settings = await SettingsService.get_settings()
        excluded = json.loads(settings.excluded_senders or "[]")
        return sender_email.lower() in [e.lower() for e in excluded]

    @staticmethod
    async def is_folder_excluded(folder_name: str) -> bool:
        """Check if a folder is in the exclusion list."""
        settings = await SettingsService.get_settings()
        excluded = json.loads(settings.excluded_folders or "[]")
        return folder_name.lower() in [f.lower() for f in excluded]
