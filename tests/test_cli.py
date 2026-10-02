import sys

from bpmn_gen import cli


def test_png_without_playwright(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "png_available", lambda: False)
    monkeypatch.setattr(sys, "argv", ["bpmn_gen", "--code", "examples/01_repair_request/code.py",
                                      "-o", str(tmp_path / "out.bpmn"), "--png"])
    assert cli.main() == 1
    assert "pip install playwright" in capsys.readouterr().err
