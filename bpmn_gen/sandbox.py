import traceback
from dataclasses import dataclass

from .diagram import Diagram


@dataclass
class RunResult:
    graph: object = None
    error: str | None = None


def run_code(code, timeout=5):
    diagram = Diagram()
    scope = {
        "__builtins__": {},
        "DIAGRAM": diagram,
        "ROOT_PROCESS_ID": diagram.root_process_id,
        "ROOT_START_TASK_ID": diagram.root_start_id,
        "ROOT_END_TASK_ID": diagram.root_end_id,
    }
    try:
        exec(compile(code, "<llm>", "exec"), scope)
    except SyntaxError as e:
        return RunResult(error=f"строка {e.lineno}: синтаксическая ошибка: {e.msg}")
    except Exception as e:
        frames = [f.lineno for f in traceback.extract_tb(e.__traceback__) if f.filename == "<llm>"]
        line = frames[-1] if frames else "?"
        message = e.args[0] if e.args else type(e).__name__
        return RunResult(error=f"строка {line}: {message}")
    return RunResult(graph=diagram.graph)
