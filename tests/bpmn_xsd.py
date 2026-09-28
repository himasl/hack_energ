from pathlib import Path

from lxml import etree

SCHEMA = etree.XMLSchema(etree.parse(str(Path(__file__).parent / "xsd" / "BPMN20.xsd")))


def xsd_errors(xml):
    if SCHEMA.validate(etree.fromstring(xml.encode("utf-8"))):
        return []
    return [f"строка {e.line}: {e.message}" for e in SCHEMA.error_log]
