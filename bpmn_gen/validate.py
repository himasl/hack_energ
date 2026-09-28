from dataclasses import dataclass, field


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fixes: list = field(default_factory=list)


def validate(graph):
    raise NotImplementedError
