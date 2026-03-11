import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
    TopicProposal,
    TopicResponse,
    TopicUpdateRequest,
)
from app.services.article_analyzer import (
    extract_initial_facts,
    extract_topic_proposals,
    fetch_article_content,
    generate_search_keywords,
)
from app.services.topic_checker import check_topic


router = APIRouter()


@router.post("/analyze", response_model=TopicAnalyzeResponse)
async def analyze_url(
    body: TopicAnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """Fetch article and return topic proposals for user to choose from."""
    try:
        content = await fetch_article_content(body.url)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Failed to fetch article content",
            headers={"X-Error-Code": "FETCH_FAILED"},
        )

    try:
        result = await extract_topic_proposals(body.url, content)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze article",
            headers={"X-Error-Code": "ANALYSIS_FAILED"},
        )

    proposals = [TopicProposal(**p) for p in result.get("proposals", [])]
    return TopicAnalyzeResponse(
        proposals=proposals,
        source_language=result.get("source_language", "en"),
        extracted_content_preview=content[:500],
    )


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def confirm_topic(
    body: TopicConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm a topic proposal and save it with initial facts."""
    check_interval = body.check_interval_days or current_user.default_check_interval_days

    try:
        content = await fetch_article_content(body.url)
        keywords = await generate_search_keywords(body.title, body.description, body.source_language)
        initial_facts_data = await extract_initial_facts(body.url, body.title, content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process topic",
            headers={"X-Error-Code": "PROCESSING_FAILED"},
        )

    topic = Topic(
        user_id=current_user.id,
        source_url=body.url,
        title=body.title,
        description=body.description,
        search_keywords=keywords,
        check_interval_days=check_interval,
        source_language=body.source_language,
        next_check_at=datetime.now(timezone.utc) + timedelta(days=check_interval),
        status=TopicStatus.active,
    )
    db.add(topic)
    db.flush()

    for fact_data in initial_facts_data:
        fact = Fact(
            topic_id=topic.id,
            content=fact_data.get("content", ""),
            source_url=body.url,
            source_title=fact_data.get("source_title", "Original article"),
            is_initial=True,
        )
        db.add(fact)

    db.commit()
    db.refresh(topic)
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
