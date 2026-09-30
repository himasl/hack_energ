from lxml import etree

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
OWNERS = ("subProcess", "pool", "process")


def tag(kind):
    prefix, local = kind.split(":")
    return f"{{{NS[prefix]}}}{local}"


def add(parent, kind, **attrs):
    return etree.SubElement(parent, tag(kind), {k: str(v) for k, v in attrs.items() if v != ""})


def num(v):
    return str(round(v))


def owner(graph, container_id):
    return next(c.id for c in graph.ancestors(container_id) if c.type in OWNERS)


def render(graph, layout):
    root = etree.Element(tag("bpmn:definitions"), nsmap=NS, id="Definitions_1",
                         targetNamespace="http://bpmn.io/schema/bpmn")
    main = graph.root
    pools = [c for c in graph.containers.values() if c.type == "pool"]
    elements = {}

    if pools:
        collab = add(root, "bpmn:collaboration", id="Collaboration_1")
        for pool in pools:
            names = [c.name for c in graph.subcontainers(pool.id) if c.type == "lane"]
            name = pool.name or (names[0] if len(names) == 1 else main.name)
            add(collab, "bpmn:participant", id=pool.id, name=name, processRef=f"Process_{pool.id}")
        for pool in pools:
            elements[pool.id] = add(root, "bpmn:process", id=f"Process_{pool.id}", isExecutable="false")
    else:
        elements[main.id] = add(root, "bpmn:process", id=main.id, name=main.name, isExecutable="false")

    def home(container_id):
        key = owner(graph, container_id)
        return elements[key] if key in elements else elements[pools[0].id]

    lanes = {}
    for pool in pools:
        members = [c for c in graph.subcontainers(pool.id) if c.type == "lane"]
        if members:
            lane_set = add(elements[pool.id], "bpmn:laneSet", id=f"LaneSet_{pool.id}")
            for lane in members:
                lanes[lane.id] = add(lane_set, "bpmn:lane", id=lane.id, name=lane.name)

    for node in graph.nodes.values():
        el = add(home(node.parent), f"bpmn:{node.type}", id=node.id, name=node.name)
        for f in graph.incoming(node.id):
            if f.kind == "sequenceFlow":
                add(el, "bpmn:incoming").text = f.id
        for f in graph.outgoing(node.id):
            if f.kind == "sequenceFlow":
                add(el, "bpmn:outgoing").text = f.id
        if node.type == "subProcess":
            elements[node.id] = el
        lane = graph.find_up(node.id, "lane", "subProcess")
        if lane and lane.type == "lane":
            add(lanes[lane.id], "bpmn:flowNodeRef").text = node.id

    for f in graph.flows:
        if f.kind == "messageFlow":
            add(collab, "bpmn:messageFlow", id=f.id, name=f.name, sourceRef=f.source, targetRef=f.target)
        else:
            add(home(graph.nodes[f.source].parent), "bpmn:sequenceFlow", id=f.id, name=f.name, sourceRef=f.source, targetRef=f.target)

    for group in graph.containers.values():
        if group.type == "group" and group.id in layout.shapes:
            category = add(root, "bpmn:category", id=f"Category_{group.id}")
            add(category, "bpmn:categoryValue", id=f"CategoryValue_{group.id}", value=group.name)
            add(home(group.parent), "bpmn:group", id=group.id,
                categoryValueRef=f"CategoryValue_{group.id}")

    diagram = add(root, "bpmndi:BPMNDiagram", id="BPMNDiagram_1")
    plane = add(diagram, "bpmndi:BPMNPlane", id="BPMNPlane_1",
                bpmnElement="Collaboration_1" if pools else main.id)

    def shape(element_id, **attrs):
        x, y, w, h = layout.shapes[element_id]
        s = add(plane, "bpmndi:BPMNShape", id=f"{element_id}_di", bpmnElement=element_id, **attrs)
        add(s, "dc:Bounds", x=num(x), y=num(y), width=num(w), height=num(h))

    for pool in pools:
        shape(pool.id, isHorizontal="true")
    for lane_id in lanes:
        shape(lane_id, isHorizontal="true")
    for node in graph.nodes.values():
        if node.type == "subProcess":
            shape(node.id, isExpanded="true")
        elif node.type == "exclusiveGateway":
            shape(node.id, isMarkerVisible="true")
        else:
            shape(node.id)
    for f in graph.flows:
        edge = add(plane, "bpmndi:BPMNEdge", id=f"{f.id}_di", bpmnElement=f.id)
        for x, y in layout.edges[f.id]:
            add(edge, "di:waypoint", x=num(x), y=num(y))
    for group in graph.containers.values():
        if group.type == "group" and group.id in layout.shapes:
            shape(group.id)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode()
