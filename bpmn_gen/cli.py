import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import batch, pipeline
from .export import PNG_HELP, png_available, to_png


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(prog="bpmn_gen")
    parser.add_argument("input", type=Path, help="файл с описанием или кодом; папка — пакетный прогон")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--code", action="store_true", help="на входе готовый код, без LLM")
    parser.add_argument("--png", action="store_true", help="сохранить картинку рядом с .bpmn")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="сколько процессов папки генерировать одновременно")
    parser.add_argument("--model", help="модель вместо LLM_MODEL; для папки можно несколько через запятую — сравнение моделей")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Файл не найден: {args.input}", file=sys.stderr)
        return 1

    if args.png and not png_available():
        print(PNG_HELP, file=sys.stderr)
        return 1

    models = [m.strip() for m in (args.model or "").split(",") if m.strip()]
    if len(models) == 1:
        os.environ["LLM_MODEL"] = models[0]

    if args.input.is_dir() and len(models) > 1 and not args.code:
        out = args.output or Path("out")
        results = batch.compare_models(args.input, out, models, args.png, args.jobs)
        for r in results:
            print(f"{r['model']}: построено {r['built']}, валидных {r['valid']}, попыток в среднем {r['attempts']}")
        print("Сравнение:", out / "models.md")
        return 0

    if args.input.is_dir():
        out = args.output or Path("out")
        rows = batch.run(args.input, out, args.code, args.png, jobs=args.jobs)
        total = batch.summary(rows)
        print(f"Построено: {total['built']} из {total['total']}, валидных: {total['valid']}, отчёт: {out / 'report.md'}")
        return 0 if total["valid"] == total["total"] else 1

    args.output = args.output or Path("out.bpmn")
    source = args.input.read_text(encoding="utf-8")
    if not source.strip() and not args.code:
        print("Пустое описание процесса", file=sys.stderr)
        return 1

    try:
        result = pipeline.build_from_code(source, pipeline.text_near(args.input)) if args.code else pipeline.generate(source)
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
            to_png(result.xml, args.output.with_suffix(".png"))
        except Exception as exc:
            print(f"x Не удалось сохранить PNG: {exc}", file=sys.stderr)
            print(PNG_HELP, file=sys.stderr)
            return 1
    print("Готово:", args.output)
    return 0
