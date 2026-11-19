"""Run the benchmark through headless Claude Code and score each result in FreeCAD.

Needs FreeCAD with the listener running, a logged-in `claude` CLI and .mcp.json.
Every run costs API usage, so try a single case first:

    python bench/run_claude.py --cases L1-box
    python bench/run_claude.py --variant bare --repeat 3
    python bench/run_claude.py --set v2
"""

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from score import CASES, score_ask, score_build_quality, score_case  # noqa: E402

import server  # noqa: E402

# The benchmark drives FreeCAD with free-form code, so it needs the code tool on.
os.environ.setdefault("FREECAD_MCP_ALLOW_CODE", "1")

PROMPT_SUFFIX = (
    "\n\n(Benchmark run: when the part is finished, make sure the final part is ONE "
    "top-level object named 'Result'. If a critical value is missing, ask instead "
    "of building.)"
)

# "bare" is the ablation baseline: bridge tools only, run outside the project so
# CLAUDE.md and the knowledge base aren't picked up. It also runs bare_server.py,
# so the model doesn't even see the tools it isn't allowed to call.
TOOLS = {
    "full": "mcp__shapebert",
    "bare": "mcp__shapebert__run_freecad_code,mcp__shapebert__get_document_info",
}
CSV_FIELDS = [
    "case",
    "repeat",
    "variant",
    "model",
    "score",
    "seconds",
    "turns",
    "cost_usd",
    "structure_score",
    "structure_issues",
    "edit_score",
    "error",
    "checks",
    "edit_checks",
    "final_text",
]


def reset_freecad():
    server.run_freecad_code(
        "for n in list(App.listDocuments()):\n    App.closeDocument(n)\n"
        "App.newDocument('Bench'); App.setActiveDocument('Bench')"
    )


def count_objects():
    return len(server._fc("doc_info").get("objects", []))


def bare_mcp_config(folder):
    """Copy .mcp.json into `folder`, pointing the server at bench/bare_server.py."""
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    config["mcpServers"]["shapebert"]["args"] = [str(HERE / "bare_server.py")]
    path = Path(folder) / "mcp_bare.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def ask_claude(prompt, variant, model):
    if variant == "full":
        cwd, mcp_config = ROOT, ROOT / ".mcp.json"
    else:
        cwd = Path(tempfile.mkdtemp(prefix="bench_bare_"))
        mcp_config = bare_mcp_config(cwd)
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    cmd += ["--mcp-config", str(mcp_config), "--allowedTools", TOOLS[variant]]
    if model:
        cmd += ["--model", model]
    # Claude's replies contain characters like the degree sign; Windows would decode
    # them with its legacy code page and crash, so read the output as UTF-8.
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200
    )
    output = proc.stdout or ""
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"result": (output or proc.stderr or "")[-2000:], "is_error": True}


class UsageLimitReachedError(Exception):
    pass


def run_case(case, variant, model):
    reset_freecad()
    started = time.time()
    reply = ask_claude(case["prompt"] + PROMPT_SUFFIX, variant, model)
    seconds = time.time() - started
    text = reply.get("result", "")
    # A run that hits the plan limit before doing any work says nothing about the
    # assistant, so stop instead of recording a zero.
    if reply.get("is_error") and "limit" in text.lower() and not reply.get("total_cost_usd"):
        raise UsageLimitReachedError(text.strip())

    if case.get("should_ask"):
        result = score_ask(case, text, count_objects())
    else:
        result = score_case(case, "Result")
        result.update(score_build_quality(case))
    result.update(
        {
            "variant": variant,
            "model": model or "default",
            "seconds": round(seconds, 1),
            "turns": reply.get("num_turns"),
            "cost_usd": reply.get("total_cost_usd"),
            "error": bool(reply.get("is_error")),
            "final_text": text[:500],
        }
    )
    return result


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: json.dumps(row.get(k)) if k.endswith(("checks", "issues")) else row.get(k)
                    for k in CSV_FIELDS
                }
            )


def summary(rows, title):
    groups = {}
    for row in rows:
        case = CASES[row["case"]]
        prefix = "v2 " if case.get("set") == "v2" else ""
        group = prefix + ("ASK" if case.get("should_ask") else f"L{case['level']}")
        groups.setdefault(group, []).append(row["score"])

    lines = [f"# {title}", "", "| Group | Runs | Mean score | pass@1 (score = 1) |", "|---|---|---|---|"]
    for group, scores in sorted(groups.items()):
        mean = sum(scores) / len(scores)
        perfect = 100 * sum(1 for s in scores if s == 1) / len(scores)
        lines.append(f"| {group} | {len(scores)} | {mean:.2f} | {perfect:.0f}% |")

    mean_score = sum(r["score"] for r in rows) / len(rows)
    cost = sum(r["cost_usd"] or 0 for r in rows)
    mean_seconds = sum(r["seconds"] for r in rows) / len(rows)
    lines += [
        "",
        f"Overall mean score **{mean_score:.2f}**, total cost ${cost:.2f}, mean {mean_seconds:.0f} s per case.",
    ]
    structure = [r["structure_score"] for r in rows if r.get("structure_score") is not None]
    edits = [r["edit_score"] for r in rows if r.get("edit_score") is not None]
    if structure:
        lines.append(
            f"Model structure (0-100): mean **{sum(structure) / len(structure):.0f}** over {len(structure)} parts."
        )
    if edits:
        passed = sum(1 for e in edits if e == 1)
        lines.append(
            f"Editability: mean **{sum(edits) / len(edits):.2f}**, {passed} of {len(edits)} parts followed a size change."
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", default="full", choices=sorted(TOOLS))
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--set", default="all", choices=["all", "v1", "v2"], help="which case set to run")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    rows = []
    selected = args.cases or [cid for cid, c in CASES.items() if args.set in ("all", c.get("set", "v1"))]
    try:
        for case_id in selected:
            for repeat in range(1, args.repeat + 1):
                row = run_case(CASES[case_id], args.variant, args.model)
                row["repeat"] = repeat
                rows.append(row)
                cost = row.get("cost_usd") or 0
                print(f"{case_id:<24} run {repeat}  score {row['score']:.2f}  {row['seconds']}s  ${cost:.2f}")
    except UsageLimitReachedError as e:
        done = {r["case"] for r in rows}
        print(f"\nStopped: {e}\nNot run yet: {' '.join(c for c in selected if c not in done)}")
    if not rows:
        return

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    csv_path = out_dir / f"{args.variant}_{stamp}.csv"
    write_csv(rows, csv_path)
    report = summary(rows, f"Benchmark {stamp} ({args.variant}, model {args.model or 'default'})")
    (out_dir / f"{args.variant}_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
