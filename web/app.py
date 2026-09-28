from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bpmn_gen import pipeline

load_dotenv()
app = FastAPI(title="Архитектор BPMN-диаграмм")
INDEX = Path(__file__).parent / "static" / "index.html"


class TextIn(BaseModel):
    text: str


class CodeIn(BaseModel):
    code: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/generate")
def generate(body: TextIn):
    if not body.text.strip():
        raise HTTPException(400, "Пустое описание процесса")
    return asdict(pipeline.generate(body.text))


@app.post("/api/build")
def build(body: CodeIn):
    return asdict(pipeline.build_from_code(body.code))


@app.get("/")
def index():
    if not INDEX.exists():
        raise HTTPException(404, "Интерфейс ещё не готов")
    return FileResponse(INDEX)
