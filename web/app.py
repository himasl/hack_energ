from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bpmn_gen import pipeline

load_dotenv()
STATIC = Path(__file__).parent / "static"
EXAMPLES = Path(__file__).parent.parent / "examples"

app = FastAPI(title="Архитектор BPMN-диаграмм")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class TextIn(BaseModel):
    text: str


class CodeIn(BaseModel):
    code: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/examples")
def examples():
    items = []
    for folder in sorted(p for p in EXAMPLES.iterdir() if (p / "input.txt").exists()):
        code = folder / "code.py"
        items.append({
            "name": folder.name,
            "text": (folder / "input.txt").read_text(encoding="utf-8"),
            "code": code.read_text(encoding="utf-8") if code.exists() else "",
        })
    return items


@app.post("/api/generate")
def generate(body: TextIn):
    if not body.text.strip():
        raise HTTPException(400, "Пустое описание процесса")
    try:
        result = pipeline.generate(body.text)
        return asdict(result)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except (ConnectionError, PermissionError, RuntimeError) as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Внутренняя ошибка при генерации: {exc}")


@app.post("/api/build")
def build(body: CodeIn):
    try:
        return asdict(pipeline.build_from_code(body.code))
    except Exception as e:
        raise HTTPException(500, f"Внутренняя ошибка при сборке схемы: {e}")
