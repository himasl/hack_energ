from dataclasses import dataclass


@dataclass
class RunResult:
    graph: object = None
    error: str | None = None


def run_code(code, timeout=5):
    raise NotImplementedError
