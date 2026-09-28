from .graph import EVENTS, GATEWAYS

TASK_SIZE = (100, 80)
EVENT_SIZE = (36, 36)
GATEWAY_SIZE = (50, 50)


def size(node):
    if node.type in EVENTS:
        return EVENT_SIZE
    if node.type in GATEWAYS:
        return GATEWAY_SIZE
    return TASK_SIZE


def layout(graph):
    raise NotImplementedError
