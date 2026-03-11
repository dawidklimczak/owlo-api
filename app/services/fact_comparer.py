import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def find_new_facts(
    topic_title: str,
    topic_description: str,
    known_facts: list[str],
    new_article_url: str,
    new_article_content: str,
    new_article_title: str,
) -> list[dict[str, Any]]:
    """
    Compare new article content against known facts.
    Returns list of genuinely new facts not present in known_facts.
    """
    prompt = _load_prompt("compare_facts")
    known_facts_formatted = "\n".join(f"- {f}" for f in known_facts) if known_facts else "(none yet)"

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"TOPIC: {topic_title}\n"
                    f"TOPIC DESCRIPTION: {topic_description}\n\n"
                    f"KNOWN FACTS:\n{known_facts_formatted}\n\n"
                    f"NEW ARTICLE URL: {new_article_url}\n"
                    f"NEW ARTICLE TITLE: {new_article_title}\n"
                    f"NEW ARTICLE CONTENT:\n{new_article_content[:4000]}"
                ),
            },
        ],
        temperature=0.1,
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("new_facts", [])
