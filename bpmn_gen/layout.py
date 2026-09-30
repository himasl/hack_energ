from .graph import EVENTS, GATEWAYS, Layout

TASK_SIZE = (120, 80)
EVENT_SIZE = (36, 36)
GATEWAY_SIZE = (50, 50)
COL_GAP = 60
ROW_GAP = 40
PAD = 30
HEADER = 30
POOL_GAP = 50
MIN_LANE = 120
MARGIN = 60


def size(node):
    if node.type in EVENTS:
        return EVENT_SIZE
    if node.type in GATEWAYS:
        return GATEWAY_SIZE
    return TASK_SIZE


def layout(graph):
    out = Layout()
    place(graph, graph.root.id, out, MARGIN, MARGIN)
    add_groups(graph, out)
    return out


def scope(graph, node_id):
    return graph.find_up(node_id, "process", "subProcess").id


def place(graph, scope_id, out, x0, y0):
    nodes = [n for n in graph.nodes.values() if scope(graph, n.id) == scope_id]
    ids = {n.id for n in nodes}
    flows = [f for f in graph.flows if f.source in ids and f.target in ids]
    sizes = {n.id: measure(graph, n.id) if n.type == "subProcess" else size(n) for n in nodes}
    rank, order, back = ranking(nodes, flows)

    bands = band_list(graph, scope_id)
    pooled = bands != [None]
    band = {n.id: band_of(graph, n.id, bands) for n in nodes}
    slot = assign_slots(nodes, flows, back, rank, order, band, bands)

    ranks = range(max(rank.values(), default=0) + 1)
    col_w = [max([sizes[i][0] for i in ids if rank[i] == r], default=0) for r in ranks]
    col_x, x = [], x0 + (HEADER + PAD if pooled else PAD)
    for w in col_w:
        col_x.append(x)
        x += w + COL_GAP
    width = x - x0

    slot_h = {b: [] for b in bands}
    for i in ids:
        rows = slot_h[band[i]]
        rows.extend([0] * (slot[i] + 1 - len(rows)))
        rows[slot[i]] = max(rows[slot[i]], sizes[i][1])
    band_h = {b: sum(h) + ROW_GAP * (len(h) - 1) + 2 * PAD for b, h in slot_h.items()}
    if pooled:
        band_h = {b: max(h, MIN_LANE) for b, h in band_h.items()}

    band_y, y, last_pool = {}, y0 + (0 if scope_id == graph.root.id else 20), None
    for b in bands:
        pool = pool_of(graph, b)
        if last_pool and pool != last_pool:
            y += POOL_GAP
        band_y[b], y, last_pool = y, y + band_h[b], pool
    height = y - y0

    for n in nodes:
        w, h = sizes[n.id]
        r, s, b = rank[n.id], slot[n.id], band[n.id]
        rows = slot_h[b]
        top = band_y[b] + PAD + sum(rows[:s]) + ROW_GAP * s + (rows[s] - h) / 2
        out.shapes[n.id] = (col_x[r] + (col_w[r] - w) / 2, top, w, h)
        if n.type == "subProcess":
            place(graph, n.id, out, *out.shapes[n.id][:2])

    if pooled:
        add_pools(graph, bands, band_y, band_h, out, x0, width)
    for f in flows:
        floor = None
        if (f.source, f.target) in back or out.shapes[f.target][0] <= out.shapes[f.source][0]:
            floor = lowest(out.shapes, ids, f, band_y[band[f.target]], band_h[band[f.target]])
        out.edges[f.id] = route(graph, f, out.shapes, floor)
    return width, height


def lowest(shapes, ids, flow, band_top, band_height):
    left = shapes[flow.target][0]
    right = shapes[flow.source][0] + shapes[flow.source][2]
    bottoms = [
        y + h for x, y, w, h in (shapes[i] for i in ids)
        if x < right and x + w > left and band_top <= y < band_top + band_height
    ]
    return max(bottoms) + 20


def measure(graph, node_id):
    return place(graph, node_id, Layout(), 0, 0)


