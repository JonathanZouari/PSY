import json
import os
from functools import lru_cache

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "topics": {"type": "array", "items": {"type": "string"}},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["task", "owner", "due"],
                "additionalProperties": False,
            },
        },
        "sentiment": {
            "type": "string",
            "enum": ["positive", "negative", "neutral", "mixed"],
        },
        "sentiment_explanation": {"type": "string"},
        "entities": {
            "type": "object",
            "properties": {
                "people": {"type": "array", "items": {"type": "string"}},
                "organizations": {"type": "array", "items": {"type": "string"}},
                "dates": {"type": "array", "items": {"type": "string"}},
                "places": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["people", "organizations", "dates", "places"],
            "additionalProperties": False,
        },
    },
    "required": [
        "summary",
        "key_points",
        "topics",
        "tasks",
        "sentiment",
        "sentiment_explanation",
        "entities",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """אתה מנתח שיחות מקצועי בעברית. עליך לנתח תמליל של שיחה עסקית/אישית ולחלץ:

1. **summary** — סיכום קצר וענייני (2-3 משפטים) של השיחה.
2. **key_points** — 3-5 נקודות מפתח מהשיחה.
3. **topics** — 3-6 נושאים מרכזיים שנדונו (מילים/ביטויים קצרים).
4. **tasks** — משימות פעולה שעלו בשיחה. לכל משימה: task (תיאור), owner (אחראי, אם הוזכר — אחרת "לא צוין"), due (מועד יעד, אם הוזכר — אחרת "לא צוין").
5. **sentiment** — אחד מ: "positive", "negative", "neutral", "mixed".
6. **sentiment_explanation** — משפט הסבר על הסנטימנט.
7. **entities** — ישויות בקטגוריות: people, organizations, dates, places. רשימה ריקה אם אין.

כללים חשובים:
- כל הטקסט חייב להיות בעברית.
- אם שדה לא רלוונטי, החזר רשימה ריקה (לא תכניס ערכים מומצאים).
- אל תוסיף מידע שלא נמצא בתמליל.
- החזר אך ורק JSON תקף לפי הסכמה — ללא טקסט נוסף, ללא markdown."""


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def analyze(transcript: str) -> dict:
    """Run Claude analysis on a Hebrew transcript. Returns dict matching ANALYSIS_SCHEMA."""
    response = _client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": ANALYSIS_SCHEMA,
            }
        },
        messages=[
            {
                "role": "user",
                "content": f"להלן תמליל השיחה לניתוח:\n\n{transcript}",
            }
        ],
    )

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
