from .graph import DATA, DATA_FLOWS, EVENTS, GATEWAYS, Layout

TASK_SIZE = (120, 80)
EVENT_SIZE = (36, 36)
GATEWAY_SIZE = (50, 50)
DATA_OBJECT_SIZE = (36, 50)
DATA_STORE_SIZE = (50, 50)
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
SHIFT = 12


def size(node):
    if node.type in EVENTS:
        return EVENT_SIZE
    if node.type in GATEWAYS:
        return GATEWAY_SIZE
    if node.type == "dataObjectReference":
        return DATA_OBJECT_SIZE
    if node.type == "dataStoreReference":
        return DATA_STORE_SIZE
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
    steps = [n for n in nodes if n.type not in DATA]
    rank, order, back = ranking(steps, [f for f in flows if f.kind not in DATA_FLOWS])

    bands = band_list(graph, scope_id)
    pooled = bands != [None]
    band = {n.id: band_of(graph, n.id, bands) for n in nodes}

    attached = []
    for n in nodes:
        if n.type in DATA:
            links = [f.source for f in graph.incoming(n.id)] + [f.target for f in graph.outgoing(n.id)]
            owner = links[0] if links else None
            rank[n.id] = rank[owner] if owner else 0
            order[n.id] = order[owner] + 0.25 if owner else len(order)
            if owner:
                band[n.id] = band[owner]
                attached.append([owner, n.id])

    chains = {}
    for f in flows:
        if (f.source, f.target) in back or f.kind == "messageFlow" or f.kind in DATA_FLOWS:
            continue
        chain = [f.source]
        for r in range(rank[f.source] + 1, rank[f.target]):
            dummy = f"{f.id}:{r}"
            rank[dummy], band[dummy], sizes[dummy], order[dummy] = r, band[f.source], DUMMY_SIZE, order[f.source] + 0.5
            chain.append(dummy)
        chains[f.id] = chain + [f.target]
    extras = {n.id for n in nodes if n.type in DATA}
    slot = assign_slots(list(chains.values()) + attached, rank, order, band, bands, extras)

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

    grid = Grid(ids, rank, col_x, col_w)
    for i in rank:
        w, h = sizes[i]
        r, s, b = rank[i], slot[i], band[i]
        rows = slot_h[b]
        center = band_y[b] + PAD + sum(rows[:s]) + ROW_GAP * s + rows[s] / 2
        grid.rows[i] = (center - rows[s] / 2, center + rows[s] / 2)
        if i in ids:
            grid.boxes[i] = (col_x[r] + (col_w[r] - w) / 2, center - h / 2, w, h)
        else:
            grid.boxes[i] = (col_x[r], center, col_w[r], 0)
    boxes = grid.boxes

    for n in nodes:
        out.shapes[n.id] = boxes[n.id]
        if n.type == "subProcess":
            place(graph, n.id, out, *boxes[n.id][:2])

    if pooled:
        add_pools(graph, bands, band_y, band_h, out, x0, width)
    routed = {}
    for f in flows:
        if f.id in chains:
            routed[f.id] = route(graph, f, grid, chains[f.id][1:-1])
        elif f.kind == "messageFlow":
            routed[f.id] = message_route(f, grid)
    for f in flows:
        if f.id not in routed and f.kind not in DATA_FLOWS:
            options = back_routes(f, grid, band_y[band[f.target]], band_h[band[f.target]])
            routed[f.id] = best(options, f, grid, routed)
    links = {(f.source, f.target) for f in flows if f.kind in DATA_FLOWS}
    data = {
        f.id: data_routes(f, grid, offset=(SHIFT / 2 if f.kind == "dataInputAssociation" else -SHIFT / 2)
                          if (f.target, f.source) in links else 0)
        for f in flows if f.kind in DATA_FLOWS
    }
    for f in sorted((f for f in flows if f.id in data), key=lambda f: len(data[f.id])):
        routed[f.id] = best(data[f.id], f, grid, routed)
    separate(flows, routed, grid)
    for f in flows:
        out.edges[f.id] = routed[f.id]
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


def assign_slots(chains, rank, order, band, bands, extras):
    preds = {i: [] for i in rank}
    succs = {i: [] for i in rank}
    for chain in chains:
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
            cell = cells[(r, b)]
            for i in [i for i in cell if i not in extras] + [i for i in cell if i in extras]:
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


