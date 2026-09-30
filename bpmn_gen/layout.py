from .graph import EVENTS, GATEWAYS, Layout

TASK_SIZE = (120, 80)
EVENT_SIZE = (36, 36)
GATEWAY_SIZE = (50, 50)
DUMMY_SIZE = (0, 20)
LABEL_SIZE = (100, 28)
COL_GAP = 60
ROW_GAP = 40
PAD = 30
HEADER = 30
POOL_GAP = 50
MIN_LANE = 120
MARGIN = 60
SWEEPS = 4


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

    chains = {}
    for f in flows:
        if (f.source, f.target) in back or f.kind == "messageFlow":
            continue
        chain = [f.source]
        for r in range(rank[f.source] + 1, rank[f.target]):
            dummy = f"{f.id}:{r}"
            rank[dummy], band[dummy], sizes[dummy], order[dummy] = r, band[f.source], DUMMY_SIZE, order[f.source] + 0.5
            chain.append(dummy)
        chains[f.id] = chain + [f.target]
    slot = assign_slots(chains, rank, order, band, bands)

    ranks = range(max(rank.values(), default=0) + 1)
    col_w = [max([sizes[i][0] for i in rank if rank[i] == r], default=0) for r in ranks]
    col_x, x = [], x0 + (HEADER + PAD if pooled else PAD)
    for w in col_w:
        col_x.append(x)
        x += w + COL_GAP
    width = x - x0

    slot_h = {b: [] for b in bands}
    for i in rank:
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

    boxes = {}
    for i in rank:
        w, h = sizes[i]
        r, s, b = rank[i], slot[i], band[i]
        rows = slot_h[b]
        center = band_y[b] + PAD + sum(rows[:s]) + ROW_GAP * s + rows[s] / 2
        if i in ids:
            boxes[i] = (col_x[r] + (col_w[r] - w) / 2, center - h / 2, w, h)
        else:
            boxes[i] = (col_x[r], center, col_w[r], 0)

    for n in nodes:
        out.shapes[n.id] = boxes[n.id]
        if n.type == "subProcess":
            place(graph, n.id, out, *boxes[n.id][:2])

    if pooled:
        add_pools(graph, bands, band_y, band_h, out, x0, width)
    for f in flows:
        if f.id in chains:
            out.edges[f.id] = route(graph, f, boxes, chains[f.id][1:-1])
        elif f.kind == "messageFlow":
            out.edges[f.id] = message_route(boxes[f.source], boxes[f.target])
        else:
            floor = lowest(boxes, ids, f, band_y[band[f.target]], band_h[band[f.target]])
            out.edges[f.id] = back_route(boxes[f.source], boxes[f.target], floor)
    for n in nodes:
        if n.type in GATEWAYS and n.name:
            out.labels[n.id] = gateway_label(graph, n.id, boxes[n.id], out.edges)
    return width, height


def gateway_label(graph, node_id, box, edges):
    x, y, w, h = box
    ends = [edges[f.id][0] for f in graph.outgoing(node_id)] + [edges[f.id][-1] for f in graph.incoming(node_id)]
    below_used = any(abs(py - (y + h)) < 1 for px, py in ends)
    top = y - 8 - LABEL_SIZE[1] if below_used else y + h + 8
    return (x + w / 2 - LABEL_SIZE[0] / 2, top, *LABEL_SIZE)


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
    for u in succ:
        if u not in targets and succ[u]:
            rank[u] = min(rank[v] for v in succ[u]) - 1
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


def assign_slots(chains, rank, order, band, bands):
    preds = {i: [] for i in rank}
    succs = {i: [] for i in rank}
    for chain in chains.values():
        for a, b in zip(chain, chain[1:]):
            preds[b].append(a)
            succs[a].append(b)

    band_index = {b: k for k, b in enumerate(bands)}
    ranks = range(max(rank.values(), default=0) + 1)
    cells = {(r, b): sorted((i for i in rank if rank[i] == r and band[i] == b), key=order.get) for r in ranks for b in bands}
    index = {i: k for cell in cells.values() for k, i in enumerate(cell)}

    def pos(i):
        return band_index[band[i]] * 1000 + index[i]

    def sweep(rank_order, neighbours):
        for r in rank_order:
            for b in bands:
                cell = cells[(r, b)]
                weight = {i: sum(map(pos, neighbours[i])) / len(neighbours[i]) if neighbours[i] else pos(i) for i in cell}
                cell.sort(key=lambda i: (weight[i], order[i]))
                index.update({i: k for k, i in enumerate(cell)})

    for _ in range(SWEEPS):
        sweep(ranks, preds)
        sweep(reversed(ranks), succs)

    slot = {}
    for r in ranks:
        for b in bands:
            last = -1
            for i in cells[(r, b)]:
                same = [slot[p] for p in preds[i] if band[p] == b]
                want = round(sum(same) / len(same)) if same else 0
                slot[i] = max(last + 1, want)
                last = slot[i]
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


def route(graph, flow, boxes, via):
    sx, sy, sw, sh = boxes[flow.source]
    tx, ty, tw, th = boxes[flow.target]
    scy, tcy = sy + sh / 2, ty + th / 2
    first = boxes[via[0]][1] if via else tcy

    if graph.nodes[flow.source].type in GATEWAYS and abs(first - scy) >= 1:
        points = [(sx + sw / 2, sy if first < scy else sy + sh), (sx + sw / 2, first)]
    else:
        points = [(sx + sw, scy)]
    level = points[-1][1]

    for dummy in via:
        left, y = boxes[dummy][:2]
        if abs(y - level) >= 1:
            points += [(left - COL_GAP / 2, level), (left - COL_GAP / 2, y)]
            level = y

    if abs(level - tcy) >= 1:
        if graph.nodes[flow.target].type in GATEWAYS:
            return points + [(tx + tw / 2, level), (tx + tw / 2, ty if level < tcy else ty + th)]
        points += [(tx - COL_GAP / 2, level), (tx - COL_GAP / 2, tcy)]
    return points + [(tx, tcy)]


def message_route(source, target):
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    start, end = (sy + sh, ty) if ty > sy else (sy, ty + th)
    mid = (start + end) / 2
    return [(sx + sw / 2, start), (sx + sw / 2, mid), (tx + tw / 2, mid), (tx + tw / 2, end)]


def lowest(boxes, ids, flow, band_top, band_height):
    left = boxes[flow.target][0]
    right = boxes[flow.source][0] + boxes[flow.source][2]
    bottoms = [
        y + h for x, y, w, h in (boxes[i] for i in ids)
        if x < right and x + w > left and band_top <= y < band_top + band_height
    ]
    return max(bottoms) + 20


def back_route(source, target, floor):
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    gap = sx + sw + COL_GAP / 2
    return [(sx + sw, sy + sh / 2), (gap, sy + sh / 2), (gap, floor), (tx + tw / 2, floor), (tx + tw / 2, ty + th)]


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
