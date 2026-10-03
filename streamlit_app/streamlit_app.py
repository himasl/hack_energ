import json
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
VENDOR = ROOT / "web" / "static" / "vendor"
EXAMPLES = ROOT / "examples"
SETTINGS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TEMPERATURE", "LLM_TIMEOUT", "LLM_MAX_REPAIRS")


def secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


load_dotenv(ROOT / ".env")
for name in SETTINGS:
    if secret(name) is not None:
        os.environ[name] = str(secret(name))

from bpmn_gen import pipeline  # noqa: E402

EDITOR = """<!doctype html><html><head><meta charset="utf-8"><style>{css}
html, body {{ margin: 0; height: 100%; font: 14px system-ui, sans-serif; }}
#canvas {{ height: calc(100% - 44px); border: 1px solid #d0d7de; border-radius: 6px; }}
.bar {{ height: 44px; display: flex; gap: 8px; align-items: center; }}
button {{ padding: 6px 12px; border: 1px solid #d0d7de; border-radius: 6px; background: #f6f8fa; cursor: pointer; }}
</style></head><body>
<div class="bar"><button id="bpmn">Скачать .bpmn с правками</button><button id="svg">Скачать .svg</button></div>
<div id="canvas"></div>
<script>{js}</script>
<script>
const modeler = new BpmnJS({{ container: '#canvas' }});
modeler.importXML({xml}).then(() => {{
  const canvas = modeler.get('canvas');
  canvas.zoom('fit-viewport', 'auto');
}});
function save(name, content, type) {{
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([content], {{ type }}));
  link.download = name;
  link.click();
}}
document.getElementById('bpmn').onclick = async () => save('diagram.bpmn', (await modeler.saveXML({{ format: true }})).xml, 'application/xml');
document.getElementById('svg').onclick = async () => save('diagram.svg', (await modeler.saveSVG()).svg, 'image/svg+xml');
</script></body></html>"""


@st.cache_resource
def editor_assets():
    css = "".join((VENDOR / name).read_text(encoding="utf-8") for name in ("diagram-js.css", "bpmn-js.css", "bpmn-embedded.css"))
    return css, (VENDOR / "bpmn-modeler.production.min.js").read_text(encoding="utf-8")


def examples():
    items = {}
    for folder in sorted(p for p in EXAMPLES.iterdir() if (p / "input.txt").exists()):
        items[folder.name] = (folder / "input.txt").read_text(encoding="utf-8")
    return items


def show(result):
    if result.attempts > 1:
        st.info(f"Модель исправляла код: попыток {result.attempts}")
    for message in result.errors:
        st.error(message)
    for message in result.warnings:
        st.warning(message)
    if result.fixes:
        with st.expander(f"Исправлено автоматически: {len(result.fixes)}"):
            for message in result.fixes:
                st.write("•", message)
    if not result.xml:
        return
    css, js = editor_assets()
    xml = json.dumps(result.xml).replace("</", "<\\/")
    st.iframe(EDITOR.format(css=css, js=js, xml=xml), height=640)
    left, right = st.columns(2)
    left.download_button("Скачать .bpmn", result.xml, "diagram.bpmn", "application/xml", use_container_width=True)
    right.download_button("Скачать код на API DIAGRAM", result.code, "diagram.py", "text/x-python", use_container_width=True)


st.set_page_config(page_title="Архитектор BPMN-диаграмм", layout="wide")
st.title("Архитектор BPMN-диаграмм")
st.caption("Описание бизнес-процесса → BPMN 2.0, который открывается и редактируется в bpmn.io")

password = secret("APP_PASSWORD")
if password and st.session_state.get("password") != password:
    entered = st.text_input("Пароль", type="password")
    if entered != password:
        st.stop()
    st.session_state["password"] = entered

if not os.environ.get("LLM_API_KEY"):
    st.warning("LLM не настроена: задайте LLM_BASE_URL, LLM_API_KEY и LLM_MODEL в Secrets приложения. "
               "Сборка из готового кода работает и без неё.")

samples = examples()
choice = st.selectbox("Пример", ["—"] + list(samples))
text = st.text_area("Описание процесса", samples.get(choice, ""), height=220)

if st.button("Построить схему", type="primary", disabled=not text.strip()):
    with st.spinner("Модель пишет код, валидатор проверяет схему…"):
        try:
            st.session_state["result"] = pipeline.generate(text)
        except Exception as exc:
            st.session_state.pop("result", None)
            st.error(str(exc))

with st.expander("Собрать из готового кода на API DIAGRAM, без LLM"):
    code_path = EXAMPLES / choice / "code.py"
    code = st.text_area("Код", code_path.read_text(encoding="utf-8") if code_path.exists() else "", height=220)
    if st.button("Собрать", disabled=not code.strip()):
        st.session_state["result"] = pipeline.build_from_code(code, text or None)

if "result" in st.session_state:
    show(st.session_state["result"])
