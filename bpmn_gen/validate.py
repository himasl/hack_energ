from dataclasses import dataclass, field

from .graph import DATA, DATA_FLOWS, EVENTS, GATEWAYS

SEQ = "sequenceFlow"


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fixes: list = field(default_factory=list)
    blocking: list = field(default_factory=list)

    def block(self, message):
        self.warnings.append(message)
        self.blocking.append(message)


def validate(graph):
    report = Report()
    check_links(graph, report)
    if report.errors:
        return report
    check_logic(graph, report)
    drop_empty_gateways(graph, report)
    connect_dangling(graph, report)
    put_into_lanes(graph, report)
    check_data_pools(graph, report)
    if report.errors:
        return report
    split_far_data(graph, report)
    make_message_flows(graph, report)
    await_replies(graph, report)
    close_pools(graph, report)
    drop_unused_events(graph)
    check_reachable(graph, report)
    check_exits(graph, report)
    return report


def check_language(graph, text, report):
    def latin_share(s):
        letters = [c for c in s if c.isalpha()]
        return sum(c.isascii() for c in letters) / len(letters) if letters else 0

    if latin_share(text) > 0.5:
        return
    names = [n.name for n in graph.nodes.values() if n.name] + [c.name for c in graph.containers.values() if c.name]
    latin = [name for name in names if latin_share(name) > 0.5]
    if names and len(latin) * 2 > len(names):
        report.block(
            f"Названия написаны не на языке описания: {', '.join(repr(n) for n in latin[:3])}. "
            f"Пишите названия шагов, участников и документов так же, как в описании процесса"
        )


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


def check_links(graph, report):
    for f in graph.flows:
        source, target = graph.nodes[f.source], graph.nodes[f.target]
        if scope(graph, f.source) != scope(graph, f.target):
            report.errors.append(
                f"Связь {label(graph, f.source)} → {label(graph, f.target)} пересекает границу подпроцесса: "
                f"внутри подпроцесса связывайте только его элементы, а сам подпроцесс — как обычную задачу"
            )
        if f.kind in DATA_FLOWS:
            other = source if f.kind == "dataOutputAssociation" else target
            if other.type in DATA or other.type in EVENTS or other.type in GATEWAYS:
                report.errors.append(
                    f"Связь {label(graph, f.source)} → {label(graph, f.target)}: документ или хранилище "
                    f"можно связывать только с задачей или подпроцессом"
                )
            continue
        if target.type == "startEvent":
            report.errors.append(f"В стартовое событие не может входить связь (от {label(graph, f.source)})")
        if source.type == "endEvent":
            report.errors.append(f"Из конечного события не может выходить связь (к {label(graph, f.target)})")


def check_logic(graph, report):
    for node in list(graph.nodes.values()):
        ins, outs = graph.incoming(node.id, SEQ), graph.outgoing(node.id, SEQ)
        name = label(graph, node.id)
        if node.type in ("exclusiveGateway", "inclusiveGateway") and len(outs) > 1 and not all(f.name for f in outs):
            report.warnings.append(f"У развилки {name} подписаны не все ветки")
        if node.type in GATEWAYS and node.name and len(ins) == 1 and len(outs) == 1:
            report.block(f"У развилки {name} только одна ветка: похоже, вторая потерялась. Добавьте ветку для другого исхода условия")
        if node.type == "dataObjectReference":
            made = graph.incoming(node.id, "dataOutputAssociation")
            used = graph.outgoing(node.id, "dataInputAssociation")
            if made and not used:
                report.warnings.append(f"Документ {name} создаётся, но дальше нигде не используется")
            if used and not made:
                report.warnings.append(f"Документ {name} используется, но в процессе нигде не создаётся")
            if not made and not used:
                report.warnings.append(f"Документ {name} не связан ни с одной задачей")
        if node.type in ("exclusiveGateway", "parallelGateway") and len(ins) > 1:
            check_join(graph, node, report)


MERGES = {
    ("exclusiveGateway", "parallelGateway"): "exclusiveGateway",
    ("inclusiveGateway", "parallelGateway"): "inclusiveGateway",
    ("inclusiveGateway", "exclusiveGateway"): "inclusiveGateway",
    ("parallelGateway", "exclusiveGateway"): "parallelGateway",
}
GATEWAY_NAMES = {"exclusiveGateway": "исключающем", "parallelGateway": "параллельном", "inclusiveGateway": "включающем"}
GATEWAY_KINDS = {"exclusiveGateway": "исключающий", "parallelGateway": "параллельный", "inclusiveGateway": "включающий"}
MERGE_KINDS = {"exclusiveGateway": "исключающее", "parallelGateway": "параллельное", "inclusiveGateway": "включающее"}
WHY = {
    "parallelGateway": "процесс вечно ждал бы ветку, которая не выполнялась",
    "exclusiveGateway": "следующий шаг выполнился бы несколько раз",
}


