import json
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.schemas.topic import TopicProposal


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


async def fetch_article_content(url: str) -> str:
    """Fetch article content using Tavily Extract, fallback to httpx + BeautifulSoup."""
    try:
        return await _fetch_via_tavily(url)
    except Exception:
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_search_keywords(title: str, description: str, source_language: str) -> list[str]:
    """Generate search keywords for topic monitoring."""
    prompt = _load_prompt("generate_keywords")
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"TOPIC TITLE: {title}\n"
                    f"TOPIC DESCRIPTION: {description}\n"
                    f"SOURCE LANGUAGE: {source_language}"
                ),
            },
        ],
        temperature=0.3,
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("keywords", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def extract_initial_facts(url: str, title: str, content: str) -> list[dict[str, str]]:
    """Extract key facts from the original article."""
    prompt = _load_prompt("compare_facts")
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"TASK: Extract all key facts from this article.\n\n"
                    f"TOPIC: {title}\n"
                    f"KNOWN FACTS: []\n\n"
                    f"NEW ARTICLE URL: {url}\n"
                    f"NEW ARTICLE CONTENT:\n{content[:6000]}"
                ),
            },
        ],
        temperature=0.1,
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("new_facts", [])
