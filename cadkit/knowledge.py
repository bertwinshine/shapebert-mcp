"""Domain matching, example search and example saving over the knowledge/ folder.

Plain markdown files and a small TF-IDF ranking: enough for a few hundred
examples, readable in git, and no extra dependencies.
"""

import datetime as dt
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("FREECAD_MCP_KNOWLEDGE", PROJECT / "knowledge"))


def _extra_roots() -> list[Path]:
    # Private knowledge is layered on top of the public folder, and new examples and
    # corrections go there, so personal work never ends up in knowledge/.
    configured = os.environ.get("FREECAD_MCP_EXTRA_KNOWLEDGE")
    if configured:
        return [Path(p) for p in configured.split(os.pathsep) if p.strip()]
    default = PROJECT / "knowledge-private"
    if default.is_dir():
        return [default]
    # A plugin install replaces the project folder on every update, so the user's own
    # examples and corrections live in the work folder instead.
    work = Path(os.environ.get("FREECAD_MCP_WORKDIR") or Path.home() / "FreeCAD_MCP_work")
    return [work / "knowledge"]


EXTRA_ROOTS = _extra_roots()

WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
STOP_WORDS = set(
    "a an the and or of to in on for with by from at as is are be this that it its "
    "make create build model design part please want need into using use mm".split()
)


def _roots(root: Path | None) -> list[Path]:
    if root is not None:
        return [Path(root)]
    # Private first, so it can override a public file with the same name.
    return [*EXTRA_ROOTS, ROOT]


def _write_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return EXTRA_ROOTS[0] if EXTRA_ROOTS else ROOT


def list_domains(root: Path | None = None) -> list[dict]:
    """Rows of the table in domains/_index.md of every knowledge folder."""
    rows, seen = [], set()
    for base in _roots(root):
        index = base / "domains" / "_index.md"
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4 or not cells[2].endswith(".md") or cells[0].lower() == "domain":
                continue
            if cells[2] in seen:
                continue
            seen.add(cells[2])
            rows.append(
                {
                    "name": cells[0],
                    "triggers": [t.strip().lower() for t in cells[1].split(",") if t.strip()],
                    "file": cells[2],
                    "status": cells[3],
                }
            )
    return rows


def _matched_triggers(request: str, triggers: list[str]) -> list[str]:
    text = " " + re.sub(r"[^a-z0-9.+\- ]", " ", request.lower()) + " "
    return [t for t in triggers if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?:s|es)?(?![a-z0-9])", text)]


def match_domain(request: str, root: Path | None = None) -> dict:
    """Score domains by whole-word trigger matches and say whether the choice is clear."""
    scored = []
    for domain in list_domains(root):
        hits = _matched_triggers(request, domain["triggers"])
        if hits:
            scored.append(
                {
                    "domain": domain["name"],
                    "file": domain["file"],
                    # "sheet metal" says more than "bend", so multi-word triggers count extra.
                    "score": sum(1 + t.count(" ") for t in hits),
                    "matched": hits,
                    "status": domain["status"],
                }
            )
    scored.sort(key=lambda s: -s["score"])

    if not scored:
        advice = "none: no domain matches - use conventions.md only, or ask the user."
    elif len(scored) == 1 or scored[0]["score"] >= 2 * scored[1]["score"]:
        advice = f"single: load {scored[0]['file']}"
        if len(scored) > 1:
            advice += f" (secondary domains may also apply: {', '.join(s['file'] for s in scored[1:3])})"
    else:
        advice = (
            "ambiguous: several domains match - ASK the user which applies "
            "(or load both if the part genuinely combines them)."
        )
    return {"request": request, "matches": scored, "advice": advice}


def read_doc(relative: str, root: Path | None = None) -> str:
    """Read a markdown file from the knowledge folders; paths outside them are refused."""
    for base in _roots(root):
        base = base.resolve()
        path = (base / relative).resolve()
        if base not in path.parents:
            raise ValueError("path escapes the knowledge folder")
        if path.with_suffix(".md").is_file():
            return path.with_suffix(".md").read_text(encoding="utf-8")
    raise FileNotFoundError(f"{relative} is not in the knowledge base")


def _tokens(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOP_WORDS and len(w) > 1]


