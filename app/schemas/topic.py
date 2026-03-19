import uuid
from datetime import datetime
from pydantic import BaseModel, HttpUrl, field_validator
from app.models.topic import TopicStatus


class TopicProposal(BaseModel):
    title: str
    description: str
    search_keywords: list[str]
    facts: list[str]


class TopicAnalyzeRequest(BaseModel):
    url: str


class TopicManualRequest(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def query_must_not_be_url(cls, v: str) -> str:
        if v.startswith("http://") or v.startswith("https://"):
            raise ValueError("This looks like a URL. Please use the /topics endpoint instead.")
        if len(v) < 3:
            raise ValueError("Query must be at least 3 characters.")
        if len(v) > 200:
            raise ValueError("Query must be at most 200 characters.")
        return v


class TopicAnalyzeResponse(BaseModel):
    proposals: list[TopicProposal]
    source_language: str


class TopicConfirmRequest(BaseModel):
    source: str
    proposal_index: int = 0
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
