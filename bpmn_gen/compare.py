import re

from .graph import DATA, EVENTS, TASKS
from .sandbox import run_code
from .validate import validate

LINKS = ("sequenceFlow", "messageFlow")


def graph_from_code(code):
    run = run_code(code)
    if run.error:
        return None
    validate(run.graph)
    return run.graph


def stems(name):
    return {w for w in re.findall(r"\w+", name.lower()) if len(w) > 2}


def root(word):
    return word[:min(5, max(3, len(word) - 1))]


def same_word(a, b):
    return root(a) in b or root(b) in a


def similarity(a, b):
    a, b = stems(a), stems(b)
    if not a or not b:
        return 0.0
    hits = sum(1 for w in a if any(same_word(w, v) for v in b))
    return 2 * hits / (len(a) + len(b))


def match(reference, generated, threshold=0.6):
    pairs = sorted(
        ((similarity(r, g), i, j) for i, r in enumerate(reference) for j, g in enumerate(generated)),
        reverse=True,
    )
    found, used = {}, set()
    for score, i, j in pairs:
        if score < threshold:
            break
        if i not in found and j not in used:
            found[i] = j
            used.add(j)
    return found


def participants(graph):
    return [c.name for c in graph.containers.values() if c.type == "lane" and c.name]


def steps(graph):
    return [n for n in graph.nodes.values() if n.type in TASKS]


def links(graph):
    pairs = set()
    for step in steps(graph):
        seen, queue = {step.id}, [f.target for f in graph.outgoing(step.id) if f.kind in LINKS]
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            node = graph.nodes[current]
            if node.type in TASKS:
                pairs.add((step.id, current))
            elif node.type not in EVENTS and node.type not in DATA:
                queue += [f.target for f in graph.outgoing(current) if f.kind in LINKS]
    return pairs


def share(found, total):
    return round(100 * found / total) if total else None


def compare(generated, reference):
    ref_people, gen_people = participants(reference), participants(generated)
    people = match(ref_people, gen_people)

    ref_steps, gen_steps = steps(reference), steps(generated)
    found = match([s.name for s in ref_steps], [s.name for s in gen_steps])
    twin = {ref_steps[i].id: gen_steps[j].id for i, j in found.items()}

    ref_links, gen_links = links(reference), links(generated)
    kept = sum(1 for a, b in ref_links if (twin.get(a), twin.get(b)) in gen_links)

    return {
        "participants_found": share(len(people), len(ref_people)),
        "steps_found": share(len(found), len(ref_steps)),
        "steps_precise": share(len(found), len(gen_steps)),
        "links_found": share(kept, len(ref_links)),
        "missing_participants": [p for i, p in enumerate(ref_people) if i not in people],
        "missing_steps": [s.name for i, s in enumerate(ref_steps) if i not in found],
    }


def main():
    import sys
    from pathlib import Path

    if len(sys.argv) != 3:
        print("python -m bpmn_gen.compare <папка с результатами> <папка с эталонами>", file=sys.stderr)
        return 1
    results, references = Path(sys.argv[1]), Path(sys.argv[2])
    print("| Процесс | Участники, % | Шаги, % | Связи, % | Точность шагов, % | Нет из эталона |")
    print("| --- | --- | --- | --- | --- | --- |")
    for reference in sorted(references.glob("*/code.py")):
        name = reference.parent.name
        code = results / f"{name}.py"
        generated = graph_from_code(code.read_text(encoding="utf-8")) if code.exists() else None
        if generated is None:
            print(f"| {name} | — | — | — | — | схема не построена |")
            continue
        found = compare(generated, graph_from_code(reference.read_text(encoding="utf-8")))
        missing = ", ".join(found["missing_participants"] + found["missing_steps"]) or "—"
        print(f"| {name} | {found['participants_found']} | {found['steps_found']} | "
              f"{found['links_found']} | {found['steps_precise']} | {missing} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
