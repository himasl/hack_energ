from dataclasses import dataclass, field

EVENTS = {"startEvent", "endEvent"}
GATEWAYS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway"}
TASKS = {"task", "userTask", "scriptTask", "subProcess"}
CONTAINERS = {"process", "pool", "lane", "subProcess", "group"}


@dataclass
class Container:
    id: str
    type: str
    name: str = ""
    parent: str | None = None


@dataclass
class Node:
    id: str
    type: str
    name: str
    parent: str


@dataclass
class Flow:
    id: str
    source: str
    target: str
    name: str = ""
    kind: str = "sequenceFlow"


@dataclass
class Layout:
    shapes: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)


@dataclass
class ProcessGraph:
    containers: dict = field(default_factory=dict)
    nodes: dict = field(default_factory=dict)
    flows: list = field(default_factory=list)
    counters: dict = field(default_factory=dict)

    def new_id(self, type):
        prefix = type[0].upper() + type[1:]
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    def add_container(self, type, name="", parent=None, id=None):
        if parent is not None:
            self.container(parent)
        c = Container(id or self.new_id(type), type, name, parent)
        self.containers[c.id] = c
        return c

    def add_node(self, type, name, parent):
        self.container(parent)
        n = Node(self.new_id(type), type, name, parent)
        self.nodes[n.id] = n
        if type == "subProcess":
            self.add_container("subProcess", name, parent, n.id)
        return n

    def add_flow(self, source, target, name="", kind="sequenceFlow"):
        self.node(source)
        self.node(target)
        f = Flow(self.new_id("flow" if kind == "sequenceFlow" else kind), source, target, name, kind)
        self.flows.append(f)
        return f

    def node(self, id):
        if id not in self.nodes:
            raise KeyError(f"Узел '{id}' не найден: связывать можно только id, которые вернули методы DIAGRAM")
        return self.nodes[id]

    def container(self, id):
        if id not in self.containers:
            raise KeyError(f"Контейнер '{id}' не найден: используйте ROOT_PROCESS_ID, дорожку, группу или подпроцесс")
        return self.containers[id]

    @property
    def root(self):
        return next(c for c in self.containers.values() if c.parent is None)

    def incoming(self, id):
        return [f for f in self.flows if f.target == id]

    def outgoing(self, id):
        return [f for f in self.flows if f.source == id]

    def children(self, id):
        return [n for n in self.nodes.values() if n.parent == id]

    def subcontainers(self, id):
        return [c for c in self.containers.values() if c.parent == id]

    def ancestors(self, id):
        chain = []
        while id is not None:
            c = self.container(id)
            chain.append(c)
            id = c.parent
        return chain

    def find_up(self, node_id, *types):
        for c in self.ancestors(self.node(node_id).parent):
            if c.type in types:
                return c
        return None
