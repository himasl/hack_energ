from dataclasses import dataclass, field


@dataclass
class Result:
    xml: str = ""
    code: str = ""
    attempts: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fixes: list = field(default_factory=list)


def build_from_code(code):
    raise NotImplementedError


def generate(text):
    raise NotImplementedError
