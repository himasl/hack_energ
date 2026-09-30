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

SAME_LANE = """
check = DIAGRAM.add_task('Проверить показания счётчика', ROOT_PROCESS_ID)
ok = DIAGRAM.add_exclusive_gateway('Показания в норме?', ROOT_PROCESS_ID)
visit = DIAGRAM.add_task('Выехать на объект', ROOT_PROCESS_ID)
act = DIAGRAM.add_task('Составить акт', ROOT_PROCESS_ID)
merge = DIAGRAM.add_exclusive_gateway('', ROOT_PROCESS_ID)
fork = DIAGRAM.add_parallel_gateway('', ROOT_PROCESS_ID)
bill = DIAGRAM.add_task('Выставить счёт', ROOT_PROCESS_ID)
notify = DIAGRAM.add_task('Уведомить абонента', ROOT_PROCESS_ID)
archive = DIAGRAM.add_task('Архивировать данные', ROOT_PROCESS_ID)
join = DIAGRAM.add_parallel_gateway('', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, check)
DIAGRAM.add_link(check, ok)
DIAGRAM.add_link(ok, visit, name='нет')
DIAGRAM.add_link(visit, act)
DIAGRAM.add_link(act, merge)
DIAGRAM.add_link(ok, merge, name='да')
DIAGRAM.add_link(merge, fork)
DIAGRAM.add_link(fork, bill)
DIAGRAM.add_link(fork, notify)
DIAGRAM.add_link(fork, archive)
DIAGRAM.add_link(bill, join)
DIAGRAM.add_link(notify, join)
DIAGRAM.add_link(archive, join)
DIAGRAM.add_link(join, ROOT_END_TASK_ID)
"""

DRAWN = {
    "task", "userTask", "scriptTask", "subProcess", "startEvent", "endEvent", "exclusiveGateway",
    "parallelGateway", "inclusiveGateway", "sequenceFlow", "messageFlow", "lane", "participant", "group",
}

CASES = {"simple": SIMPLE, "same_lane": SAME_LANE, "loop": LOOP, "nested": NESTED, "two_pools": TWO_POOLS}
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


def crosses(a, b, box):
    x, y, w, h = box[0] + 2, box[1] + 2, box[2] - 4, box[3] - 4
    if a[1] == b[1]:
        return y < a[1] < y + h and max(a[0], b[0]) > x and min(a[0], b[0]) < x + w
    if a[0] == b[0]:
        return x < a[0] < x + w and max(a[1], b[1]) > y and min(a[1], b[1]) < y + h
    return False


@pytest.mark.parametrize("name", CASES)
def test_edges_do_not_cross_shapes(name):
    from bpmn_gen.layout import layout
    from bpmn_gen.sandbox import run_code
    from bpmn_gen.validate import validate

    graph = run_code(CASES[name]).graph
    validate(graph)
    result = layout(graph)
    for f in graph.flows:
        around = {c.id for c in graph.ancestors(graph.nodes[f.source].parent)}
        others = [n for n in graph.nodes if n not in (f.source, f.target) and n not in around]
        points = result.edges[f.id]
        for a, b in zip(points, points[1:]):
            for n in others:
                assert not crosses(a, b, result.shapes[n]), (f.id, n)


def test_fixes():
    result = build_from_code(NESTED)
    assert any("Лишний шаг" in f for f in result.fixes)
    assert "messageFlow" in build_from_code(TWO_POOLS).xml


def test_code_errors_point_to_line():
    assert build_from_code("a = DIAGRAM.add_task('x', 'Lane_9')").errors[0].startswith("строка 1:")
    assert "синтаксическая" in build_from_code("a = (").errors[0]
    bad = SIMPLE + "sub = DIAGRAM.create_subprocess('П', ROOT_PROCESS_ID)\nt = DIAGRAM.add_task('В', sub)\nDIAGRAM.add_link(a, t)\n"
    assert "границу подпроцесса" in build_from_code(bad).errors[0]
