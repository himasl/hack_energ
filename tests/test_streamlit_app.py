from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parent.parent / "streamlit_app" / "streamlit_app.py")


def test_builds_example_from_code():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.selectbox[0].select("02_tech_connection").run()
    at.button[1].click().run()
    assert not at.exception and not at.error
    assert [b.label for b in at.get("download_button")] == ["Скачать .bpmn", "Скачать код на API DIAGRAM"]


def test_password():
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["APP_PASSWORD"] = "секрет"
    at.run()
    assert len(at.selectbox) == 0
    at.text_input[0].input("секрет").run()
    assert len(at.selectbox) == 1
