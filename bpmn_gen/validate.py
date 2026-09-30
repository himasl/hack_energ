from dataclasses import dataclass, field

from .graph import EVENTS, GATEWAYS


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fixes: list = field(default_factory=list)


def validate(graph):
    report = Report()
    check_scopes(graph, report)
    if report.errors:
        return report
    drop_empty_gateways(graph, report)
    connect_dangling(graph, report)
    put_into_lanes(graph, report)
    make_message_flows(graph, report)
    close_pools(graph)
    check_reachable(graph, report)
    return report


def scope(graph, node_id):
    return graph.find_up(node_id, "process", "subProcess").id


def label(graph, node_id):
    node = graph.nodes[node_id]
    return f"'{node.name}'" if node.name else node.id


def scopes(graph):
    return [graph.root.id] + [c.id for c in graph.containers.values() if c.type == "subProcess"]


def event(graph, scope_id, type):
    for node in graph.nodes.values():
        if node.type == type and scope(graph, node.id) == scope_id:
            return node.id
    return graph.add_node(type, "", scope_id).id


def check_scopes(graph, report):
    for f in graph.flows:
        if scope(graph, f.source) != scope(graph, f.target):
            report.errors.append(
                f"Связь {label(graph, f.source)} → {label(graph, f.target)} пересекает границу подпроцесса: "
                f"внутри подпроцесса связывайте только его элементы, а сам подпроцесс — как обычную задачу"
            )
        if graph.nodes[f.target].type == "startEvent":
            report.errors.append(f"В стартовое событие не может входить связь (от {label(graph, f.source)})")
        if graph.nodes[f.source].type == "endEvent":
            report.errors.append(f"Из конечного события не может выходить связь (к {label(graph, f.target)})")


def drop_empty_gateways(graph, report):
    for node in list(graph.nodes.values()):
        ins, outs = graph.incoming(node.id), graph.outgoing(node.id)
        if node.type in GATEWAYS and not node.name and len(ins) == 1 and len(outs) == 1:
            report.fixes.append(f"Убран лишний шлюз {label(graph, node.id)}")
            ins[0].target = outs[0].target
            ins[0].name = ins[0].name or outs[0].name
            graph.flows.remove(outs[0])
            del graph.nodes[node.id]


def connect_dangling(graph, report):
    for scope_id in scopes(graph):
        members = [n for n in graph.nodes.values() if scope(graph, n.id) == scope_id and n.type not in EVENTS]
        for node in members:
            if not graph.incoming(node.id):
                graph.add_flow(event(graph, scope_id, "startEvent"), node.id)
                report.fixes.append(f"{label(graph, node.id)} соединён со стартом")
            if not graph.outgoing(node.id):
                graph.add_flow(node.id, event(graph, scope_id, "endEvent"))
                report.fixes.append(f"{label(graph, node.id)} соединён с концом")
        start, end = event(graph, scope_id, "startEvent"), event(graph, scope_id, "endEvent")
        if not graph.outgoing(start) and not graph.incoming(end):
            graph.add_flow(start, end)


def lane_of(graph, node_id):
    box = graph.find_up(node_id, "lane", "pool")
    return box.id if box else None


def put_into_lanes(graph, report):
    boxes = [c.id for c in graph.containers.values() if c.type == "lane"]
    boxes += [c.id for c in graph.containers.values() if c.type == "pool" and not graph.subcontainers(c.id)]
    if not boxes:
        return
    for node in graph.nodes.values():
        if scope(graph, node.id) != graph.root.id or lane_of(graph, node.id):
            continue
        neighbours = [f.target for f in graph.outgoing(node.id)] + [f.source for f in graph.incoming(node.id)]
        if node.type == "endEvent":
            neighbours.reverse()
        lanes = [lane_of(graph, n) for n in neighbours if lane_of(graph, n)]
        chain = graph.ancestors(node.parent)
        holder = node if len(chain) == 1 else chain[-2]
        holder.parent = lanes[0] if lanes else boxes[0]
        if node.type not in EVENTS:
            report.fixes.append(f"{label(graph, node.id)} перенесён в дорожку '{graph.containers[holder.parent].name}'")


def make_message_flows(graph, report):
    for f in graph.flows:
        a, b = graph.find_up(f.source, "pool"), graph.find_up(f.target, "pool")
        if a and b and a.id != b.id and f.kind == "sequenceFlow":
            f.kind = "messageFlow"
            report.fixes.append(f"Связь {label(graph, f.source)} → {label(graph, f.target)} между пулами стала сообщением")


def close_pools(graph):
    pools = [c.id for c in graph.containers.values() if c.type == "pool"]
    if len(pools) < 2:
        return
    for node in list(graph.nodes.values()):
        if node.type in EVENTS or scope(graph, node.id) != graph.root.id:
            continue
        flows = [f for f in graph.flows if f.kind == "sequenceFlow"]
        if not any(f.target == node.id for f in flows):
            graph.add_flow(pool_event(graph, node.id, "startEvent"), node.id)
        if not any(f.source == node.id for f in flows):
            graph.add_flow(node.id, pool_event(graph, node.id, "endEvent"))


def pool_event(graph, node_id, type):
    pool = graph.find_up(node_id, "pool")
    for other in graph.nodes.values():
        if other.type == type and scope(graph, other.id) == graph.root.id and graph.find_up(other.id, "pool") == pool:
            return other.id
    return graph.add_node(type, "", lane_of(graph, node_id)).id


def check_reachable(graph, report):
    starts = [n.id for n in graph.nodes.values() if n.type == "startEvent"]
    seen, stack = set(starts), list(starts)
    while stack:
        for f in graph.outgoing(stack.pop()):
            if f.target not in seen:
                seen.add(f.target)
                stack.append(f.target)
    for node in graph.nodes.values():
        if node.id not in seen:
            report.warnings.append(f"{label(graph, node.id)} недостижим от старта")
