import ast
import builtins
import sys
import time
import traceback
from dataclasses import dataclass

from .diagram import Diagram

SAFE = ("len", "enumerate", "zip", "list", "dict", "tuple", "str", "int", "min", "max")
API = {name for name in dir(Diagram) if not name.startswith("_") and callable(getattr(Diagram, name))}
MAX_RANGE = 1000
MAX_NUMBER = 10_000

ALLOWED = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.For, ast.If, ast.Pass, ast.Break, ast.Continue,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.JoinedStr, ast.FormattedValue,
    ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Starred,
    ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.comprehension,
    ast.Subscript, ast.Slice, ast.Call, ast.keyword, ast.Attribute,
    ast.BinOp, ast.Add, ast.Sub, ast.Mod,
    ast.UnaryOp, ast.USub, ast.Not,
    ast.BoolOp, ast.And, ast.Or,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.IfExp,
)


class Rejected(Exception):
    def __init__(self, line, message):
        super().__init__(message)
        self.line = line


class Timeout(Exception):
    pass


def lines(tree):
    found = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            found[child] = getattr(child, "lineno", None) or found.get(parent) or getattr(parent, "lineno", "?")
    return found


def check(tree):
    line_of = lines(tree)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None) or line_of.get(node, "?")
        if not isinstance(node, ALLOWED):
            raise Rejected(line, f"конструкция {type(node).__name__} не разрешена: используйте только "
                                 f"присваивания, for, if и вызовы DIAGRAM.*")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise Rejected(line, f"имя {node.id} не разрешено")
        if isinstance(node, ast.Attribute):
            if not (isinstance(node.value, ast.Name) and node.value.id == "DIAGRAM") or node.attr not in API:
                raise Rejected(line, f"обращаться через точку можно только к методам DIAGRAM: {', '.join(sorted(API))}")
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool) \
                and abs(node.value) > MAX_NUMBER:
            raise Rejected(line, f"слишком большое число: {node.value}")


def safe_range(*args):
    values = range(*args)
    if len(values) > MAX_RANGE:
        raise ValueError(f"range не больше {MAX_RANGE} элементов")
    return values


@dataclass
class RunResult:
    graph: object = None
    error: str | None = None


def run_code(code, timeout=5):
    try:
        tree = ast.parse(code, "<llm>")
        check(tree)
    except SyntaxError as e:
        return RunResult(error=f"строка {e.lineno}: синтаксическая ошибка: {e.msg}")
    except Rejected as e:
        return RunResult(error=f"строка {e.line}: {e}")

    diagram = Diagram()
    scope = {
        "__builtins__": {name: getattr(builtins, name) for name in SAFE} | {"range": safe_range},
        "DIAGRAM": diagram,
        "ROOT_PROCESS_ID": diagram.root_process_id,
        "ROOT_START_TASK_ID": diagram.root_start_id,
        "ROOT_END_TASK_ID": diagram.root_end_id,
    }
    deadline = time.monotonic() + timeout

    def watch(frame, event, arg):
        if time.monotonic() > deadline:
            raise Timeout()
        return watch

    previous = sys.gettrace()
    sys.settrace(watch)
    try:
        exec(compile(tree, "<llm>", "exec"), scope)
    except Timeout:
        return RunResult(error=f"код выполнялся дольше {timeout} с: уберите бесконечные или слишком длинные циклы")
    except Exception as e:
        frames = [f.lineno for f in traceback.extract_tb(e.__traceback__) if f.filename == "<llm>"]
        line = frames[-1] if frames else "?"
        message = e.args[0] if e.args else type(e).__name__
        return RunResult(error=f"строка {line}: {message}")
    finally:
        sys.settrace(previous)
    return RunResult(graph=diagram.graph)
