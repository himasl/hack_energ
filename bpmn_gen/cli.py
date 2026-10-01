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
    parser.add_argument("--png", action="store_true", help="сохранить картинку рядом с .bpmn")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Файл не найден: {args.input}", file=sys.stderr)
        return 1

    source = args.input.read_text(encoding="utf-8")
    if not source.strip() and not args.code:
        print("Пустое описание процесса", file=sys.stderr)
        return 1

    try:
        result = pipeline.build_from_code(source) if args.code else pipeline.generate(source)
    except ValueError as exc:
        print(f"x {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"x {exc}", file=sys.stderr)
        return 1

    for message in result.warnings + result.fixes:
        print("!", message, file=sys.stderr)
    if result.errors:
        for message in result.errors:
            print("x", message, file=sys.stderr)
        return 1

    args.output.write_text(result.xml, encoding="utf-8")
    if not args.code:
        args.output.with_suffix(".py").write_text(result.code, encoding="utf-8")
    if args.png:
        try:
            from .export import to_png
        except ImportError:
            print("Для --png нужен playwright: pip install playwright && playwright install chromium", file=sys.stderr)
            return 1
        to_png(result.xml, args.output.with_suffix(".png"))
    print("Готово:", args.output)
    return 0