class Grid:
    def __init__(self, ids, rank, col_x, col_w):
        self.ids, self.rank, self.col_x, self.col_w = ids, rank, col_x, col_w
        self.boxes, self.rows = {}, {}

    def left_gap(self, i):
        return self.col_x[self.rank[i]] - COL_GAP / 2

    def right_gap(self, i):
        return self.col_x[self.rank[i]] + self.col_w[self.rank[i]] + COL_GAP / 2

    def clear(self, i, y1, y2):
        low, high = min(y1, y2), max(y1, y2)
        return not any(
            j != i and self.rank[j] == self.rank[i] and self.boxes[j][1] < high and self.boxes[j][1] + self.boxes[j][3] > low
            for j in self.ids
        )


def is_split(graph, node_id):
    return graph.nodes[node_id].type in GATEWAYS and len(graph.outgoing(node_id, "sequenceFlow")) > 1


def is_join(graph, node_id):
    return graph.nodes[node_id].type in GATEWAYS and len(graph.incoming(node_id, "sequenceFlow")) > 1


def route(graph, flow, grid, via):
    sx, sy, sw, sh = grid.boxes[flow.source]
    tx, ty, tw, th = grid.boxes[flow.target]
    scy, tcy = sy + sh / 2, ty + th / 2
    first = grid.boxes[via[0]][1] if via else tcy

    if is_split(graph, flow.source) and abs(first - scy) >= 1 and grid.clear(flow.source, scy, first):
        points = [(sx + sw / 2, sy if first < scy else sy + sh), (sx + sw / 2, first)]
    else:
        points = [(sx + sw, scy)]
    level = points[-1][1]

    for dummy in via:
        y = grid.boxes[dummy][1]
        if abs(y - level) >= 1:
            points += [(grid.left_gap(dummy), level), (grid.left_gap(dummy), y)]
            level = y

    if abs(level - tcy) >= 1:
        if is_join(graph, flow.target) and grid.clear(flow.target, level, tcy):
            return points + [(tx + tw / 2, level), (tx + tw / 2, ty if level < tcy else ty + th)]
        points += [(grid.left_gap(flow.target), level), (grid.left_gap(flow.target), tcy)]
    return points + [(tx, tcy)]


def message_route(flow, grid):
    sx, sy, sw, sh = grid.boxes[flow.source]
    tx, ty, tw, th = grid.boxes[flow.target]
    down = ty > sy
    start, end = (sy + sh, ty) if down else (sy, ty + th)
    near = grid.rows[flow.source][1] + ROW_GAP / 2 if down else grid.rows[flow.source][0] - ROW_GAP / 2
    far = grid.rows[flow.target][0] - ROW_GAP / 2 if down else grid.rows[flow.target][1] + ROW_GAP / 2
    gap = grid.right_gap(flow.source) - SHIFT if tx + tw / 2 >= sx + sw / 2 else grid.left_gap(flow.source) + SHIFT
    out_x, in_x = sx + sw / 2 + SHIFT / 2, tx + tw / 2 - SHIFT / 2
    return [
        (out_x, start), (out_x, near), (gap, near),
        (gap, far), (in_x, far), (in_x, end),
    ]


def data_routes(flow, grid, offset=0):
    output = flow.kind == "dataOutputAssociation"
    data, task = (flow.target, flow.source) if output else (flow.source, flow.target)
    dx, dy, dw, dh = grid.boxes[data]
    tx, ty, tw, th = grid.boxes[task]
    data_x, task_x, middle = dx + dw / 2 + offset, tx + tw / 2 + offset, dy + dh / 2 + offset
    below = ty > dy
    if grid.rank[data] == grid.rank[task]:
        top, bottom = (dy + dh, ty) if below else (dy, ty + th)
        if grid.clear(data, top, bottom):
            points = [(data_x, top), (data_x, bottom)]
            return [points[::-1] if output else points]
    near_right = tx + tw / 2 >= dx + dw / 2
    options = []
    for right in (near_right, not near_right):
        edge, gap = (dx + dw, grid.right_gap(data) + SHIFT) if right else (dx, grid.left_gap(data) - SHIFT)
        for top_side in (below, not below):
            far = grid.rows[task][0] - ROW_GAP / 2 if top_side else grid.rows[task][1] + ROW_GAP / 2
            end = ty if top_side else ty + th
            points = [(edge, middle), (gap, middle), (gap, far + offset), (task_x, far + offset), (task_x, end)]
            options.append(points[::-1] if output else points)
    return options


def data_route(flow, grid):
    return data_routes(flow, grid)[0]


def best(options, flow, grid, routed):
    def cost(points):
        segments = list(zip(points, points[1:]))
        others = [list(zip(p, p[1:])) for p in routed.values()]
        crossings = sum(1 for s in segments for line in others for t in line if crosses(s, t))
        shared = sum(1 for s in segments for line in others for t in line if collinear(s, t))
        through = sum(
            1 for s in segments for i in grid.ids
            if i not in (flow.source, flow.target) and through_box(s, grid.boxes[i])
        )
        return through * 100 + shared * 10 + crossings
    return min(options, key=cost)


