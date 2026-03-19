import json
import logging
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


async def fetch_article_content(url: str) -> str:
    """Fetch article content using Tavily Extract, fallback to httpx + BeautifulSoup."""
    try:
        return await _fetch_via_tavily(url)
    except Exception as e:
        logger.warning(f"Tavily extract failed for {url}, falling back to httpx: {e}")
        return await _fetch_via_httpx(url)


async def _fetch_via_tavily(url: str) -> str:
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            "https://api.tavily.com/extract",
            json={"urls": [url]},
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if results:
            return results[0].get("raw_content", "")
        raise ValueError("No content extracted")


async def _fetch_via_httpx(url: str) -> str:
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        response = await http.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:8000]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def extract_topic_proposals(url: str, content: str) -> dict[str, Any]:
    """Call OpenAI to extract topic proposals from article content."""
    prompt = _load_prompt("extract_topic")
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"URL: {url}\n\nARTICLE CONTENT:\n{content[:6000]}"},
        ],
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _search_via_tavily(query: str, max_results: int = 5) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": max_results, "search_depth": "basic"},
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
        )
        response.raise_for_status()
        return response.json().get("results", [])


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _extract_via_tavily_batch(urls: list[str]) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            "https://api.tavily.com/extract",
            json={"urls": urls},
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
        )
        response.raise_for_status()
        return response.json().get("results", [])


async def fetch_query_content(query: str) -> list[dict]:
    """Search Tavily for query, extract full content from top 3 results."""
    search_results = await _search_via_tavily(query, max_results=5)
    top_urls = [r["url"] for r in search_results[:3] if r.get("url")]
    if not top_urls:
        raise ValueError("No search results found for query")
    return await _extract_via_tavily_batch(top_urls)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def extract_topic_proposals_from_query(query: str, extracted_results: list[dict]) -> dict[str, Any]:
    """Call OpenAI to extract topic proposals from a user query and search result contents."""
    prompt = _load_prompt("extract_topic_from_query")
    combined_content = "\n\n---\n\n".join(
        f"SOURCE: {r.get('url', '')}\n{r.get('raw_content', '')[:2000]}"
        for r in extracted_results
    )
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"USER QUERY: {query}\n\nSOURCE CONTENT:\n{combined_content[:6000]}"},
        ],
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content)


