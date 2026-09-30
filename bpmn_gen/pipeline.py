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


def build_from_code(code):
    result = Result(code=code, attempts=1)
    run = run_code(code)
    if run.error:
        result.errors.append(run.error)
        return result
    report = validate(run.graph)
    result.errors, result.warnings, result.fixes = report.errors, report.warnings, report.fixes
    if not report.errors:
        result.xml = render(run.graph, layout(run.graph))
    return result


def generate(text):
    code, errors = None, None
    for attempt in range(llm.config()["max_repairs"] + 1):
        code = llm.generate_code(text, code, errors)
        result = build_from_code(code)
        result.attempts = attempt + 1
        if not result.errors:
            break
        errors = result.errors
    return result
