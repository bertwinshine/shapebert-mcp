"""Solve every reference case and write docs/validation.md; needs a running FreeCAD listener.

    python tests/validation/report.py                    # write the report
    python tests/validation/report.py --freeze "reason"  # also accept these results
    python tests/validation/report.py --freeze "reason" --cases kirsch_plate  # only these

Closes every open FreeCAD document. Freeze only on purpose, and give the same reason
in the commit message.
"""

import argparse
import datetime
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tests/replies.py
import cases  # noqa: E402

ROOT = cases.HERE.parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FREECAD_MCP_ALLOW_CODE", "1")
os.environ.setdefault("FREECAD_MCP_WORKDIR", str(Path(tempfile.gettempdir()) / "freecad_mcp_test_work"))
DOC = ROOT / "docs" / "validation.md"

INTRO = """# FEA validation

ShapeBert's FEA tools (`fea_setup`, `fea_run`, `fea_results`, `fea_convergence`)
solved against textbook answers and published benchmarks. Each case lives in
`tests/validation/<case>/`: `case.json` holds the setup, the formula or published
value, the source, the tolerance and why it is that wide; `fixture.json` holds the
accepted FEA result per environment. The analytical values are computed from the
formulas in `tests/validation/cases.py`, never typed in; only a benchmark's published
reference value (NAFEMS) is typed in, with its citation. Material: steel,
E 210000 MPa, nu 0.3, rho 7850 kg/m3, alpha 12e-6 1/K, k 50 W/(m K).

`pytest tests/validation` checks every value against its tolerance and, where a
result is frozen for the same FreeCAD, CalculiX, Gmsh and OS, that it has not moved
by more than 1e-6 relative (in the digits `fea_results` reports). Meshes differ
between platforms, so other environments only get the tolerance check. This file is
written by `python tests/validation/report.py` with a running FreeCAD listener.
Citations marked "edition/section to be checked" still need their edition or
section confirmed against the book; cases marked "description to be checked" were
modelled from an incomplete description and say what is missing. The background to
each formula, and how 3D FEA differs from it, is in `knowledge/domains/fea-mechanics.md`.
"""

TABLE_HEAD = [
    "| Case | Quantity | Unit | Analytical | FEA | Error % | Tolerance % | Result | Frozen | Mesh "
    "| Element | Solver | Date |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
]
BENCHMARK_HEAD = [
    "| Case | Quantity | Unit | Published | Target | Hand check | FEA | Error % | Tolerance % | Result "
    "| Frozen | Mesh | Element | Solver | Date |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
]


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _today() -> str:
    return datetime.date.today().isoformat()


def _run_cells(row, results, moved) -> str:
    block = results["assumptions"]
    mesh = block["mesh"]
    frozen = "no fixture" if moved is None else ("moved" if row["id"] in moved else "same")
    return (
        f"{_fmt(row['fea'])} | {row['error_pct']:.3f} | {row['tolerance_pct']} | "
        f"{'pass' if row['passed'] else '**fail**'} | {frozen} | {mesh['max_element_size_mm']} mm, "
        f"{mesh['nodes']} nodes, {mesh['elements']} el. | {block['elements']['type']} | "
        f"CalculiX {block['solver']['version']} | {_today()} |"
    )


def _row(case, row, results, moved) -> str:
    return f"| {case['title']} | {row['label']} | {row['unit']} | {_fmt(row['analytical'])} | " + _run_cells(
        row, results, moved
    )


def _hand_cell(hand) -> str:
    return "none applies" if hand is None else f"{_fmt(hand['value'])} (`{hand['case']}`)"


def _benchmark_row(case, row, results, moved) -> str:
    return (
        f"| {case['title']} | {row['label']} | {row['unit']} | {row['published']} | "
        f"{_fmt(row['analytical'])} | {_hand_cell(row['hand'])} | " + _run_cells(row, results, moved)
    )


def _not_modelled_rows(case) -> list[str]:
    return [
        f"| {case['title']} | {q['label']} | {q['unit']} | {q['published']} | {_fmt(q['published_value'])} | "
        f"none applies | not modelled |  | {q['tolerance_pct']} | **not run** |  |  |  |  | {_today()} |"
        for q in case["quantities"]
    ]


