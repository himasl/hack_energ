from itertools import combinations
from pathlib import Path

import pytest
from lxml import etree

from bpmn_gen.pipeline import build_from_code
from tests.bpmn_moddle import AVAILABLE, moddle_warnings
from bpmn_gen.quality import xsd_errors

EXAMPLES = sorted(Path(__file__).parent.parent.glob("examples/*/code.py"))
BENCH = sorted(Path(__file__).parent.parent.glob("bench/*/code.py"))

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

DOCUMENTS = """
DIAGRAM.set_name('Технологическое присоединение')
pool, (client, office) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Заявитель', 'Сетевая организация'])
request = DIAGRAM.add_data_object('Заявка на присоединение', client)
contract = DIAGRAM.add_data_object('Договор', office)
crm = DIAGRAM.add_data_store('CRM', office)
send = DIAGRAM.add_user_task('Подать заявку', client)
check = DIAGRAM.add_user_task('Проверить заявку', office)
prepare = DIAGRAM.add_script_task('Подготовить договор', office)
sign = DIAGRAM.add_user_task('Подписать договор', client)
DIAGRAM.add_link(ROOT_START_TASK_ID, send)
DIAGRAM.add_link(send, request)
DIAGRAM.add_link(send, check)
DIAGRAM.add_link(request, check)
DIAGRAM.add_link(check, crm)
DIAGRAM.add_link(check, prepare)
DIAGRAM.add_link(prepare, contract)
DIAGRAM.add_link(contract, sign)
DIAGRAM.add_link(prepare, sign)
DIAGRAM.add_link(sign, ROOT_END_TASK_ID)
"""

DRAWN = {
    "task", "userTask", "scriptTask", "subProcess", "startEvent", "endEvent", "exclusiveGateway",
    "parallelGateway", "inclusiveGateway", "sequenceFlow", "messageFlow", "lane", "participant", "group",
    "dataObjectReference", "dataStoreReference", "dataInputAssociation", "dataOutputAssociation",
}

LOOP_CODE = """
pool, lanes = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Оператор', 'Система'])
steps = ['Принять показания', 'Проверить показания', 'Сохранить показания']
prev = ROOT_START_TASK_ID
for i, name in enumerate(steps):
    task = DIAGRAM.add_task(name, lanes[i % len(lanes)])
    DIAGRAM.add_link(prev, task)
    prev = task
DIAGRAM.add_link(prev, ROOT_END_TASK_ID)
"""

JOIN_ACROSS_LANES = """
pool, (master, crew) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Мастер участка', 'Бригада'])
fork = DIAGRAM.add_parallel_gateway('', master)
permit = DIAGRAM.add_user_task('Оформить наряд-допуск', master)
materials = DIAGRAM.add_user_task('Подготовить материалы', crew)
join = DIAGRAM.add_parallel_gateway('', master)
repair = DIAGRAM.add_user_task('Выполнить ремонт', crew)
DIAGRAM.add_link(ROOT_START_TASK_ID, fork)
DIAGRAM.add_link(fork, permit)
DIAGRAM.add_link(fork, materials)
DIAGRAM.add_link(permit, join)
DIAGRAM.add_link(materials, join)
DIAGRAM.add_link(join, repair)
DIAGRAM.add_link(repair, ROOT_END_TASK_ID)
"""

CASES = {"simple": SIMPLE, "documents": DOCUMENTS, "loop_code": LOOP_CODE, "same_lane": SAME_LANE, "loop": LOOP, "nested": NESTED, "two_pools": TWO_POOLS, "join_across_lanes": JOIN_ACROSS_LANES}
CASES.update({p.parent.name: p.read_text(encoding="utf-8") for p in EXAMPLES + BENCH})


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


def shared(a, b, c, d):
    if a[1] == b[1] == c[1] == d[1]:
        lo, hi = 0, 0
    elif a[0] == b[0] == c[0] == d[0]:
        lo, hi = 1, 1
    else:
        return False
    return min(max(a[lo], b[lo]), max(c[hi], d[hi])) - max(min(a[lo], b[lo]), min(c[hi], d[hi])) > 1


