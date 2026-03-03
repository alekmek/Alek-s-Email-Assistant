from typing import Optional

from sqlalchemy import select

from app.config import get_settings
from app.models import UserProfile
from app.services.database import AsyncSessionLocal


class ProfileService:
    """Service for user profile and provider credential management."""

    DEFAULT_ID = "default"
    CREDENTIAL_FIELDS = (
        "anthropic_api_key",
        "nylas_api_key",
        "nylas_client_id",
        "nylas_client_secret",
        "nylas_grant_id",
        "deepgram_api_key",
        "cartesia_api_key",
    )

    @staticmethod
    def _normalize_secret(value: Optional[str]) -> str:
        if value is None:
            return ""
        return value.strip()

    @staticmethod
    def _mask_secret(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    @staticmethod
    async def get_profile() -> UserProfile:
        """Get profile, creating default profile row if it doesn't exist."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.id == ProfileService.DEFAULT_ID)
            )
            profile = result.scalar_one_or_none()

            if not profile:
                profile = UserProfile(id=ProfileService.DEFAULT_ID)
                session.add(profile)
                await session.commit()
                await session.refresh(profile)

            return profile

    @staticmethod
    async def update_profile(
        display_name: Optional[str] = None,
        **credential_updates,
    ) -> UserProfile:
        """Update profile display name and/or credentials."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.id == ProfileService.DEFAULT_ID)
            )
            profile = result.scalar_one_or_none()

            if not profile:
                profile = UserProfile(id=ProfileService.DEFAULT_ID)
                session.add(profile)

            if display_name is not None:
                normalized_name = display_name.strip()
                if normalized_name:
                    profile.display_name = normalized_name

            for key, value in credential_updates.items():
                if key in ProfileService.CREDENTIAL_FIELDS and value is not None:
                    setattr(profile, key, ProfileService._normalize_secret(value))

            await session.commit()
            await session.refresh(profile)
            return profile

    @staticmethod
    def _env_credentials() -> dict:
        env = get_settings()
        return {
            "anthropic_api_key": env.anthropic_api_key,
            "nylas_api_key": env.nylas_api_key,
            "nylas_client_id": env.nylas_client_id,
            "nylas_client_secret": env.nylas_client_secret,
            "nylas_grant_id": env.nylas_grant_id or env.nylas_sid,
            "deepgram_api_key": env.deepgram_api_key,
            "cartesia_api_key": env.cartesia_api_key,
        }

    @staticmethod
    async def resolve_credentials() -> dict:
        """Resolve runtime credentials from profile first, then environment fallback."""
        profile = await ProfileService.get_profile()
        env_values = ProfileService._env_credentials()

        resolved = {}
        for field in ProfileService.CREDENTIAL_FIELDS:
            profile_value = ProfileService._normalize_secret(getattr(profile, field, ""))
            resolved[field] = profile_value or env_values.get(field, "")
        return resolved

    @staticmethod
    async def profile_to_dict(profile: Optional[UserProfile] = None) -> dict:
        """Return profile metadata plus credential status (without raw secret values)."""
        if profile is None:
            profile = await ProfileService.get_profile()

        env_values = ProfileService._env_credentials()
        credentials = {}

        for field in ProfileService.CREDENTIAL_FIELDS:
            profile_value = ProfileService._normalize_secret(getattr(profile, field, ""))
            env_value = ProfileService._normalize_secret(env_values.get(field, ""))
            effective_value = profile_value or env_value

            if profile_value:
                source = "profile"
            elif env_value:
                source = "env"
            else:
                source = "missing"

            credentials[field] = {
                "configured": bool(effective_value),
                "source": source,
                "preview": ProfileService._mask_secret(effective_value),
            }

        return {
            "id": profile.id,
            "display_name": profile.display_name,
            "credentials": credentials,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }
