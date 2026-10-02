from dataclasses import dataclass, field

from . import llm
from .layout import layout
from .render import render
from .sandbox import run_code
from .validate import validate


@dataclass
class Result:
    xml: str = ""
    code: str = ""
    attempts: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fixes: list = field(default_factory=list)
    blocking: list = field(default_factory=list)


def build_from_code(code):
    result = Result(code=code, attempts=1)
    run = run_code(code)
    if run.error:
        result.errors.append(run.error)
        return result
    report = validate(run.graph)
    result.errors, result.warnings, result.fixes = report.errors, report.warnings, report.fixes
    result.blocking = report.blocking
    if not report.errors:
        result.xml = render(run.graph, layout(run.graph))
    return result


def generate(text):
    if not text or not text.strip():
        raise ValueError("Пустое описание процесса")

    code, errors = None, None
    max_repairs = llm.config()["max_repairs"]

    for attempt in range(max_repairs + 1):
        try:
            code = llm.generate_code(text, code, errors)
        except Exception as exc:
            return Result(
                code=code or "",
                attempts=attempt + 1,
                errors=[str(exc)],
                warnings=[],
                fixes=[],
            )

        result = build_from_code(code)
        result.attempts = attempt + 1
        if not result.errors and (not result.blocking or attempt >= max_repairs):
            return result

        if attempt >= max_repairs:
            result.errors.append(
                "Не удалось получить корректную схему после нескольких попыток. "
                "Проверьте описание процесса и попробуйте ещё раз."
            )
            return result

        errors = result.errors or result.blocking

    return result