def _sources(all_cases) -> list[str]:
    lines = ["", "## Cases, sources and tolerances", ""]
    for case in all_cases:
        lines += [f"### {case['title']} (`{case['id']}`)", "", case["description"], ""]
        if "description_check" in case:
            lines += [f"Description to be checked: {case['description_check']}", ""]
        if "not_modelled" in case:
            lines += [f"Not modelled: {case['not_modelled']}", ""]
        for q in case["quantities"]:
            hand = cases.HAND_CHECKS.get(case["id"], {}).get(q["id"])
            extra = f" Hand check: `calc_hand_check` `{hand[0]}`." if hand else ""
            published = f" Published: {q['published']}." if "published" in q else ""
            mesh = f" Mesh {q['mesh_size_mm']} mm." if "mesh_size_mm" in q else ""
            lines.append(
                f"- {q['label']}: `{q['formula']}`.{published} Source: {q['citation']}.{mesh}{extra} "
                f"Tolerance {q['tolerance_pct']} %: {q['tolerance_reason']}"
            )
        lines.append("")
    return lines


def _convergence(case, conv) -> list[str]:
    names = list(conv["quantities"])
    lines = [
        f"### {case['title']}",
        "",
        f"`fea_convergence` follows {', '.join(f'`{n}`' for n in names)}; the stress leaves out "
        f"everything within {conv['excluded_within_mm']} mm of a fixed face, sharp inside edge or "
        f"concentrated load. A result has converged when its last change is under {conv['limit_pct']} %.",
        "",
        "| Mesh | Nodes | Elements | " + " | ".join(f"{n} | Change" for n in names) + " |",
        "|---|---|---|" + "---|---|" * len(names),
    ]
    for i, run in enumerate(conv["runs"]):
        cells = []
        for n in names:
            q = conv["quantities"][n]
            change = q["change_pct"][i - 1] if i else None
            cells += [_fmt(q["values"][i]), "" if change is None else f"{change:.3f} %"]
        lines.append(
            f"| {run['mesh_size_mm']} mm | {run['nodes']} | {run['elements']} | " + " | ".join(cells) + " |"
        )
    converged = ", ".join(conv["converged_quantities"]) or "none"
    lines += ["", f"Converged: {converged}. Not converged: {', '.join(conv['not_converged']) or 'none'}.", ""]
    return lines


def _solve_cases(server, all_cases, freeze, freeze_ids):
    """Solve every modelled case; returns (results table, benchmark table, failures, env).
    Cases that are not modelled get table rows, not failures."""
    table, bench, failures, env = [*TABLE_HEAD], [*BENCHMARK_HEAD], [], None
    for case in all_cases:
        if "not_modelled" in case:
            bench += _not_modelled_rows(case)
            continue
        runs = cases.solve_all(server, case)
        rows = cases.compare(case, runs, server)
        env = cases.environment(server, runs[case["fea_setup"]["mesh_size_mm"]])
        if freeze and (not freeze_ids or case["id"] in freeze_ids):
            cases.freeze(case["id"], env, rows, freeze)
        mismatches = cases.frozen_mismatches(case["id"], env, rows)
        moved = None if mismatches is None else {m.split(":")[0] for m in mismatches}
        make_row = _benchmark_row if case.get("benchmark") else _row
        target = bench if case.get("benchmark") else table
        target += [make_row(case, row, runs[row["mesh_size_mm"]], moved) for row in rows]
        failures += [
            f"- {case['title']}, {r['label']}: error {r['error_pct']:.3f} %" for r in rows if not r["passed"]
        ]
        failures += [f"- {case['title']}: moved from the frozen result ({m})" for m in mismatches or []]
        print(f"{case['id']}: {sum(r['passed'] for r in rows)}/{len(rows)} within tolerance")
    return table, bench, failures, env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", metavar="REASON", help="accept this run's results for this environment")
    parser.add_argument("--cases", nargs="+", metavar="ID", help="with --freeze: freeze only these cases")
    args = parser.parse_args()
    import server

    all_cases = cases.load_cases()
    table, bench, failures, env = _solve_cases(server, all_cases, args.freeze, args.cases)
    conv_lines = []
    for case in cases.modelled(all_cases):
        if not case.get("convergence"):
            continue
        cases.solve(server, case)
        conv = cases.reply(server.fea_convergence(timeout_s=900))
        if not conv["converged"]:
            failures.append(
                f"- {case['title']}, mesh convergence: not converged for {', '.join(conv['not_converged'])}"
            )
        conv_lines += _convergence(case, conv)
    cases.fresh_document(server)

    text = [
        INTRO,
        f"Last run: {_today()}, {env}.",
        "",
        "## Results",
        "",
        *table,
        "",
        "## Published benchmarks",
        "",
        "FEA against the published target, with `calc_hand_check` where a closed form applies. "
        "The error is against the target.",
        "",
        *bench,
        "",
        "## Mesh convergence",
        "",
        *conv_lines,
        "## Known failures",
        "",
        *(failures or ["None in the last run."]),
        "",
        "Not run, because the tools cannot set them up yet:",
        "",
        *[f"- {c['title']}: {c['not_modelled']}" for c in all_cases if "not_modelled" in c],
        *_sources(all_cases),
    ]
    DOC.write_text("\n".join(text).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
