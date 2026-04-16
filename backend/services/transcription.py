import os
from functools import lru_cache

from openai import OpenAI


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe Hebrew audio with Whisper. Returns the plain text."""
    response = _client().audio.transcriptions.create(
        model="whisper-1",
        file=(filename, audio_bytes),
        language="he",
        response_format="text",
    )
    return response if isinstance(response, str) else response.text