def ranking(nodes, flows):
    succ = {n.id: [] for n in nodes}
    for f in flows:
        succ[f.source].append(f.target)
    targets = {f.target for f in flows}
    roots = [n.id for n in nodes if n.type == "startEvent"]
    roots += [n.id for n in nodes if n.id not in targets] + list(succ)

    order, state, back, finished = {}, {}, set(), []

    def visit(u):
        state[u] = "open"
        order[u] = len(order)
        for v in succ[u]:
            if state.get(v) == "open":
                back.add((u, v))
            elif v not in state:
                visit(v)
        state[u] = "done"
        finished.append(u)

    for r in roots:
        if r not in state:
            visit(r)

    rank = {i: 0 for i in succ}
    for u in reversed(finished):
        for v in succ[u]:
            if (u, v) not in back:
                rank[v] = max(rank[v], rank[u] + 1)
    return rank, order, back


def band_list(graph, scope_id):
    if scope_id != graph.root.id:
        return [None]
    bands = []
    for pool in graph.containers.values():
        if pool.type == "pool":
            lanes = [c.id for c in graph.subcontainers(pool.id) if c.type == "lane"]
            bands += lanes or [pool.id]
    return bands or [None]


def band_of(graph, node_id, bands):
    box = graph.find_up(node_id, "lane", "pool")
    return box.id if box and box.id in bands else bands[0]


def pool_of(graph, band):
    if band is None:
        return None
    box = graph.containers[band]
    return box.parent if box.type == "lane" else box.id


def assign_slots(nodes, flows, back, rank, order, band, bands):
    preds = {n.id: [] for n in nodes}
    for f in flows:
        if (f.source, f.target) not in back and f.kind == "sequenceFlow":
            preds[f.target].append(f.source)

    slot = {}

    def key(i):
        above = [slot[p] for p in preds[i] if p in slot and band[p] == band[i]]
        return (sum(above) / len(above) if above else 0, order[i])

    for r in range(max(rank.values(), default=0) + 1):
        for b in bands:
            cell = sorted((n.id for n in nodes if rank[n.id] == r and band[n.id] == b), key=key)
            for s, i in enumerate(cell):
                slot[i] = s
    return slot


def add_pools(graph, bands, band_y, band_h, out, x0, width):
    pools = {}
    for b in bands:
        pools.setdefault(pool_of(graph, b), []).append(b)
    for pool, members in pools.items():
        top = band_y[members[0]]
        out.shapes[pool] = (x0, top, width, sum(band_h[b] for b in members))
        for b in members:
            if b != pool:
                out.shapes[b] = (x0 + HEADER, band_y[b], width - HEADER, band_h[b])


def route(graph, flow, shapes, floor):
    sx, sy, sw, sh = shapes[flow.source]
    tx, ty, tw, th = shapes[flow.target]
    scx, scy, tcx, tcy = sx + sw / 2, sy + sh / 2, tx + tw / 2, ty + th / 2

    if flow.kind == "messageFlow":
        start, end = (sy + sh, ty) if tcy > scy else (sy, ty + th)
        mid = (start + end) / 2
        return [(scx, start), (scx, mid), (tcx, mid), (tcx, end)]
    if floor is not None:
        gap = sx + sw + COL_GAP / 2
        return [(sx + sw, scy), (gap, scy), (gap, floor), (tcx, floor), (tcx, ty + th)]
    if abs(scy - tcy) < 1:
        return [(sx + sw, scy), (tx, tcy)]
    if graph.nodes[flow.source].type in GATEWAYS:
        return [(scx, sy if tcy < scy else sy + sh), (scx, tcy), (tx, tcy)]
    if graph.nodes[flow.target].type in GATEWAYS:
        return [(sx + sw, scy), (tcx, scy), (tcx, ty if scy < tcy else ty + th)]
    mid = tx - COL_GAP / 2
    return [(sx + sw, scy), (mid, scy), (mid, tcy), (tx, tcy)]


def add_groups(graph, out):
    for group in graph.containers.values():
        if group.type != "group":
            continue
        boxes = [
            out.shapes[n.id] for n in graph.nodes.values()
            if n.id in out.shapes and any(c.id == group.id for c in graph.ancestors(n.parent))
        ]
        if boxes:
            left = min(b[0] for b in boxes) - 15
            top = min(b[1] for b in boxes) - 15
            right = max(b[0] + b[2] for b in boxes) + 15
            bottom = max(b[1] + b[3] for b in boxes) + 15
            out.shapes[group.id] = (left, top, right - left, bottom - top)
