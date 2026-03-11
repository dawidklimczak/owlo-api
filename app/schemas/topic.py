import uuid
from datetime import datetime
from pydantic import BaseModel, HttpUrl
from app.models.topic import TopicStatus


class TopicProposal(BaseModel):
    title: str
    description: str


class TopicAnalyzeRequest(BaseModel):
    url: str


class TopicAnalyzeResponse(BaseModel):
    proposals: list[TopicProposal]
    source_language: str
    extracted_content_preview: str


class TopicConfirmRequest(BaseModel):
    url: str
    title: str
    description: str
    source_language: str
    check_interval_days: int | None = None


class FactResponse(BaseModel):
    id: uuid.UUID
    content: str
    source_url: str
    source_title: str
    discovered_at: datetime
    is_initial: bool

    model_config = {"from_attributes": True}


class CheckResultResponse(BaseModel):
    id: uuid.UUID
    checked_at: datetime
    sources_found: int
    new_facts_count: int
    credits_used: int

    model_config = {"from_attributes": True}


class TopicResponse(BaseModel):
    id: uuid.UUID
    source_url: str
    title: str
    description: str
    search_keywords: list[str]
    check_interval_days: int
    next_check_at: datetime | None
    last_checked_at: datetime | None
    has_update: bool
    status: TopicStatus
    source_language: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicDetailResponse(TopicResponse):
    facts: list[FactResponse]
    check_results: list[CheckResultResponse]


class TopicUpdateRequest(BaseModel):
    check_interval_days: int | None = None
    status: TopicStatus | None = None
