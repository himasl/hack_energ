import json
import time
from pathlib import Path

from . import pipeline
from .export import to_png
from .quality import analyze

COLUMNS = [
    ("name", "Процесс"),
    ("valid", "XSD"),
    ("participants", "Участники"),
    ("tasks", "Задачи"),
    ("gateways", "Шлюзы"),
    ("flows", "Связи"),
    ("overlaps", "Наложения"),
    ("edges_through_shapes", "Стрелки сквозь фигуры"),
    ("edge_crossings", "Пересечения стрелок"),
    ("warnings", "Предупреждения"),
    ("attempts", "Попытки"),
    ("seconds", "Время, с"),
]


def find_inputs(folder, code):
    pattern = "*.py" if code else "*.txt"
    return sorted(p for p in folder.rglob(pattern) if not p.name.startswith("output"))


def case_name(path, folder):
    if path.stem in ("input", "code"):
        folder_name = path.parent.relative_to(folder).as_posix()
        return path.parent.name if folder_name == "." else folder_name
    return str(path.relative_to(folder).with_suffix(""))


def run(folder, out, code=False, png=False):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in find_inputs(folder, code):
        name = case_name(path, folder)
        target = out / f"{name.replace('/', '__')}.bpmn"
        started = time.time()
        source = path.read_text(encoding="utf-8")
        try:
            result = pipeline.build_from_code(source) if code else pipeline.generate(source)
        except Exception as e:
            result = pipeline.Result(errors=[f"{type(e).__name__}: {e}"])
        row = {"name": name, "seconds": round(time.time() - started, 2), "attempts": result.attempts}
        row["warnings"] = len(result.warnings)
        row["messages"] = result.errors + result.warnings
        if result.xml:
            target.write_text(result.xml, encoding="utf-8")
            if not code:
                target.with_suffix(".py").write_text(result.code, encoding="utf-8")
            if png:
                try:
                    to_png(result.xml, target.with_suffix(".png"))
                except Exception as e:
                    row["messages"].append(f"PNG не сохранён: {e}")
            row.update(analyze(result.xml))
        else:
            row["valid"] = None
        rows.append(row)
    write_report(rows, out)
    return rows


def summary(rows):
    built = [r for r in rows if "tasks" in r]
    return {
        "total": len(rows),
        "built": len(built),
        "valid": sum(bool(r["valid"]) for r in rows),
        "overlaps": sum(r["overlaps"] for r in built),
        "edges_through_shapes": sum(r["edges_through_shapes"] for r in built),
        "edge_crossings": sum(r["edge_crossings"] for r in built),
        "seconds": round(sum(r["seconds"] for r in rows), 2),
    }


def cell(value):
    if value is True:
        return "да"
    if value is False:
        return "нет"
    return "—" if value is None else str(value)


def write_report(rows, out):
    total = summary(rows)
    lines = [
        "# Отчёт о качестве диаграмм",
        "",
        f"Построено: {total['built']} из {total['total']}, валидных по XSD: {total['valid']}. "
        f"Наложений: {total['overlaps']}, стрелок сквозь фигуры: {total['edges_through_shapes']}, "
        f"пересечений стрелок: {total['edge_crossings']}. Время: {total['seconds']} с.",
        "",
        "| " + " | ".join(title for _, title in COLUMNS) + " |",
        "| " + " | ".join("---" for _ in COLUMNS) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(row.get(key)) for key, _ in COLUMNS) + " |")
    notes = [(row["name"], m) for row in rows for m in row["messages"]]
    if notes:
        lines += ["", "## Ошибки и предупреждения", ""]
        lines += [f"- **{name}**: {message}" for name, message in notes]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "report.json").write_text(
        json.dumps({"summary": total, "diagrams": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