@pytest.mark.parametrize("name", CASES)
def test_edges_do_not_share_segments(name):
    from bpmn_gen.layout import layout
    from bpmn_gen.sandbox import run_code
    from bpmn_gen.validate import validate

    graph = run_code(CASES[name]).graph
    validate(graph)
    edges = layout(graph).edges
    for f, g in combinations(graph.flows, 2):
        if f.source == g.source or f.target == g.target:
            continue
        for a, b in zip(edges[f.id], edges[f.id][1:]):
            for c, d in zip(edges[g.id], edges[g.id][1:]):
                assert not shared(a, b, c, d), (f.id, g.id)


@pytest.mark.parametrize("path", BENCH, ids=lambda p: p.parent.name)
def test_bench_reference_is_clean(path):
    result = build_from_code(path.read_text(encoding="utf-8"))
    assert result.errors == [] and result.blocking == []


def test_fixes():
    result = build_from_code(NESTED)
    assert any("Лишний шаг" in w for w in result.warnings)
    assert "messageFlow" in build_from_code(TWO_POOLS).xml


def test_code_errors_point_to_line():
    assert build_from_code("a = DIAGRAM.add_task('x', 'Lane_9')").errors[0].startswith("строка 1:")
    assert "синтаксическая" in build_from_code("a = (").errors[0]
    assert build_from_code("import os").errors
    bad = SIMPLE + "sub = DIAGRAM.create_subprocess('П', ROOT_PROCESS_ID)\nt = DIAGRAM.add_task('В', sub)\nDIAGRAM.add_link(a, t)\n"
    assert "границу подпроцесса" in build_from_code(bad).errors[0]


def warnings_for(code):
    return " | ".join(build_from_code(code).warnings)


def test_logic_warnings():
    xor_and = """
a = DIAGRAM.add_task('Оценить', ROOT_PROCESS_ID)
x = DIAGRAM.add_exclusive_gateway('Нужен ремонт?', ROOT_PROCESS_ID)
b = DIAGRAM.add_task('Отремонтировать', ROOT_PROCESS_ID)
c = DIAGRAM.add_task('Закрыть', ROOT_PROCESS_ID)
j = DIAGRAM.add_parallel_gateway('', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, a)
DIAGRAM.add_link(a, x)
DIAGRAM.add_link(x, b, name='да')
DIAGRAM.add_link(x, c)
DIAGRAM.add_link(b, j)
DIAGRAM.add_link(c, j)
DIAGRAM.add_link(j, ROOT_END_TASK_ID)
"""
    text = warnings_for(xor_and)
    assert "подписаны не все ветки" in text
    assert "будет вечно ждать" in text
    assert "несколько раз" in warnings_for(xor_and.replace("add_exclusive_gateway", "add_parallel_gateway").replace(
        "add_parallel_gateway('', ", "add_exclusive_gateway('', "))

    one_branch = """
x = DIAGRAM.add_exclusive_gateway('Требуется отключение?', ROOT_PROCESS_ID)
a = DIAGRAM.add_task('Согласовать', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, x)
DIAGRAM.add_link(x, a)
DIAGRAM.add_link(a, ROOT_END_TASK_ID)
"""
    assert "только одна ветка" in warnings_for(one_branch)

    documents = """
a = DIAGRAM.add_task('Составить акт', ROOT_PROCESS_ID)
b = DIAGRAM.add_task('Проверить смету', ROOT_PROCESS_ID)
act = DIAGRAM.add_data_object('Акт', ROOT_PROCESS_ID)
estimate = DIAGRAM.add_data_object('Смета', ROOT_PROCESS_ID)
lost = DIAGRAM.add_data_object('Протокол', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, a)
DIAGRAM.add_link(a, b)
DIAGRAM.add_link(b, ROOT_END_TASK_ID)
DIAGRAM.add_link(a, act)
DIAGRAM.add_link(estimate, b)
"""
    text = warnings_for(documents)
    assert "'Акт' создаётся, но дальше нигде не используется" in text
    assert "'Смета' используется, но в процессе нигде не создаётся" in text
    assert "'Протокол' не связан" in text
    assert build_from_code(documents).xml


