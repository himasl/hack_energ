from pathlib import Path

from bpmn_gen import batch
from bpmn_gen.quality import analyze

ROOT = Path(__file__).parent.parent
MINIMAL = (Path(__file__).parent / "fixtures" / "minimal.bpmn").read_text(encoding="utf-8")


def test_clean_diagram():
    result = analyze(MINIMAL)
    assert result["valid"]
    assert (result["tasks"], result["flows"]) == (1, 2)
    assert result["overlaps"] == result["edges_through_shapes"] == result["edge_crossings"] == 0


def test_detects_overlap():
    assert analyze(MINIMAL.replace('<dc:Bounds x="392" y="102"', '<dc:Bounds x="320" y="102"'))["overlaps"] == 1


def test_detects_edge_through_shape():
    assert analyze(MINIMAL.replace('<dc:Bounds x="392" y="102"', '<dc:Bounds x="200" y="102"'))["edges_through_shapes"] == 1


def test_detects_edge_crossing():
    crossing = MINIMAL.replace(
        '<di:waypoint x="340" y="120"/>\n        <di:waypoint x="392" y="120"/>',
        '<di:waypoint x="200" y="60"/>\n        <di:waypoint x="200" y="200"/>',
    )
    assert analyze(crossing)["edge_crossings"] == 1


def test_batch_report(tmp_path):
    rows = batch.run(ROOT / "examples", tmp_path, code=True)
    assert rows and all(r["valid"] for r in rows)
    assert (tmp_path / "report.md").exists() and (tmp_path / "report.json").exists()
    assert (tmp_path / f"{rows[0]['name']}.bpmn").exists()


def test_batch_report_not_built(tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "broken.py").write_text("bad = ", encoding="utf-8")
    rows = batch.run(cases, tmp_path / "out", code=True)
    assert rows[0]["valid"] is None
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "Построено: 0 из 1, валидных по XSD: 0" in report


def test_compare_models(tmp_path, monkeypatch):
    import os

    from bpmn_gen import pipeline

    good = (ROOT / "examples/01_repair_request/code.py").read_text(encoding="utf-8")

    def fake(text, previous_code=None, errors=None):
        return "bad = " if os.environ["LLM_MODEL"] == "flaky" and not errors else good

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", fake)
    one = tmp_path / "cases" / "01_repair_request"
    one.mkdir(parents=True)
    (one / "input.txt").write_text((ROOT / "examples/01_repair_request/input.txt").read_text(encoding="utf-8"), encoding="utf-8")
    results = batch.compare_models(tmp_path / "cases", tmp_path, ["good", "flaky"])
    assert [r["attempts"] for r in results] == [1.0, 2.0]
    assert "| flaky | 1 из 1 |" in (tmp_path / "models.md").read_text(encoding="utf-8")
    assert results[0]["failure"] is None

    def broken(text, previous_code=None, errors=None):
        raise RuntimeError("Ошибка LLM API: Error code: 402")

    monkeypatch.setattr(pipeline.llm, "generate_code", broken)
    results = batch.compare_models(tmp_path / "cases", tmp_path, ["paid"])
    assert "1 шт.: Ошибка LLM API: Error code: 402" in results[0]["failure"]


def test_parallel_batch_keeps_order(tmp_path, monkeypatch):
    import time

    from bpmn_gen import pipeline

    codes = {p.read_text(encoding="utf-8"): (p.parent / "code.py").read_text(encoding="utf-8")
             for p in (ROOT / "bench").glob("*/input.txt")}

    def slow(text, previous_code=None, errors=None):
        time.sleep(0.3)
        return codes[text]

    monkeypatch.setattr(pipeline.llm, "config", lambda: {"max_repairs": 2})
    monkeypatch.setattr(pipeline.llm, "generate_code", slow)
    started = time.time()
    rows = batch.run(ROOT / "bench", tmp_path, jobs=8)
    assert time.time() - started < 1.5
    assert [r["name"] for r in rows] == sorted(r["name"] for r in rows)
    assert all(r["valid"] for r in rows)
    assert all(r["steps_found"] == 100 for r in rows)
    assert "Совпадение с эталоном: участники 100%" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_compare_with_reference():
    from bpmn_gen.compare import compare, graph_from_code, similarity

    assert similarity("Зарегистрировать заявку", "Регистрация заявки") == 1.0
    assert similarity("Выполнить работы", "Выполнить ремонт") < 0.6
    code = (ROOT / "bench/02_permit_to_work/code.py").read_text(encoding="utf-8")
    reference = graph_from_code(code)
    assert compare(reference, reference)["steps_found"] == 100
    worse = code.replace("briefing = DIAGRAM.add_user_task('Провести целевой инструктаж', admitter)\n", "").replace(
        "DIAGRAM.add_link(check_place, briefing)\nDIAGRAM.add_link(briefing, admit)", "DIAGRAM.add_link(check_place, admit)")
    found = compare(graph_from_code(worse), reference)
    assert found["missing_steps"] == ["Провести целевой инструктаж"]
    assert found["steps_found"] < 100 and found["order_kept"] == 100 and found["steps_precise"] == 100
    swapped = code.replace("DIAGRAM.add_link(admit, work)\nDIAGRAM.add_link(work, hand_over)\nDIAGRAM.add_link(hand_over, close)",
                           "DIAGRAM.add_link(admit, hand_over)\nDIAGRAM.add_link(hand_over, work)\nDIAGRAM.add_link(work, close)")
    assert swapped != code and compare(graph_from_code(swapped), reference)["order_kept"] < 100


def test_compare_synonyms():
    from bpmn_gen.compare import similarity

    assert similarity("Отправить заявку на отключение", "Направить заявку на отключение") == 1.0
    assert similarity("Опубликовать информацию на сайте", "Разместить информацию на сайте") == 1.0
    assert similarity("Отключить оборудование", "Включить потребителей") == 0.0