def _field(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip().strip('"') if match else ""


def _parse_example(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
    return {
        "file": path.name,
        "title": title,
        "prompt": _field(r"\*\*Prompt it answers:\*\*\s*(.+)", text),
        "domain": _field(r"\*\*Domain:\*\*\s*(.+)", text),
        "text": text,
    }


def _examples(root: Path | None) -> list[dict]:
    found = {}
    for base in _roots(root):
        for path in sorted((base / "examples").glob("*.md")):
            if not path.name.startswith("_"):
                found.setdefault(path.name, path)
    return [_parse_example(p) for p in found.values()]


def list_examples(root: Path | None = None) -> list[dict]:
    return [{k: e[k] for k in ("file", "title", "prompt", "domain")} for e in _examples(root)]


def search_examples(query: str, k: int = 3, root: Path | None = None) -> list[dict]:
    """Rank saved examples by TF-IDF; title, prompt and domain words count three times."""
    docs = []
    for example in _examples(root):
        heading = " ".join([example["title"], example["prompt"], example["domain"]])
        docs.append((example, Counter(_tokens(heading) * 3 + _tokens(example["text"]))))
    if not docs:
        return []

    doc_freq = Counter(term for _, counts in docs for term in counts)
    query_terms = set(_tokens(query))
    results = []
    for example, counts in docs:
        score = sum(
            (1 + math.log(counts[t])) * math.log(1 + len(docs) / doc_freq[t])
            for t in query_terms
            if t in counts
        )
        if score > 0:
            length = math.sqrt(sum(counts.values())) or 1.0
            results.append({key: example[key] for key in ("file", "title", "prompt", "domain")})
            results[-1]["score"] = round(score / length * 10, 3)
    results.sort(key=lambda r: -r["score"])
    return results[:k]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "example"


def _example_markdown(
    title, prompt, code, questions, domain, conventions, notes, metrics, verified_by
) -> str:
    lines = [f"# Example: {title}", "", f'**Prompt it answers:** "{prompt}"', ""]
    if domain:
        lines += [f"**Domain:** {domain}", ""]
    lines += [
        f"**Ask first if not given:** {'; '.join(questions) if questions else '(nothing critical)'}",
        "",
    ]
    if conventions:
        lines += [f"**Conventions used:** {conventions}", ""]
    lines += [
        "**Verified FreeCAD code (change the numbers at the top to fit the request):**",
        "",
        "```python",
        code.strip("\n"),
        "```",
        "",
    ]
    if metrics:
        lines += ["**Measured result:** " + ", ".join(f"{k} = {v}" for k, v in metrics.items()), ""]
    if notes:
        lines += [f"**Notes:** {notes}", ""]
    lines += [f"**Verified by:** {verified_by} ({dt.date.today().isoformat()})", ""]
    return "\n".join(lines)


def save_example(
    title: str,
    prompt: str,
    code: str,
    questions_asked: list[str] | None = None,
    domain: str = "",
    conventions_used: str = "",
    notes: str = "",
    metrics: dict | None = None,
    verified_by: str = "author",
    slug: str | None = None,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """Write a solved or corrected case to examples/<slug>.md of the writable knowledge folder."""
    base = _write_root(root)
    slug = _slug(slug or title)
    (base / "examples").mkdir(parents=True, exist_ok=True)
    path = base / "examples" / f"{slug}.md"
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path.name} exists - pass overwrite=True or choose another slug")
    if "result" not in code:
        hint = "(Code does not set `result`; consider returning validity and volume.)"
        notes = f"{notes}\n{hint}" if notes else hint

    markdown = _example_markdown(
        title, prompt, code, questions_asked or [], domain, conventions_used, notes, metrics, verified_by
    )
    path.write_text(markdown, encoding="utf-8")
    return {"saved": f"{base.name}/examples/{path.name}", "slug": slug}


def log_correction(
    prompt: str,
    what_was_wrong: str,
    fix: str,
    domain: str = "",
    example_saved: str = "",
    root: Path | None = None,
) -> dict:
    """Append a correction to corrections.jsonl in the writable knowledge folder."""
    record = {
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "prompt": prompt,
        "wrong": what_was_wrong,
        "fix": fix,
        "domain": domain,
        "example": example_saved,
    }
    base = _write_root(root)
    base.mkdir(parents=True, exist_ok=True)
    with open(base / "corrections.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"logged": record}


def correction_stats(root: Path | None = None) -> dict:
    path = _write_root(root) / "corrections.jsonl"
    if not path.exists():
        return {"corrections": 0, "by_domain": {}}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_domain = Counter(r.get("domain") or "general" for r in records)
    return {"corrections": len(records), "by_domain": dict(by_domain)}
