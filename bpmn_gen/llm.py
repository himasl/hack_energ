import os
from pathlib import Path

PROMPT = Path(__file__).parent / "prompts" / "system.md"


def config():
    return {
        "base_url": os.getenv("LLM_BASE_URL"),
        "api_key": os.getenv("LLM_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
        "max_repairs": int(os.getenv("LLM_MAX_REPAIRS", "2")),
    }


def generate_code(text, previous_code=None, errors=None):
    raise NotImplementedError
