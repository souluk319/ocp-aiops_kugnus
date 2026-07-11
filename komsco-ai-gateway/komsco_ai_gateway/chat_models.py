from typing import Any

from pydantic import BaseModel, Field


MAX_IMAGE_ATTACHMENTS = 4
MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024


class ImageAttachment(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=180)
    mimeType: str = Field(min_length=1, max_length=80)
    size: int = Field(ge=1, le=MAX_IMAGE_ATTACHMENT_BYTES)
    data: str = Field(min_length=1)


class ChatContextMessage(BaseModel):
    role: str = Field(min_length=1, max_length=20)
    content: str = Field(default="", max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    pageContext: dict[str, Any] | None = None
    conversationId: str | None = None
    language: str | None = Field(default=None, max_length=16)
    runId: str | None = None
    recentMessages: list[ChatContextMessage] = Field(default_factory=list, max_length=8)
    attachments: list[ImageAttachment] = Field(default_factory=list, max_length=MAX_IMAGE_ATTACHMENTS)
