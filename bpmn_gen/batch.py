import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def build(path, code):
    started = time.time()
    source = path.read_text(encoding="utf-8")
    try:
        result = pipeline.build_from_code(source) if code else pipeline.generate(source)
    except Exception as e:
        result = pipeline.Result(errors=[f"{type(e).__name__}: {e}"])
    return result, round(time.time() - started, 2)


def run(folder, out, code=False, png=False, label="", jobs=1):
    out.mkdir(parents=True, exist_ok=True)
    inputs = find_inputs(folder, code)
    rows = [None] * len(inputs)
    with ThreadPoolExecutor(max_workers=max(jobs, 1)) as pool:
        futures = {pool.submit(build, path, code): i for i, path in enumerate(inputs)}
        for done, future in enumerate(as_completed(futures), 1):
            i = futures[future]
            result, seconds = future.result()
            rows[i] = describe(case_name(inputs[i], folder), result, seconds, out, code, png)
            status = "построено" if result.xml else "не построено"
            print(f"[{done}/{len(inputs)}] {label}{rows[i]['name']}: {status}, попыток {result.attempts}, {seconds} с", flush=True)
    write_report(rows, out)
    return rows


def describe(name, result, seconds, out, code, png):
    target = out / f"{name.replace('/', '__')}.bpmn"
    row = {"name": name, "seconds": seconds, "attempts": result.attempts}
    row["warnings"] = len(result.warnings)
    row["blocking"] = len(result.blocking)
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
    return row


MODEL_COLUMNS = [
    ("model", "Модель"),
    ("built", "Построено"),
    ("valid", "Валидно по XSD"),
    ("attempts", "Попыток в среднем"),
    ("blocking", "Логических ошибок осталось"),
    ("warnings", "Предупреждений"),
    ("overlaps", "Наложения"),
    ("edge_crossings", "Пересечения стрелок"),
    ("seconds", "Время прогона, с"),
    ("failure", "Почему не построено"),
]


def first_failure(rows):
    failed = [r for r in rows if not r.get("tasks")]
    if not failed:
        return None
    message = next((m for m in failed[0]["messages"]), "")
    return f"{len(failed)} шт.: {message[:120]}".replace("|", "/")


def compare_models(folder, out, models, png=False, jobs=1):
    results = []
    for model in models:
        os.environ["LLM_MODEL"] = model
        started = time.time()
        rows = run(folder, out / model.replace("/", "_").replace(":", "_"), png=png, label=f"{model} · ", jobs=jobs)
        wall = round(time.time() - started, 2)
        total = summary(rows)
        results.append({
            "model": model,
            "built": f"{total['built']} из {total['total']}",
            "valid": total["valid"],
            "attempts": round(sum(r["attempts"] for r in rows) / max(len(rows), 1), 2),
            "blocking": sum(r.get("blocking", 0) for r in rows),
            "warnings": sum(r["warnings"] for r in rows),
            "overlaps": total["overlaps"],
            "edge_crossings": total["edge_crossings"],
            "seconds": wall,
            "failure": first_failure(rows),
        })
    lines = [
        "# Сравнение моделей",
        "",
        f"Набор: `{folder}`, процессов: {len(rows) if models else 0}. Отчёт по каждой модели — в её папке.",
        "",
        "| " + " | ".join(title for _, title in MODEL_COLUMNS) + " |",
        "| " + " | ".join("---" for _ in MODEL_COLUMNS) + " |",
    ]
    lines += ["| " + " | ".join(cell(r[key]) for key, _ in MODEL_COLUMNS) + " |" for r in results]
    out.mkdir(parents=True, exist_ok=True)
    (out / "models.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "models.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


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
