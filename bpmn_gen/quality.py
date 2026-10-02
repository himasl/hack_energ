from itertools import combinations
from pathlib import Path

from lxml import etree

XSD = Path(__file__).parent / "xsd" / "BPMN20.xsd"
MODEL = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
DI = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"
WAYPOINT = "{http://www.omg.org/spec/DD/20100524/DI}waypoint"
FRAMES = {"participant", "lane", "group"}
TASKS = {"task", "userTask", "scriptTask", "subProcess"}
GATEWAYS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway"}

_schema = None


def xsd_errors(xml):
    global _schema
    if _schema is None:
        _schema = etree.XMLSchema(etree.parse(str(XSD)))
    if _schema.validate(etree.fromstring(xml.encode("utf-8"))):
        return []
    return [f"строка {e.line}: {e.message}" for e in _schema.error_log]


def analyze(xml):
    doc = etree.fromstring(xml.encode("utf-8"))
    kinds = {e.get("id"): etree.QName(e).localname for e in doc.iter() if e.get("id")}
    shapes = {}
    for s in doc.iter(f"{DI}BPMNShape"):
        b = s.find(f"{DC}Bounds")
        shapes[s.get("bpmnElement")] = tuple(float(b.get(k)) for k in ("x", "y", "width", "height"))
    edges = {}
    for e in doc.iter(f"{DI}BPMNEdge"):
        edges[e.get("bpmnElement")] = [(float(p.get("x")), float(p.get("y"))) for p in e.iter(WAYPOINT)]

    nodes = {i: box for i, box in shapes.items() if kinds.get(i) not in FRAMES}
    ends = {}
    for e in doc.iter():
        if e.get("sourceRef") and e.get("targetRef"):
            ends[e.get("id")] = (e.get("sourceRef"), e.get("targetRef"))

    errors = xsd_errors(xml)
    return {
        "valid": not errors,
        "xsd_errors": errors,
        "participants": sum(k == "lane" for k in kinds.values()) or sum(k == "participant" for k in kinds.values()),
        "tasks": sum(k in TASKS for k in kinds.values()),
        "gateways": sum(k in GATEWAYS for k in kinds.values()),
        "flows": sum(k in ("sequenceFlow", "messageFlow") for k in kinds.values()),
        "overlaps": count_overlaps(nodes),
        "edges_through_shapes": count_edges_through(edges, nodes, ends),
        "edge_crossings": count_edge_crossings(edges),
    }


def inside(a, b):
    return b[0] <= a[0] and b[1] <= a[1] and a[0] + a[2] <= b[0] + b[2] and a[1] + a[3] <= b[1] + b[3]


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def count_overlaps(nodes):
    return sum(
        1 for a, b in combinations(nodes.values(), 2)
        if overlap(a, b) and not inside(a, b) and not inside(b, a)
    )


def segments(points):
    return list(zip(points, points[1:]))


def crosses_box(a, b, box):
    x, y, w, h = box[0] + 2, box[1] + 2, box[2] - 4, box[3] - 4
    if a[1] == b[1]:
        return y < a[1] < y + h and max(a[0], b[0]) > x and min(a[0], b[0]) < x + w
    if a[0] == b[0]:
        return x < a[0] < x + w and max(a[1], b[1]) > y and min(a[1], b[1]) < y + h
    return False


def count_edges_through(edges, nodes, ends):
    total = 0
    for edge_id, points in edges.items():
        source, target = ends.get(edge_id, (None, None))
        for node_id, box in nodes.items():
            if node_id in (source, target):
                continue
            if all(inside((x, y, 0, 0), box) for x, y in (points[0], points[-1])):
                continue
            if any(crosses_box(a, b, box) for a, b in segments(points)):
                total += 1
    return total


def cross(s, t):
    (a, b), (c, d) = s, t
    if a[1] == b[1] and c[0] == d[0]:
        (a, b), (c, d) = (c, d), (a, b)
    if not (a[0] == b[0] and c[1] == d[1]):
        return False
    x, y = a[0], c[1]
    return min(a[1], b[1]) < y < max(a[1], b[1]) and min(c[0], d[0]) < x < max(c[0], d[0])


def count_edge_crossings(edges):
    lines = list(edges.values())
    return sum(
        1 for p, q in combinations(lines, 2)
        for s in segments(p) for t in segments(q)
        if cross(s, t)
    )
