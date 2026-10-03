import pytest

from bpmn_gen.sandbox import run_code

ATTACKS = {
    "subclasses": ("x = ().__class__.__base__.__subclasses__()", "только к методам DIAGRAM"),
    "import": ("import os", "Import не разрешена"),
    "internals": ("g = DIAGRAM.graph", "только к методам DIAGRAM"),
    "dunder": ("__import__('os')", "__import__ не разрешено"),
    "builtins": ("x = open('/etc/passwd')", "'open' is not defined"),
    "while": ("while True:\n    pass", "While не разрешена"),
    "power": ("x = 2\nfor i in range(10 ** 9):\n    pass", "строка 2: конструкция Pow"),
    "memory": ("x = 'a' * 9999", "Mult не разрешена"),
    "big number": ("x = 100000000", "слишком большое число"),
    "range": ("for i in range(5000):\n    pass", "range не больше"),
    "function": ("def f():\n    pass", "FunctionDef не разрешена"),
}


@pytest.mark.parametrize("name", ATTACKS)
def test_sandbox_rejects(name):
    code, message = ATTACKS[name]
    result = run_code(code)
    assert result.graph is None and message in result.error


def test_sandbox_timeout():
    code = "for i in range(1000):\n    for j in range(1000):\n        for k in range(1000):\n            pass"
    assert "дольше 1 с" in run_code(code, timeout=1).error


def test_sandbox_allows_loops_and_fstrings():
    code = """
pool, lanes = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['A', 'B'])
prev = ROOT_START_TASK_ID
for i, name in enumerate(['Принять', 'Проверить']):
    task = DIAGRAM.add_task(f'{name} заявку {i + 1}', lanes[i % len(lanes)])
    DIAGRAM.add_link(prev, task)
    prev = task
DIAGRAM.add_link(prev, ROOT_END_TASK_ID)
"""
    result = run_code(code)
    assert result.error is None
    assert {n.name for n in result.graph.nodes.values()} >= {"Принять заявку 1", "Проверить заявку 2"}
