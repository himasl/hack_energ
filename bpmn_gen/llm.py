import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI, RateLimitError

PROMPT = Path(__file__).parent / "prompts" / "system.md"


def config():
    load_dotenv()
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    return {
        "base_url": os.getenv("LLM_BASE_URL"),
        "api_key": os.getenv("LLM_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
        "timeout": timeout,
        "max_repairs": int(os.getenv("LLM_MAX_REPAIRS", "2")),
    }


def _read_system_prompt():
    if not PROMPT.exists():
        return "You create valid Python code for BPMN generation. Return only Python code."
    return PROMPT.read_text(encoding="utf-8")


def _extract_python_code(raw_text):
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return ""
    match = re.search(r"```(?:python)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    return cleaned.strip()


def generate_code(text, previous_code=None, errors=None):
    cfg = config()
    base_url = cfg["base_url"]
    api_key = cfg["api_key"]
    model = cfg["model"]

    if not base_url or not api_key or not model:
        raise ValueError(
            "LLM не настроен: задайте LLM_BASE_URL, LLM_API_KEY и LLM_MODEL в .env "
            "или окружении проекта."
        )

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=cfg["timeout"])

    prompt = _read_system_prompt()
    user_parts = [
        "Задача: по описанию процесса напиши Python-код для DIAGRAM API.",
        f"Описание процесса:\n{text}\n",
    ]
    if previous_code:
        user_parts.append("Предыдущая версия кода:\n```python\n" + previous_code + "\n```\n")
    if errors:
        user_parts.append("Ошибки, которые надо исправить:\n" + "\n".join(str(e) for e in errors))
    user_message = "\n".join(user_parts)

    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=cfg["temperature"],
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
        )
    except TimeoutError as exc:
        raise RuntimeError("LLM таймаут: проверьте LLM_TIMEOUT и доступность провайдера.") from exc
    except AuthenticationError as exc:
        raise PermissionError("LLM API: неверный LLM_API_KEY или недоступен токен.") from exc
    except RateLimitError as exc:
        raise RuntimeError("LLM API: превышен лимит запросов, повторите позже.") from exc
    except APIConnectionError as exc:
        raise ConnectionError("Не удалось подключиться к LLM провайдеру: проверьте LLM_BASE_URL.") from exc
    except APIError as exc:
        raise RuntimeError(f"Ошибка LLM API: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ошибка генерации через LLM: {exc}") from exc

    content = completion.choices[0].message.content
    code = _extract_python_code(content)
    if not code:
        raise RuntimeError("LLM вернул пустой ответ: ожидался Python-код.")
    return code
