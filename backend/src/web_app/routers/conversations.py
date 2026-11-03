"""Conversations and the chat stream (CH-01 to CH-07, OR-05).

A conversation's id is its LangGraph thread id: the checkpointer keeps the messages and
context, the `conversations` table keeps the list. Sending a message answers with a
Server-Sent Events stream (see src/workflow/streaming.py for the event order).

Ownership and the message length are checked in `start_turn`, a dependency, so a bad
request still gets a normal JSON error; once the stream opens, failures arrive as an
`error` event instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.sse import EventSourceResponse

from src.core.errors import ValidationFailed
from src.data.db.base import new_id
from src.data.db.models import Conversation
from src.data.db.repositories.conversation_repository import ConversationRepository
from src.utils.images import decode_image
from src.web_app.auth.current_user import CurrentUserDep
from src.web_app.dependencies import ContainerDep, DbDep
from src.web_app.schemas.chat import (
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationOut,
    MessageCreate,
)
from src.workflow.screenshot import ScreenshotInput
from src.workflow.state import UserContext
from src.workflow.streaming import ChatEvent, history, stream_turn

router = APIRouter(prefix="/conversations", tags=["chat"])

SCREENSHOT_QUESTION = "Analyze the portfolio in this screenshot."


def _out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _thread(conversation_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": conversation_id}}


@router.get("", response_model=ConversationList, summary="Your conversations, newest first")
def list_conversations(user: CurrentUserDep, db: DbDep) -> ConversationList:
    rows = ConversationRepository(db).list_for(user.id)
    return ConversationList(conversations=[_out(c) for c in rows])


@router.post(
    "",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
def create_conversation(
    body: ConversationCreate, user: CurrentUserDep, db: DbDep
) -> ConversationOut:
    conversation = ConversationRepository(db).create(user.id, body.title)
    db.commit()
    return _out(conversation)


@router.get(
    "/{conversation_id}", response_model=ConversationDetail, summary="A conversation's messages"
)
async def get_conversation(
    conversation_id: str, user: CurrentUserDep, db: DbDep, container: ContainerDep
) -> ConversationDetail:
    conversation = ConversationRepository(db).get_owned(user.id, conversation_id)
    snapshot = await container.workflow.aget_state(_thread(conversation.id))
    messages = snapshot.values.get("messages", []) if snapshot else []
    return ConversationDetail(conversation=_out(conversation), messages=history(messages))


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and its memory",
)
async def delete_conversation(
    conversation_id: str, user: CurrentUserDep, db: DbDep, container: ContainerDep
) -> Response:
    repo = ConversationRepository(db)
    repo.delete(repo.get_owned(user.id, conversation_id))
    db.commit()
    if container.checkpointer is not None:
        await container.checkpointer.adelete_thread(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Chat stream ---------------------------------------------------------------


@dataclass(frozen=True)
class ChatTurn:
    conversation_id: str
    user_id: str
    text: str
    image: ScreenshotInput | None = None


def start_turn(
    conversation_id: str, body: MessageCreate, user: CurrentUserDep, container: ContainerDep
) -> ChatTurn:
    """Validate the turn before the stream opens; also names and bumps the conversation."""
    workflow = container.settings.workflow
    image: ScreenshotInput | None = None
    if body.image is not None:
        try:
            data = decode_image(body.image.data, body.image.media_type, workflow.max_image_bytes)
        except ValueError as error:
            raise ValidationFailed(str(error)) from None
        image = ScreenshotInput(media_type=body.image.media_type, data=data)
    text = body.content.strip() or (SCREENSHOT_QUESTION if image else "")
    if not text:
        raise ValidationFailed("Type a question to get started.")
    limit = workflow.max_message_chars
    if len(text) > limit:
        raise ValidationFailed(f"Keep messages under {limit} characters.")
    # Its own short session: a request-scoped one would stay open for the whole stream.
    with container.session_factory() as db:
        repo = ConversationRepository(db)
        repo.record_turn(repo.get_owned(user.id, conversation_id), text)
        db.commit()
    return ChatTurn(conversation_id=conversation_id, user_id=user.id, text=text, image=image)


@router.post(
    "/{conversation_id}/messages",
    response_class=EventSourceResponse,
    summary="Send a message; the answer streams back as Server-Sent Events",
)
async def send_message(
    turn: Annotated[ChatTurn, Depends(start_turn)], container: ContainerDep
) -> AsyncIterator[ChatEvent]:
    async for event in stream_turn(
        container.workflow,
        thread_id=turn.conversation_id,
        user=UserContext(user_id=turn.user_id),
        text=turn.text,
        turn_id=new_id(),
        image=turn.image,
    ):
        yield event
