import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.models.check_result import CheckResult
from app.models.fact import Fact
from app.models.notification import Notification, NotificationType
from app.models.topic import Topic, TopicStatus
from app.services.fact_comparer import find_new_facts
from app.services.notification import send_new_facts_notification


logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _tavily_search(query: str, start_date: str | None = None) -> list[dict]:
    payload: dict = {
        "query": query,
        "max_results": settings.MAX_SEARCH_RESULTS_PER_TOPIC,
        "search_depth": "basic",
    }
    if start_date is not None:
        payload["start_date"] = start_date
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            "https://api.tavily.com/search",
            json=payload,
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
        )
        response.raise_for_status()
        return response.json().get("results", [])


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _tavily_extract(urls: list[str]) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            "https://api.tavily.com/extract",
            json={"urls": urls},
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
        )
        response.raise_for_status()
        return response.json().get("results", [])


async def _filter_relevant_results(
    topic_title: str, topic_description: str, search_results: list[dict]
) -> list[dict]:
    """Use AI to filter out irrelevant search results before deep analysis."""
    prompt = _load_prompt("analyze_results")
    results_text = json.dumps(
        [{"url": r.get("url"), "title": r.get("title"), "snippet": r.get("content", "")[:300]} for r in search_results]
    )
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"TOPIC: {topic_title}\n"
                    f"DESCRIPTION: {topic_description}\n\n"
                    f"SEARCH RESULTS:\n{results_text}"
                ),
            },
        ],
        temperature=0.1,
    )
    data = json.loads(response.choices[0].message.content)
    relevant_urls = set(data.get("relevant_urls", []))
    return [r for r in search_results if r.get("url") in relevant_urls]


async def check_topic(topic: Topic, db: Session) -> int:
    """
    Run a full check cycle for a topic.
    Returns number of new facts found.
    """
    if topic.status != TopicStatus.active:
        return 0

    user = topic.user
    if user.credits_remaining <= 0:
        logger.warning("User %s has no credits, skipping topic %s", user.id, topic.id)
        return 0

    search_queries = topic.search_keywords[:3] if len(topic.search_keywords) > 3 else topic.search_keywords
    all_results: list[dict] = []

    reference_dt = topic.last_checked_at if topic.last_checked_at is not None else topic.created_at
    start_date = (reference_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    for query in search_queries:
        try:
            results = await _tavily_search(query, start_date=start_date)
            all_results.extend(results)
        except Exception as e:
            logger.error("Tavily search failed for query '%s': %s", query, e)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    # Filter out URLs we already know about
    known_urls = {f.source_url for f in topic.facts}
    unique_results = [r for r in unique_results if r.get("url") not in known_urls]

    if not unique_results:
        _save_check_result(topic, db, search_queries, 0, 0)
        _advance_next_check(topic, db)
        return 0

    # Filter relevant results via AI
    try:
        relevant_results = await _filter_relevant_results(topic.title, topic.description, unique_results)
    except Exception as e:
        logger.error("Relevance filtering failed: %s", e)
        relevant_results = unique_results[:5]

    if not relevant_results:
        _save_check_result(topic, db, search_queries, len(unique_results), 0)
        _advance_next_check(topic, db)
        return 0

    # Extract full content for relevant results
    try:
        extracted = await _tavily_extract([r["url"] for r in relevant_results])
    except Exception as e:
        logger.error("Tavily extract failed: %s", e)
        extracted = []

    content_map = {item["url"]: item.get("raw_content", "") for item in extracted}
    known_facts_text = [f.content for f in topic.facts]

    new_facts_found: list[Fact] = []

    for result in relevant_results:
        url = result.get("url", "")
        content = content_map.get(url, result.get("content", ""))
        if not content:
            continue

        try:
            new_facts = await find_new_facts(
                topic_title=topic.title,
                topic_description=topic.description,
                known_facts=known_facts_text,
                new_article_url=url,
                new_article_content=content,
                new_article_title=result.get("title", ""),
            )
        except Exception as e:
            logger.error("Fact comparison failed for %s: %s", url, e)
            continue

        for fact_data in new_facts:
            fact = Fact(
                topic_id=topic.id,
                content=fact_data.get("content", ""),
                source_url=url,
                source_title=result.get("title", ""),
                is_initial=False,
            )
            db.add(fact)
            new_facts_found.append(fact)
            # Update known facts for subsequent comparisons
            known_facts_text.append(fact_data.get("content", ""))

    if new_facts_found:
        topic.has_update = True
        notification = Notification(
            user_id=user.id,
            topic_id=topic.id,
            type=NotificationType.new_facts,
        )
        db.add(notification)

    _save_check_result(topic, db, search_queries, len(unique_results), len(new_facts_found))
    _advance_next_check(topic, db)

    user.credits_remaining = max(0, user.credits_remaining - 1)
    db.commit()

    if new_facts_found:
        try:
            await send_new_facts_notification(
                email=user.email,
                topic_title=topic.title,
                new_facts_count=len(new_facts_found),
                topic_id=str(topic.id),
                language=user.language,
            )
        except Exception as e:
            logger.error("Failed to send email notification: %s", e)

    return len(new_facts_found)


def _save_check_result(
    topic: Topic, db: Session, queries: list[str], sources_found: int, new_facts: int
) -> None:
    result = CheckResult(
        topic_id=topic.id,
        search_queries_used=queries,
        sources_found=sources_found,
        new_facts_count=new_facts,
        credits_used=1,
    )
    db.add(result)
    topic.last_checked_at = datetime.now(timezone.utc)


def _advance_next_check(topic: Topic, db: Session) -> None:
    topic.next_check_at = datetime.now(timezone.utc) + timedelta(days=topic.check_interval_days)
