from pathlib import Path

VENDOR = Path(__file__).parent.parent / "web" / "static" / "vendor"
STYLES = ("diagram-js.css", "bpmn-js.css", "bpmn-embedded.css")
MARGIN = 20
FOOTER = 50

PAGE = """<html><head><style>{css}
html, body {{ margin: 0; background: #fff; }}
#canvas {{ width: 100vw; height: 100vh; }}
.djs-palette {{ display: none; }}
</style></head><body><div id="canvas"></div><script>{js}</script></body></html>"""

IMPORT = """async (xml) => {
  window.modeler = new BpmnJS({ container: '#canvas' });
  await window.modeler.importXML(xml);
  const { x, y, width, height } = window.modeler.get('canvas').viewbox().inner;
  return { x, y, width, height };
}"""

FIT = """(box) => window.modeler.get('canvas').viewbox(box)"""


def to_png(xml, path, scale=2):
    from playwright.sync_api import sync_playwright

    css = "".join((VENDOR / name).read_text(encoding="utf-8") for name in STYLES)
    js = (VENDOR / "bpmn-modeler.production.min.js").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=scale)
        page.set_content(PAGE.format(css=css, js=js))
        box = page.evaluate(IMPORT, xml)
        box = {
            "x": box["x"] - MARGIN,
            "y": box["y"] - MARGIN,
            "width": box["width"] + 2 * MARGIN,
            "height": box["height"] + 2 * MARGIN + FOOTER,
        }
        page.set_viewport_size({"width": round(box["width"]), "height": round(box["height"])})
        page.evaluate(FIT, box)
        page.screenshot(path=str(path))
        browser.close()