def test_pipeline_generate_success(monkeypatch):
    import bpmn_gen.pipeline as pipeline

    def fake_generate_code(text, previous_code=None, errors=None):
        return SIMPLE

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", fake_generate_code)

    result = pipeline.generate("Сделать быстрый пример")
    assert result.errors == []
    assert result.xml.startswith("<?xml")
    assert result.code.strip() == SIMPLE.strip()


def test_pipeline_generate_retries_after_error(monkeypatch):
    import bpmn_gen.pipeline as pipeline

    calls = {"count": 0}

    def fake_generate_code(text, previous_code=None, errors=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return "bad = "
        return SIMPLE

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", fake_generate_code)

    result = pipeline.generate("Сделать пример с исправлением")
    assert result.errors == []
    assert result.attempts == 2
    assert calls["count"] == 2


def test_pipeline_generate_fails_after_retries(monkeypatch):
    import bpmn_gen.pipeline as pipeline

    def fake_generate_code(text, previous_code=None, errors=None):
        return "bad = "

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", fake_generate_code)

    result = pipeline.generate("Сделать невалидный пример")
    assert result.errors
    assert any("Не удалось получить корректную схему" in e for e in result.errors)
    assert result.attempts <= 3


XOR_INTO_AND = """
a = DIAGRAM.add_task('Оценить', ROOT_PROCESS_ID)
x = DIAGRAM.add_exclusive_gateway('Нужен ремонт?', ROOT_PROCESS_ID)
b = DIAGRAM.add_task('Отремонтировать', ROOT_PROCESS_ID)
j = DIAGRAM.add_parallel_gateway('', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, a)
DIAGRAM.add_link(a, x)
DIAGRAM.add_link(x, b, name='да')
DIAGRAM.add_link(x, j, name='нет')
DIAGRAM.add_link(b, j)
DIAGRAM.add_link(j, ROOT_END_TASK_ID)
"""


def test_deadlock_goes_back_to_llm(monkeypatch):
    import bpmn_gen.pipeline as pipeline

    seen = []

    def fake_generate_code(text, previous_code=None, errors=None):
        seen.append(errors)
        return XOR_INTO_AND if len(seen) == 1 else XOR_INTO_AND.replace("add_parallel_gateway", "add_exclusive_gateway")

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", fake_generate_code)

    result = pipeline.generate("Процесс с развилкой")
    assert result.attempts == 2
    assert "будет вечно ждать" in seen[1][0]
    assert result.blocking == [] and result.xml


def test_deadlock_kept_as_warning_after_retries(monkeypatch):
    import bpmn_gen.pipeline as pipeline

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", lambda text, previous_code=None, errors=None: XOR_INTO_AND)

    result = pipeline.generate("Процесс с развилкой")
    assert result.attempts == 3
    assert result.errors == [] and result.xml
    assert any("будет вечно ждать" in w for w in result.warnings)


def test_data_errors():
    gateway = SIMPLE + "d = DIAGRAM.add_data_object('Акт', ROOT_PROCESS_ID)\ng = DIAGRAM.add_parallel_gateway('', ROOT_PROCESS_ID)\nDIAGRAM.add_link(g, d)\n"
    assert "только с задачей" in build_from_code(gateway).errors[0]
    pools = TWO_POOLS + "d = DIAGRAM.add_data_object('Обращение', client)\nDIAGRAM.add_link(call, d)\nDIAGRAM.add_link(d, take)\n"
    assert "разных пулов" in build_from_code(pools).errors[0]


def test_process_name():
    xml = build_from_code(DOCUMENTS).xml
    assert 'name="Технологическое присоединение"' in xml


ROUND_TRIP = """
p1, (office,) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Сетевая компания'])
p2, (vendor,) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['Поставщик'])
order = DIAGRAM.add_task('Заказать материалы', office)
ship = DIAGRAM.add_task('Отгрузить материалы', vendor)
receive = DIAGRAM.add_task('Принять материалы', office)
DIAGRAM.add_link(ROOT_START_TASK_ID, order)
DIAGRAM.add_link(order, ship)
DIAGRAM.add_link(ship, receive)
DIAGRAM.add_link(receive, ROOT_END_TASK_ID)
"""


def test_pools_wait_for_reply():
    from bpmn_gen.sandbox import run_code
    from bpmn_gen.validate import validate

    graph = run_code(ROUND_TRIP).graph
    report = validate(graph)
    assert report.warnings == []
    names = {(graph.nodes[f.source].name, graph.nodes[f.target].name) for f in graph.flows if f.kind == "sequenceFlow"}
    assert ("Заказать материалы", "Принять материалы") in names
    office = {n.id for n in graph.nodes.values() if graph.find_up(n.id, "pool").name == "" and n.type == "startEvent"
              and graph.find_up(n.id, "lane").name == "Сетевая компания"}
    assert len(office) == 1


def test_gateway_message_goes_back_to_llm():
    code = TWO_POOLS.replace("DIAGRAM.add_link(call, take)", "g = DIAGRAM.add_exclusive_gateway('Срочно?', client)\nDIAGRAM.add_link(call, g)\nDIAGRAM.add_link(g, take, name='да')\nDIAGRAM.add_link(g, ROOT_END_TASK_ID, name='нет')")
    result = build_from_code(code)
    assert result.xml and any("соединяет шлюз с другим пулом" in m for m in result.blocking)


def test_loop_without_exit_and_unreachable():
    loop = """
a = DIAGRAM.add_task('Проверить', ROOT_PROCESS_ID)
b = DIAGRAM.add_task('Исправить', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, a)
DIAGRAM.add_link(a, b)
DIAGRAM.add_link(b, a)
"""
    result = build_from_code(loop)
    assert result.xml and any("цикл без выхода" in m for m in result.blocking)

    island = SIMPLE + """
c = DIAGRAM.add_task('Согласовать', ROOT_PROCESS_ID)
d = DIAGRAM.add_task('Доработать', ROOT_PROCESS_ID)
DIAGRAM.add_link(c, d)
DIAGRAM.add_link(d, c)
"""
    blocking = build_from_code(island).blocking
    assert any("Недостижимы от старта" in m and "'Согласовать'" in m for m in blocking)


def test_inclusive_split_joins():
    code = """
g = DIAGRAM.add_inclusive_gateway('Кого уведомить?', ROOT_PROCESS_ID)
a = DIAGRAM.add_task('Уведомить соцобъекты', ROOT_PROCESS_ID)
b = DIAGRAM.add_task('Уведомить юрлица', ROOT_PROCESS_ID)
j = DIAGRAM.add_parallel_gateway('', ROOT_PROCESS_ID)
DIAGRAM.add_link(ROOT_START_TASK_ID, g)
DIAGRAM.add_link(g, a, name='соцобъекты')
DIAGRAM.add_link(g, b, name='юрлица')
DIAGRAM.add_link(a, j)
DIAGRAM.add_link(b, j)
DIAGRAM.add_link(j, ROOT_END_TASK_ID)
"""
    assert any("вечно ждать" in m for m in build_from_code(code).blocking)
    exclusive = code.replace("add_parallel_gateway('', ", "add_exclusive_gateway('', ")
    assert any("столько раз" in m for m in build_from_code(exclusive).blocking)
    inclusive = code.replace("add_parallel_gateway('', ", "add_inclusive_gateway('', ")
    assert build_from_code(inclusive).blocking == []


def test_far_data_is_shown_twice():
    code = (Path(__file__).parent.parent / "bench/05_meter_readings/code.py").read_text(encoding="utf-8")
    result = build_from_code(code)
    doc = etree.fromstring(result.xml.encode())
    refs = [e for e in doc.iter() if etree.QName(e).localname == "dataStoreReference"]
    stores = [e for e in doc.iter() if etree.QName(e).localname == "dataStore"]
    assert len(refs) == 2 and len(stores) == 1
    assert {r.get("dataStoreRef") for r in refs} == {stores[0].get("id")}
    assert any("показан ещё раз" in f for f in result.fixes)
