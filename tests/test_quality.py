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
    results = batch.compare_models(ROOT / "examples", tmp_path, ["good", "flaky"])
    assert [r["attempts"] for r in results] == [1.0, 2.0]
    assert "| flaky | 1 из 1 |" in (tmp_path / "models.md").read_text(encoding="utf-8")
    assert results[0]["failure"] is None

    def broken(text, previous_code=None, errors=None):
        raise RuntimeError("Ошибка LLM API: Error code: 402")

    monkeypatch.setattr(pipeline.llm, "generate_code", broken)
    results = batch.compare_models(ROOT / "examples", tmp_path, ["paid"])
    assert "1 шт.: Ошибка LLM API: Error code: 402" in results[0]["failure"]
