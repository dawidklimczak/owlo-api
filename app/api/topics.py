import logging
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.fact import Fact
from app.models.topic import Topic, TopicStatus
from app.models.user import User
from app.schemas.topic import (
    TopicAnalyzeRequest,
    TopicAnalyzeResponse,
    TopicConfirmRequest,
    TopicDetailResponse,
    TopicManualRequest,
    TopicProposal,
    TopicResponse,
    TopicUpdateRequest,
)
from app.services.article_analyzer import (
    extract_topic_proposals,
    extract_topic_proposals_from_query,
    fetch_article_content,
    fetch_query_content,
)
from app.services.topic_checker import check_topic


router = APIRouter()

_proposals_cache: dict[tuple, dict] = {}
CACHE_TTL_MINUTES = 10


@router.post("", response_model=TopicAnalyzeResponse)
async def analyze_url(
    body: TopicAnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """Fetch article and return topic proposals (with keywords + facts) for user to choose from."""
    try:
        content = await fetch_article_content(body.url)
    except Exception as e:
        logger.error(f"fetch_article_content failed for {body.url}: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Failed to fetch article content",
            headers={"X-Error-Code": "FETCH_FAILED"},
        )

    try:
        result = await extract_topic_proposals(body.url, content)
    except Exception as e:
        logger.error(f"extract_topic_proposals failed for {body.url}: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze article",
            headers={"X-Error-Code": "ANALYSIS_FAILED"},
        )

    proposals = [TopicProposal(**p) for p in result.get("proposals", [])]
    source_language = result.get("source_language", "en")

    cache_key = (current_user.id, body.url)
    _proposals_cache[cache_key] = {
        "proposals": proposals,
        "source_language": source_language,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=CACHE_TTL_MINUTES),
    }

    return TopicAnalyzeResponse(proposals=proposals, source_language=source_language)


@router.post("/manual", response_model=TopicAnalyzeResponse)
async def analyze_query(
    body: TopicManualRequest,
    current_user: User = Depends(get_current_user),
):
    """Search for a user query and return topic proposals (with keywords + facts) for user to choose from."""
    try:
        extracted_results = await fetch_query_content(body.query)
    except Exception as e:
        logger.error(f"fetch_query_content failed for '{body.query}': {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Failed to fetch content for query",
            headers={"X-Error-Code": "FETCH_FAILED"},
        )

    try:
        result = await extract_topic_proposals_from_query(body.query, extracted_results)
    except Exception as e:
        logger.error(f"extract_topic_proposals_from_query failed for '{body.query}': {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze query",
            headers={"X-Error-Code": "ANALYSIS_FAILED"},
        )

    proposals = [TopicProposal(**p) for p in result.get("proposals", [])]
    source_language = result.get("source_language", "en")

    cache_key = (current_user.id, body.query)
    _proposals_cache[cache_key] = {
        "proposals": proposals,
        "source_language": source_language,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=CACHE_TTL_MINUTES),
    }

    return TopicAnalyzeResponse(proposals=proposals, source_language=source_language)


@router.post("/confirm", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def confirm_topic(
    body: TopicConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm a cached proposal by index and save Topic + Facts."""
    cache_key = (current_user.id, body.source)
    cached = _proposals_cache.get(cache_key)

    if not cached or cached["expires_at"] < datetime.now(timezone.utc):
        _proposals_cache.pop(cache_key, None)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Proposals expired or not found. Please analyze again.",
            headers={"X-Error-Code": "PROPOSALS_EXPIRED"},
        )

    proposals: list[TopicProposal] = cached["proposals"]
    if body.proposal_index < 0 or body.proposal_index >= len(proposals):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid proposal index. Must be 0–{len(proposals) - 1}.",
            headers={"X-Error-Code": "INVALID_PROPOSAL_INDEX"},
        )

    proposal = proposals[body.proposal_index]
    source_language = cached["source_language"]
    check_interval = body.check_interval_days or current_user.default_check_interval_days

    topic = Topic(
        user_id=current_user.id,
        source_url=body.source,
        title=proposal.title,
        description=proposal.description,
        search_keywords=proposal.search_keywords,
        check_interval_days=check_interval,
        source_language=source_language,
        next_check_at=datetime.now(timezone.utc) + timedelta(days=check_interval),
        status=TopicStatus.active,
    )
    db.add(topic)
    db.flush()

    for fact_content in proposal.facts:
        fact = Fact(
            topic_id=topic.id,
            content=fact_content,
            source_url=body.source,
            source_title="Initial source",
            is_initial=True,
        )
        db.add(fact)

    try:
        db.commit()
        db.refresh(topic)
    except Exception as e:
        logger.error(f"confirm_topic DB commit failed: {e}\n{traceback.format_exc()}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save topic",
            headers={"X-Error-Code": "DB_ERROR"},
        )
    _proposals_cache.pop(cache_key, None)
    return topic


@router.get("", response_model=list[TopicResponse])
async def list_topics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Topic)
        .filter(Topic.user_id == current_user.id)
        .order_by(Topic.created_at.desc())
        .all()
    )


@router.get("/{topic_id}", response_model=TopicDetailResponse)
async def get_topic(
    topic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_user_topic(topic_id, current_user.id, db)
    return topic


@router.patch("/{topic_id}", response_model=TopicResponse)
async def update_topic(
    topic_id: uuid.UUID,
    body: TopicUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_user_topic(topic_id, current_user.id, db)

    if body.check_interval_days is not None:
        topic.check_interval_days = body.check_interval_days
    if body.status is not None:
        topic.status = body.status

    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_user_topic(topic_id, current_user.id, db)
    db.delete(topic)
    db.commit()


@router.post("/{topic_id}/check", response_model=dict)
async def force_check_topic(
    topic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.credits_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No credits remaining",
            headers={"X-Error-Code": "NO_CREDITS"},
        )

    topic = _get_user_topic(topic_id, current_user.id, db)

    new_facts_count = await check_topic(topic, db)
    return {"new_facts_count": new_facts_count}


@router.post("/{topic_id}/mark-read", response_model=TopicResponse)
async def mark_topic_read(
    topic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_user_topic(topic_id, current_user.id, db)
    topic.has_update = False
    db.commit()
    db.refresh(topic)
    return topic


def _get_user_topic(topic_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> Topic:
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == user_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic
