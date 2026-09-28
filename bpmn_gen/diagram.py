from .graph import ProcessGraph


class Diagram:
    def __init__(self, name="Процесс"):
        self.graph = ProcessGraph()
        self.root_process_id = ""
        self.root_start_id = ""
        self.root_end_id = ""

    def add_task(self, name, parent):
        raise NotImplementedError

    def add_user_task(self, name, parent):
        raise NotImplementedError

    def add_script_task(self, name, parent):
        raise NotImplementedError

    def create_subprocess(self, name, parent):
        raise NotImplementedError

    def add_exclusive_gateway(self, name, parent):
        raise NotImplementedError

    def add_parallel_gateway(self, name, parent):
        raise NotImplementedError

    def add_inclusive_gateway(self, name, parent):
        raise NotImplementedError

    def add_pool(self, parent, lane_names):
        raise NotImplementedError

    def add_group(self, name, parent):
        raise NotImplementedError

    def add_link(self, source, target, name=""):
        raise NotImplementedError
