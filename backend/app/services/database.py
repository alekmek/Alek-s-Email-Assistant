from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete
from typing import Optional
from datetime import datetime

from app.config import get_settings
from app.models import Base, Conversation, Message, UserSettings


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with AsyncSessionLocal() as session:
        yield session


class ConversationService:
    """Service for managing conversations and messages."""

    @staticmethod
    async def create_conversation(title: Optional[str] = None) -> Conversation:
        """Create a new conversation."""
        async with AsyncSessionLocal() as session:
            conversation = Conversation(title=title)
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            return conversation

    @staticmethod
    async def get_conversation(conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_conversations(limit: int = 50, offset: int = 0) -> list[Conversation]:
        """List all conversations, most recent first."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_conversation_title(conversation_id: str, title: str) -> Optional[Conversation]:
        """Update a conversation's title."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                conversation.title = title
                conversation.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(conversation)
            return conversation

    @staticmethod
    async def delete_conversation(conversation_id: str) -> bool:
        """Delete a conversation and all its messages."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                await session.delete(conversation)
                await session.commit()
                return True
            return False

    @staticmethod
    async def add_message(
        conversation_id: str,
        role: str,
        content: str
    ) -> Optional[Message]:
        """Add a message to a conversation."""
        async with AsyncSessionLocal() as session:
            # Verify conversation exists
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if not conversation:
                return None

            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=content
            )
            session.add(message)

            # Update conversation's updated_at
            conversation.updated_at = datetime.utcnow()

            # Auto-generate title from first user message if not set
            if conversation.title is None and role == "user":
                # Take first 50 chars of first user message as title
                conversation.title = content[:50] + ("..." if len(content) > 50 else "")

            await session.commit()
            await session.refresh(message)
            return message

    @staticmethod
    async def get_messages(conversation_id: str) -> list[Message]:
        """Get all messages for a conversation."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            return list(result.scalars().all())
