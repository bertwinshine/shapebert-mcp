"""Solve every reference case and write docs/validation.md; needs a running FreeCAD listener.

    python tests/validation/report.py                    # write the report
    python tests/validation/report.py --freeze "reason"  # also accept these results

Closes every open FreeCAD document. Freeze only on purpose, and give the same reason
in the commit message.
"""

import argparse
import datetime
import os
import sys
import tempfile
from pathlib import Path

import cases

ROOT = cases.HERE.parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FREECAD_MCP_ALLOW_CODE", "1")
os.environ.setdefault("FREECAD_MCP_WORKDIR", str(Path(tempfile.gettempdir()) / "freecad_mcp_test_work"))
DOC = ROOT / "docs" / "validation.md"

INTRO = """# FEA validation

ShapeBert's FEA tools (`fea_setup`, `fea_run`, `fea_results`, `fea_convergence`)
solved against textbook answers. Each case lives in `tests/validation/<case>/`:
`case.json` holds the setup, the formula, the source, the tolerance and why it is
that wide; `fixture.json` holds the accepted FEA result per environment. The
analytical values are computed from the formulas in `tests/validation/cases.py`,
never typed in. Material: steel, E 210000 MPa, nu 0.3, rho 7850 kg/m3,
alpha 12e-6 1/K, k 50 W/(m K).

`pytest tests/validation` checks every value against its tolerance and, where a
result is frozen for the same FreeCAD, CalculiX, Gmsh and OS, that it has not moved
by more than 1e-6 relative (in the digits `fea_results` reports). Meshes differ
between platforms, so other environments only get the tolerance check. This file is
written by `python tests/validation/report.py` with a running FreeCAD listener.
Citations marked "edition/section to be checked" still need their edition or
section confirmed against the book. The background to each formula, and how 3D FEA
differs from it, is in `knowledge/domains/fea-mechanics.md`.
"""


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _row(case, row, results, moved) -> str:
    block = results["assumptions"]
    mesh = block["mesh"]
    frozen = "no fixture" if moved is None else ("moved" if moved else "same")
    return (
        f"| {case['title']} | {row['label']} | {row['unit']} | {_fmt(row['analytical'])} | "
        f"{_fmt(row['fea'])} | {row['error_pct']:.3f} | {row['tolerance_pct']} | "
        f"{'pass' if row['passed'] else '**fail**'} | {frozen} | {mesh['max_element_size_mm']} mm, "
        f"{mesh['nodes']} nodes, {mesh['elements']} el. | {block['elements']['type']} | "
        f"CalculiX {block['solver']['version']} | {datetime.date.today().isoformat()} |"
    )


def _sources(all_cases) -> list[str]:
    lines = ["", "## Cases, sources and tolerances", ""]
    for case in all_cases:
        lines += [f"### {case['title']} (`{case['id']}`)", "", case["description"], ""]
        for q in case["quantities"]:
            lines.append(
                f"- {q['label']}: `{q['formula']}`. Source: {q['citation']}. "
                f"Tolerance {q['tolerance_pct']} %: {q['tolerance_reason']}"
            )
        lines.append("")
    return lines


def _convergence(conv) -> list[str]:
    names = list(conv["quantities"])
    lines = [
        "",
        "## Mesh convergence (cantilever)",
        "",
        f"`fea_convergence` on the cantilever follows {', '.join(f'`{n}`' for n in names)}; the stress "
        f"leaves out everything within {conv['excluded_within_mm']} mm of the fixed end. A result has "
        f"converged when its last change is under {conv['limit_pct']} %.",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", metavar="REASON", help="accept this run's results for this environment")
    args = parser.parse_args()
    import server

    all_cases = cases.load_cases()
    table = [
        "| Case | Quantity | Unit | Analytical | FEA | Error % | Tolerance % | Result | Frozen | Mesh "
        "| Element | Solver | Date |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    failures, env = [], None
    for case in all_cases:
        results = cases.solve(server, case)
        rows = cases.compare(case, results)
        env = cases.environment(server, results)
        if args.freeze:
            cases.freeze(case["id"], env, rows, args.freeze)
        moved = cases.frozen_mismatches(case["id"], env, rows)
        table += [_row(case, row, results, moved) for row in rows]
        failures += [
            f"- {case['title']}, {r['label']}: error {r['error_pct']:.3f} %" for r in rows if not r["passed"]
        ]
        failures += [f"- {case['title']}: moved from the frozen result ({m})" for m in moved or []]
        print(f"{case['id']}: {sum(r['passed'] for r in rows)}/{len(rows)} within tolerance")
    cantilever = next(c for c in all_cases if c["id"] == "cantilever_static")
    cases.solve(server, cantilever)
    conv = cases.reply(server.fea_convergence(timeout_s=900))
    if not conv["converged"]:
        failures.append(
            f"- Cantilever mesh convergence: not converged for {', '.join(conv['not_converged'])}"
        )
    cases.fresh_document(server)

    text = [
        INTRO,
        f"Last run: {datetime.date.today().isoformat()}, {env}.",
        "",
        "## Results",
        "",
        *table,
        *_convergence(conv),
        "## Known failures",
        "",
        *(failures or ["None in the last run."]),
        *_sources(all_cases),
    ]
    DOC.write_text("\n".join(text).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
