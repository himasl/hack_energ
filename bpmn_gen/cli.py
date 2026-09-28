import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import pipeline


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(prog="bpmn_gen")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("out.bpmn"))
    parser.add_argument("--code", action="store_true", help="на входе готовый код, без LLM")
    args = parser.parse_args()

    source = args.input.read_text(encoding="utf-8")
    result = pipeline.build_from_code(source) if args.code else pipeline.generate(source)

    for message in result.warnings + result.fixes:
        print("!", message, file=sys.stderr)
    if result.errors:
        for message in result.errors:
            print("x", message, file=sys.stderr)
        return 1

    args.output.write_text(result.xml, encoding="utf-8")
    args.output.with_suffix(".py").write_text(result.code, encoding="utf-8")
    print("Готово:", args.output)
    return 0
