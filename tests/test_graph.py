from pathlib import Path

import pytest

from bpmn_gen.graph import ProcessGraph
from bpmn_gen.quality import xsd_errors

MINIMAL = (Path(__file__).parent / "fixtures" / "minimal.bpmn").read_text(encoding="utf-8")


@pytest.fixture
def g():
    g = ProcessGraph()
    g.add_container("process", "Ремонт")
    g.add_container("pool", "Сетевая компания", "Process_1")
    g.add_container("lane", "Диспетчер", "Pool_1")
    g.add_container("lane", "Бригада", "Pool_1")
    g.add_node("startEvent", "", "Process_1")
    g.add_node("userTask", "Зарегистрировать заявку", "Lane_1")
    g.add_node("userTask", "Выполнить ремонт", "Lane_2")
    g.add_flow("StartEvent_1", "UserTask_1")
    g.add_flow("UserTask_1", "UserTask_2", "да")
    return g


def test_ids(g):
    assert g.root.id == "Process_1"
    assert list(g.nodes) == ["StartEvent_1", "UserTask_1", "UserTask_2"]
    assert [f.id for f in g.flows] == ["Flow_1", "Flow_2"]


def test_navigation(g):
    assert g.outgoing("UserTask_1")[0].target == "UserTask_2"
    assert g.incoming("UserTask_2")[0].name == "да"
    assert g.find_up("UserTask_2", "lane").id == "Lane_2"
    assert g.find_up("UserTask_2", "pool").id == "Pool_1"
    assert [c.id for c in g.subcontainers("Pool_1")] == ["Lane_1", "Lane_2"]


def test_subprocess():
    g = ProcessGraph()
    g.add_container("process")
    sub = g.add_node("subProcess", "Согласование", "Process_1")
    g.add_node("task", "Шаг", sub.id)
    assert g.containers[sub.id].type == "subProcess"
    assert g.find_up("Task_1", "process", "subProcess").id == sub.id


def test_message_flow(g):
    assert g.add_flow("UserTask_1", "UserTask_2", kind="messageFlow").id == "MessageFlow_1"


def test_errors():
    g = ProcessGraph()
    g.add_container("process")
    with pytest.raises(KeyError, match="Узел"):
        g.add_flow("task_9", "task_10")
    with pytest.raises(KeyError, match="Контейнер"):
        g.add_node("task", "x", "Lane_404")


def test_xsd():
    assert xsd_errors(MINIMAL) == []
    assert xsd_errors(MINIMAL.replace("bpmn:task", "bpmn:taskk"))