def check_join(graph, join, report):
    splits = set()
    for f in graph.incoming(join.id, SEQ):
        current, seen = f.source, set()
        while current not in seen:
            seen.add(current)
            if graph.nodes[current].type in GATEWAYS and len(graph.outgoing(current, SEQ)) > 1:
                break
            ins = graph.incoming(current, SEQ)
            if len(ins) != 1:
                return
            current = ins[0].source
        splits.add(current)
    if len(splits) != 1:
        return
    split = graph.nodes[splits.pop()]
    wanted = MERGES.get((split.type, join.type))
    if not wanted:
        return
    why = WHY[join.type]
    if len(graph.outgoing(join.id, SEQ)) <= 1:
        old, join.type = join.type, wanted
        report.fixes.append(
            f"Ветки развилки {label(graph, split.id)} сходились в {GATEWAY_NAMES[old]} шлюзе ({why}): "
            f"он заменён на {GATEWAY_KINDS[wanted]}"
        )
        return
    merge = graph.add_node(wanted, "", join.parent)
    for f in graph.incoming(join.id, SEQ):
        f.target = merge.id
    graph.add_flow(merge.id, join.id)
    report.fixes.append(
        f"Ветки развилки {label(graph, split.id)} сходились в {GATEWAY_NAMES[join.type]} шлюзе {label(graph, join.id)} "
        f"({why}): перед ним добавлено {MERGE_KINDS[wanted]} слияние"
    )


def drop_empty_gateways(graph, report):
    for node in list(graph.nodes.values()):
        ins, outs = graph.incoming(node.id, SEQ), graph.outgoing(node.id, SEQ)
        if node.type in GATEWAYS and not node.name and len(ins) == 1 and len(outs) == 1:
            report.fixes.append(f"Убран лишний шлюз {label(graph, node.id)}")
            ins[0].target = outs[0].target
            ins[0].name = ins[0].name or outs[0].name
            graph.flows.remove(outs[0])
            del graph.nodes[node.id]


def many_pools(graph):
    return sum(c.type == "pool" for c in graph.containers.values()) > 1


def connect_dangling(graph, report):
    for scope_id in scopes(graph):
        if scope_id == graph.root.id and many_pools(graph):
            continue
        members = [
            n for n in graph.nodes.values()
            if scope(graph, n.id) == scope_id and n.type not in EVENTS and n.type not in DATA
        ]
        inner = scope_id != graph.root.id
        no_in = [n for n in members if not graph.incoming(n.id, SEQ)]
        no_out = [n for n in members if not graph.outgoing(n.id, SEQ)]
        for node in no_in:
            graph.add_flow(event(graph, scope_id, "startEvent"), node.id)
            if not (inner and len(no_in) == 1):
                report.block(
                    f"Обрыв логики: в {label(graph, node.id)} ничего не ведёт, соединено со стартом. "
                    f"Свяжите этот шаг с шагом, после которого он выполняется"
                )
        for node in no_out:
            graph.add_flow(node.id, event(graph, scope_id, "endEvent"))
            if not (inner and len(no_out) == 1):
                report.warnings.append(f"Обрыв логики: из {label(graph, node.id)} процесс никуда не идёт, соединено с концом")
        start, end = event(graph, scope_id, "startEvent"), event(graph, scope_id, "endEvent")
        if not graph.outgoing(start, SEQ) and not graph.incoming(end, SEQ):
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


def check_data_pools(graph, report):
    for node in graph.nodes.values():
        if node.type not in DATA:
            continue
        links = [f.target for f in graph.outgoing(node.id)] + [f.source for f in graph.incoming(node.id)]
        pools = {graph.find_up(n, "pool").id for n in links if graph.find_up(n, "pool")}
        own = graph.find_up(node.id, "pool")
        if len(pools) == 1 and own and own.id not in pools:
            node.parent = lane_of(graph, links[0])
            report.fixes.append(f"{label(graph, node.id)} перенесён в дорожку '{graph.containers[node.parent].name}'")
        if len(pools) > 1:
            report.errors.append(
                f"{label(graph, node.id)} связан с задачами из разных пулов: передачу между пулами "
                f"показывайте связью между задачами, а документ создайте в каждом пуле отдельно"
            )


FAR = 2


def steps_between(graph, a, b):
    seen, frontier, depth = {a}, [a], 0
    while frontier and depth <= FAR:
        if b in frontier:
            return depth
        depth += 1
        nxt = []
        for n in frontier:
            for f in graph.outgoing(n, SEQ) + graph.incoming(n, SEQ):
                other = f.target if f.source == n else f.source
                if other not in seen:
                    seen.add(other)
                    nxt.append(other)
        frontier = nxt
    return depth


