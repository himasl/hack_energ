from .graph import DATA, ProcessGraph


class Diagram:
    def __init__(self, name="Процесс"):
        self.graph = ProcessGraph()
        self.root_process_id = self.graph.add_container("process", name).id
        self.root_start_id = self._add("startEvent", "", self.root_process_id)
        self.root_end_id = self._add("endEvent", "", self.root_process_id)

    def _add(self, type, name, parent):
        return self.graph.add_node(type, name, parent).id

    def add_task(self, name, parent):
        return self._add("task", name, parent)

    def add_user_task(self, name, parent):
        return self._add("userTask", name, parent)

    def add_script_task(self, name, parent):
        return self._add("scriptTask", name, parent)

    def create_subprocess(self, name, parent):
        sub = self._add("subProcess", name, parent)
        self._add("startEvent", "", sub)
        self._add("endEvent", "", sub)
        return sub

    def add_exclusive_gateway(self, name, parent):
        return self._add("exclusiveGateway", name, parent)

    def add_parallel_gateway(self, name, parent):
        return self._add("parallelGateway", name, parent)

    def add_inclusive_gateway(self, name, parent):
        return self._add("inclusiveGateway", name, parent)

    def add_pool(self, parent, lane_names):
        pool = self.graph.add_container("pool", "", parent).id
        lanes = [self.graph.add_container("lane", name, pool).id for name in lane_names]
        return pool, lanes

    def add_group(self, name, parent):
        return self.graph.add_container("group", name, parent).id

    def set_name(self, name):
        self.graph.root.name = name

    def add_data_object(self, name, parent):
        return self._add("dataObjectReference", name, parent)

    def add_data_store(self, name, parent):
        return self._add("dataStoreReference", name, parent)

    def add_link(self, source, target, name=""):
        kind = "sequenceFlow"
        if self.graph.node(target).type in DATA:
            kind = "dataOutputAssociation"
        elif self.graph.node(source).type in DATA:
            kind = "dataInputAssociation"
        self.graph.add_flow(source, target, name, kind)
