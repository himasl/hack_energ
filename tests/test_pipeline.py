from itertools import combinations
from pathlib import Path

import pytest
from lxml import etree

from bpmn_gen.pipeline import build_from_code
from tests.bpmn_moddle import AVAILABLE, moddle_warnings
from tests.bpmn_xsd import xsd_errors

EXAMPLES = sorted(Path(__file__).parent.parent.glob("examples/*/code.py"))

SIMPLE = """
a = DIAGRAM.add_task('Принять заявку', ROOT_PROCESS_ID)
b = DIAGRAM.add_task('Проверить', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, a)
DIAGRAM.add_link(a, b)
DIAGRAM.add_link(b, ROOT_END_TASK_ID)
"""

LOOP = """
pool, (client, office) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Заявитель', 'Сетевая компания'])
send = DIAGRAM.add_user_task('Подать заявку', client)
check = DIAGRAM.add_user_task('Проверить документы', office)
ok = DIAGRAM.add_exclusive_gateway('Документы полные?', office)
fix = DIAGRAM.add_user_task('Дополнить документы', client)
DIAGRAM.add_link(ROOT_START_TASK_ID, send)
DIAGRAM.add_link(send, check)
DIAGRAM.add_link(check, ok)
DIAGRAM.add_link(ok, fix, name='нет')
DIAGRAM.add_link(fix, check)
DIAGRAM.add_link(ok, ROOT_END_TASK_ID, name='да')
"""

NESTED = """
pool, (a, b) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Диспетчер', 'Бригада'])
sub = DIAGRAM.create_subprocess('Подготовка к работам', b)
s1 = DIAGRAM.add_task('Получить наряд', sub)
s2 = DIAGRAM.add_task('Провести инструктаж', sub)
DIAGRAM.add_link(s1, s2)
grp = DIAGRAM.add_group('Контроль', a)
c = DIAGRAM.add_task('Проверить готовность', grp)
d = DIAGRAM.add_task('Лишний шаг', a)
DIAGRAM.add_link(ROOT_START_TASK_ID, c)
DIAGRAM.add_link(c, sub)
DIAGRAM.add_link(sub, ROOT_END_TASK_ID)
"""

TWO_POOLS = """
p1, (client,) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Потребитель'])
p2, (grid,) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Диспетчер сети'])
call = DIAGRAM.add_user_task('Сообщить об отключении', client)
take = DIAGRAM.add_user_task('Принять обращение', grid)
DIAGRAM.add_link(ROOT_START_TASK_ID, call)
DIAGRAM.add_link(call, take)
DIAGRAM.add_link(take, ROOT_END_TASK_ID)
"""

DRAWN = {
    "task", "userTask", "scriptTask", "subProcess", "startEvent", "endEvent", "exclusiveGateway",
    "parallelGateway", "inclusiveGateway", "sequenceFlow", "messageFlow", "lane", "participant", "group",
}

CASES = {"simple": SIMPLE, "loop": LOOP, "nested": NESTED, "two_pools": TWO_POOLS}
CASES.update({p.parent.name: p.read_text(encoding="utf-8") for p in EXAMPLES})


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


@pytest.mark.parametrize("name", CASES)
def test_valid_bpmn(name):
    result = build_from_code(CASES[name])
    assert result.errors == []
    assert xsd_errors(result.xml) == []

    doc = etree.fromstring(result.xml.encode())
    elements = {e.get("id") for e in doc.iter() if etree.QName(e).localname in DRAWN}
    drawn = {e.get("bpmnElement") for e in doc.iter() if e.get("bpmnElement")}
    assert drawn - {"Collaboration_1", "Process_1"} == elements


@pytest.mark.skipif(not AVAILABLE, reason="нужен node и npm install в tests/moddle")
@pytest.mark.parametrize("name", CASES)
def test_bpmn_moddle_reads_without_warnings(name):
    assert moddle_warnings(build_from_code(CASES[name]).xml) == []


@pytest.mark.parametrize("name", CASES)
def test_shapes_do_not_overlap(name):
    from bpmn_gen.layout import layout
    from bpmn_gen.sandbox import run_code
    from bpmn_gen.validate import validate

    graph = run_code(CASES[name]).graph
    validate(graph)
    shapes = layout(graph).shapes
    for a, b in combinations(graph.nodes, 2):
        inside = graph.nodes[a].parent == b or graph.nodes[b].parent == a
        assert inside or not overlaps(shapes[a], shapes[b]), (a, b)


def test_fixes():
    result = build_from_code(NESTED)
    assert any("Лишний шаг" in f for f in result.fixes)
    assert "messageFlow" in build_from_code(TWO_POOLS).xml


def test_code_errors_point_to_line():
    assert build_from_code("a = DIAGRAM.add_task('x', 'Lane_9')").errors[0].startswith("строка 1:")
    assert "синтаксическая" in build_from_code("a = (").errors[0]
    bad = SIMPLE + "sub = DIAGRAM.create_subprocess('П', ROOT_PROCESS_ID)\nt = DIAGRAM.add_task('В', sub)\nDIAGRAM.add_link(a, t)\n"
    assert "границу подпроцесса" in build_from_code(bad).errors[0]