def split_far_data(graph, report):
    for node in [n for n in graph.nodes.values() if n.type in DATA]:
        links = graph.incoming(node.id) + graph.outgoing(node.id)
        if len(links) < 2:
            continue
        task = lambda f: f.source if f.target == node.id else f.target
        owners = {node.id: task(links[0])}
        for f in links[1:]:
            near = next((c for c, o in owners.items() if steps_between(graph, o, task(f)) <= FAR), None)
            if near is None:
                copy = graph.add_node(node.type, node.name, graph.nodes[task(f)].parent)
                copy.ref = node.ref or node.id
                owners[copy.id] = task(f)
                near = copy.id
                report.fixes.append(
                    f"{label(graph, node.id)} показан ещё раз рядом с {label(graph, task(f))}, "
                    f"чтобы связь не тянулась через всю схему"
                )
            if f.target == node.id:
                f.target = near
            else:
                f.source = near


def make_message_flows(graph, report):
    for f in graph.flows:
        a, b = graph.find_up(f.source, "pool"), graph.find_up(f.target, "pool")
        if a and b and a.id != b.id and f.kind == SEQ:
            f.kind = "messageFlow"
            report.fixes.append(f"Связь {label(graph, f.source)} → {label(graph, f.target)} между пулами стала сообщением")
            if graph.nodes[f.source].type in GATEWAYS or graph.nodes[f.target].type in GATEWAYS:
                report.block(
                    f"Связь {label(graph, f.source)} → {label(graph, f.target)} соединяет шлюз с другим пулом: "
                    f"сообщение между пулами может идти только от задачи к задаче. Ветку шлюза ведите к задаче "
                    f"своего пула (например, «Отправить ...»), а от неё — связь в другой пул"
                )


def await_replies(graph, report):
    if not many_pools(graph):
        return
    pool = {n: graph.find_up(n, "pool") for n in graph.nodes}
    waiting = {
        n for n in graph.nodes
        if not graph.incoming(n, SEQ) and graph.incoming(n, "messageFlow") and scope(graph, n) == graph.root.id
    }
    for node in list(graph.nodes.values()):
        if graph.outgoing(node.id, SEQ) or not graph.outgoing(node.id, "messageFlow"):
            continue
        seen, queue = {node.id}, [f.target for f in graph.outgoing(node.id, "messageFlow")]
        while queue:
            current = queue.pop(0)
            if current in waiting and pool[current] == pool[node.id]:
                graph.add_flow(node.id, current)
                waiting.discard(current)
                report.fixes.append(f"{label(graph, node.id)} → {label(graph, current)}: процесс ждёт ответа из другого пула")
                break
            seen.add(current)
            outs = [f for f in graph.outgoing(current) if f.kind not in DATA_FLOWS]
            if graph.nodes[current].type in ("exclusiveGateway", "inclusiveGateway") and len(outs) > 1:
                continue
            queue += [f.target for f in outs if f.target not in seen]


def close_pools(graph, report):
    pools = [c.id for c in graph.containers.values() if c.type == "pool"]
    if len(pools) < 2:
        return
    for node in list(graph.nodes.values()):
        if node.type in EVENTS or node.type in DATA or scope(graph, node.id) != graph.root.id:
            continue
        if not graph.incoming(node.id, SEQ):
            if not graph.incoming(node.id, "messageFlow"):
                report.block(
                    f"Обрыв логики: в {label(graph, node.id)} ничего не ведёт, соединено со стартом. "
                    f"Свяжите этот шаг с шагом, после которого он выполняется"
                )
            graph.add_flow(pool_event(graph, node.id, "startEvent"), node.id)
        if not graph.outgoing(node.id, SEQ):
            graph.add_flow(node.id, pool_event(graph, node.id, "endEvent"))


def drop_unused_events(graph):
    if not many_pools(graph):
        return
    for node in list(graph.nodes.values()):
        if node.type in EVENTS and scope(graph, node.id) == graph.root.id \
                and not graph.incoming(node.id) and not graph.outgoing(node.id):
            del graph.nodes[node.id]


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
            if f.target not in seen and f.kind not in DATA_FLOWS:
                seen.add(f.target)
                stack.append(f.target)
    lost = [label(graph, n.id) for n in graph.nodes.values() if n.id not in seen and n.type not in DATA]
    if lost:
        report.block(f"Недостижимы от старта: {', '.join(lost)}. В эти шаги нельзя попасть ни с одной ветки процесса")


def check_exits(graph, report):
    ends = [n.id for n in graph.nodes.values() if n.type == "endEvent"]
    seen, stack = set(ends), list(ends)
    while stack:
        for f in graph.incoming(stack.pop()):
            if f.source not in seen and f.kind not in DATA_FLOWS:
                seen.add(f.source)
                stack.append(f.source)
    stuck = [label(graph, n.id) for n in graph.nodes.values() if n.id not in seen and n.type not in DATA]
    if stuck:
        report.block(
            f"Из шагов {', '.join(stuck)} нельзя дойти до завершения: похоже на цикл без выхода. "
            f"Добавьте ветку, которая выводит из цикла"
        )
