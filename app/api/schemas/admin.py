"""Request/response models for the admin corpus endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field


class DocumentOut(BaseModel):
    """One row of the admin screen's document table."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    status: str  # pending | processing | indexed | failed
    chunks_total: int
    chunks_done: int
    corpus_version: int
    error: str | None
    created_at: datetime
    indexed_at: datetime | None

    @computed_field
    @property
    def progress(self) -> float:
        """0.0–1.0, computed server-side on purpose.

        The client would otherwise divide by chunks_total and hit ZeroDivisionError (or
        render NaN%) for every document in "pending", which is the state every document
        passes through and therefore the state the progress bar is most likely to meet.
        """
        if self.chunks_total <= 0:
            return 0.0
        return min(self.chunks_done / self.chunks_total, 1.0)


class CorpusStatusOut(BaseModel):
    """Everything the admin screen polls, in one response.

    One endpoint rather than one per widget: the screen refreshes on a timer, and three
    polls per tick is three times the load for data that must agree with itself anyway.
    """

    documents: list[DocumentOut]
    total_chunks: int
    embedding_model: str
    # True while any document is pending or processing. The client uses it to decide
    # whether to keep polling — computing it here keeps that rule in one place rather than
    # duplicating the status-string list in TypeScript.
    is_ingesting: bool


class UploadAccepted(BaseModel):
    document: DocumentOut
    # False when the bytes were already indexed with the current encoder, so no background
    # work was scheduled. The UI says "déjà indexé" instead of showing a bar that will
    # never move.
    processing: bool


class AdminUserOut(BaseModel):
    """One row of the admin screen's user table.

    message_count and session_count are read-model numbers computed alongside the row
    (see list_users in admin.py), not columns on User — a running counter would be a
    second source of truth for facts the messages/refresh_tokens tables already hold, and
    one more thing that could drift from what actually happened.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    # Total user-authored messages ever sent, not today's count: this is an activity
    # figure for the admin screen, not the same number the daily rate limit checks.
    message_count: int
    # Active refresh tokens: not revoked, not expired. Each one is roughly one signed-in
    # device or browser, which is the closest thing this app has to a session count.
    session_count: int


class AdminUserUpdate(BaseModel):
    is_admin: bool