NUDGES = (6, -6, 12, -12, 18, -18)


def separate(flows, routed, grid):
    ends = {f.id: (f.source, f.target) for f in flows}

    def related(a, b):
        return ends[a][0] == ends[b][0] or ends[a][1] == ends[b][1]

    def clashes(edge_id, segment):
        for other, points in routed.items():
            if other == edge_id or related(edge_id, other):
                continue
            if any(collinear(segment, t) for t in zip(points, points[1:])):
                return True
        return False

    def blocked(edge_id, points):
        source, target = ends[edge_id]
        return any(
            through_box(s, grid.boxes[i]) for s in zip(points, points[1:]) for i in grid.ids
            if i not in (source, target)
        )

    def crossings_near(edge_id, points, k):
        near = list(zip(points[k - 1:k + 3], points[k:k + 3]))
        return sum(
            1 for other, line in routed.items() if other != edge_id
            for t in zip(line, line[1:]) for s in near if crosses(s, t)
        )

    for flow in flows:
        points = routed[flow.id]
        for k in range(1, len(points) - 2):
            segment = (points[k], points[k + 1])
            if not clashes(flow.id, segment):
                continue
            vertical = points[k][0] == points[k + 1][0]
            if vertical == (points[k - 1][0] == points[k][0]) or vertical == (points[k + 1][0] == points[k + 2][0]):
                continue
            options = []
            for step in NUDGES:
                moved = list(points)
                if vertical:
                    moved[k], moved[k + 1] = (points[k][0] + step, points[k][1]), (points[k + 1][0] + step, points[k + 1][1])
                else:
                    moved[k], moved[k + 1] = (points[k][0], points[k][1] + step), (points[k + 1][0], points[k + 1][1] + step)
                if not clashes(flow.id, (moved[k], moved[k + 1])) and not blocked(flow.id, moved):
                    options.append((crossings_near(flow.id, moved, k), abs(step), moved))
            if options:
                points = routed[flow.id] = min(options, key=lambda o: o[:2])[2]


def crosses(s, t):
    (a, b), (c, d) = s, t
    if a[1] == b[1] and c[0] == d[0]:
        (a, b), (c, d) = (c, d), (a, b)
    if not (a[0] == b[0] and c[1] == d[1]):
        return False
    return min(a[1], b[1]) < c[1] < max(a[1], b[1]) and min(c[0], d[0]) < a[0] < max(c[0], d[0])


def collinear(s, t):
    (a, b), (c, d) = s, t
    axis = 1 if a[0] == b[0] == c[0] == d[0] else 0 if a[1] == b[1] == c[1] == d[1] else None
    if axis is None:
        return False
    return min(max(a[axis], b[axis]), max(c[axis], d[axis])) - max(min(a[axis], b[axis]), min(c[axis], d[axis])) > 1


def through_box(s, box):
    (a, b), (x, y, w, h) = s, (box[0] + 2, box[1] + 2, box[2] - 4, box[3] - 4)
    if a[1] == b[1]:
        return y < a[1] < y + h and max(a[0], b[0]) > x and min(a[0], b[0]) < x + w
    if a[0] == b[0]:
        return x < a[0] < x + w and max(a[1], b[1]) > y and min(a[1], b[1]) < y + h
    return False


def back_routes(flow, grid, band_top, band_height):
    sx, sy, sw, sh = grid.boxes[flow.source]
    tx, ty, tw, th = grid.boxes[flow.target]
    exit_x, entry_x = grid.right_gap(flow.source) - SHIFT / 2, grid.left_gap(flow.target)
    inside = [
        (y, y + h) for x, y, w, h in (grid.boxes[i] for i in grid.ids)
        if x < exit_x and x + w > entry_x and band_top <= y < band_top + band_height
    ]
    floor = max((b for _, b in inside), default=band_top + band_height - PAD) + ROW_GAP / 2
    ceiling = min((t for t, _ in inside), default=band_top + PAD) - ROW_GAP / 2
    return [
        [(sx + sw, sy + sh / 2), (exit_x, sy + sh / 2), (exit_x, level),
         (entry_x, level), (entry_x, ty + th / 2), (tx, ty + th / 2)]
        for level in (floor, ceiling)
    ]


def back_route(flow, grid, band_top, band_height):
    return back_routes(flow, grid, band_top, band_height)[0]


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
