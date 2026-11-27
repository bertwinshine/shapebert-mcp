"""Material table and input checks for the CalculiX FEA tools (plain Python)."""

import os
import re

import shapebert_selectors as selectors

# Linear-elastic values in N, mm, MPa; thermal values in W/(m K), J/(kg K) and 1/K.
# Steel is S235 like weldments.py; the densities of the plastics match
# domains/fdm-3d-printing.md.
MATERIALS = {
    "steel": {
        "grade": "S235 (EN 10025-2, t <= 16 mm)",
        "E_mpa": 210000,
        "nu": 0.30,
        "density_kg_m3": 7850,
        "yield_mpa": 235,
        "k_w_mk": 50,
        "cp_j_kgk": 460,
        "alpha_1_k": 12e-6,
    },
    "aluminium": {
        "grade": "EN AW-6061-T6 (EN 755-2)",
        "E_mpa": 69000,
        "nu": 0.33,
        "density_kg_m3": 2700,
        "yield_mpa": 240,
        "k_w_mk": 167,
        "cp_j_kgk": 896,
        "alpha_1_k": 23.6e-6,
    },
    "PETG": {
        "grade": "typical filament datasheet, printed in XY",
        "E_mpa": 2000,
        "nu": 0.38,
        "density_kg_m3": 1270,
        "yield_mpa": 45,
        "k_w_mk": 0.2,
        "cp_j_kgk": 1200,
        "alpha_1_k": 68e-6,
        "thermal_values": "typical",
        "note": "FDM part: across the layers (Z) strength can be half of this.",
    },
    "PLA": {
        "grade": "typical filament datasheet, printed in XY",
        "E_mpa": 3500,
        "nu": 0.36,
        "density_kg_m3": 1240,
        "yield_mpa": 50,
        "k_w_mk": 0.13,
        "cp_j_kgk": 1800,
        "alpha_1_k": 68e-6,
        "thermal_values": "typical",
        "note": "FDM part: across the layers (Z) strength can be half of this; PLA creeps under steady load.",
    },
}
LOOKUP = {**{k.lower(): k for k in MATERIALS}, "aluminum": "aluminium", "alu": "aluminium"}

# Also names the solver folder in the work folder, so no dots or slashes.
ANALYSIS_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
# Finer meshes than this would run Gmsh and CalculiX for hours or out of memory.
MIN_MESH_SIZE_MM = 0.05
MAX_MESH_ELEMENTS = 2_000_000
SIMPLIFIED_NOTE = (
    "Simplified linear-elastic check: small deformations, ideal fixed faces, no contact, "
    "no welds or bolts, no fatigue or buckling. Peak stress at sharp corners next to fixed "
    "faces is a mesh singularity, not a real value. Not a substitute for a certified analysis."
)
MODAL_NOTE = (
    "Simplified modal check: ideal fixed faces (real supports are softer, so real "
    "frequencies are lower), no added masses, no damping. Not a substitute for a "
    "certified analysis or a vibration test."
)
THERMAL_NOTE = (
    "Simplified heat-conduction check: fixed face temperatures, all other faces insulated "
    "(no convection or radiation), constant material values. Not a substitute for a "
    "certified analysis."
)
THERMOMECH_NOTE = (
    "Simplified thermal-stress check: steady temperatures, linear-elastic, constant material "
    "values, ideal supports. Fully fixed faces also block the sideways thermal expansion, "
    "which gives real but local peak stresses there. Not a substitute for a certified analysis."
)
BUCKLING_NOTE = (
    "Linear (Euler) buckling: the load factor times the applied load is the ideal elastic "
    "buckling load of a perfectly straight part. Real parts with imperfections, eccentric "
    "loads, residual stress or yielding fail lower, often much lower for stocky parts. "
    "Use it with the design code's buckling rules; not a substitute for a certified analysis."
)
TRANSIENT_NOTE = (
    "Simplified transient heat-conduction check: face temperatures switched on at time 0, "
    "all other faces insulated (no convection or radiation), constant material values, "
    "fixed time steps. Not a substitute for a certified analysis."
)
NOTES = {
    "thermal_transient": TRANSIENT_NOTE,
    "buckling": BUCKLING_NOTE,
    "static": SIMPLIFIED_NOTE,
    "modal": MODAL_NOTE,
    "thermal_steady": THERMAL_NOTE,
    "thermomechanical": THERMOMECH_NOTE,
}


def material(name: str) -> dict:
    key = LOOKUP.get(name.strip().lower())
    if key is None:
        raise ValueError(f"unknown material {name!r}; choose one of {sorted(MATERIALS)}")
    return {"name": key, **MATERIALS[key]}


DEFAULT_INITIAL_TEMPERATURE_C = 20.0
# Tetrahedra that FreeCAD writes for CalculiX: type -> (order, description).
ELEMENT_TYPES = {"C3D4": (1, "4-node linear tetrahedra"), "C3D10": (2, "10-node quadratic tetrahedra")}
# Peak stress this many mesh sizes or closer to a fixed face or a sharp inside edge
# is treated as a singularity: it keeps growing as the mesh is refined.
SINGULARITY_BAND_MESH_SIZES = 2
CONVERGED_PCT = 2.0
REFINE_FACTOR = 1.5
CONVERGENCE_MESHES = 3
# Material values each analysis type uses; yield only feeds the safety factor.
USED_VALUES = {
    "static": ("E_mpa", "nu", "yield_mpa"),
    "modal": ("E_mpa", "nu", "density_kg_m3"),
    "buckling": ("E_mpa", "nu"),
    "thermal_steady": ("k_w_mk",),
    "thermal_transient": ("k_w_mk", "density_kg_m3", "cp_j_kgk"),
    "thermomechanical": ("E_mpa", "nu", "alpha_1_k", "k_w_mk", "yield_mpa"),
}
VALUE_UNITS = {
    "E_mpa": "MPa",
    "nu": "-",
    "density_kg_m3": "kg/m^3",
    "yield_mpa": "MPa",
    "k_w_mk": "W/(m K)",
    "cp_j_kgk": "J/(kg K)",
    "alpha_1_k": "1/K",
}
THERMAL_VALUES = {"k_w_mk", "cp_j_kgk", "alpha_1_k"}
RESULT_UNITS = {
    "static": {"length": "mm", "force": "N", "stress": "MPa"},
    "modal": {"length": "mm", "frequency": "Hz", "mass": "kg"},
    "buckling": {"length": "mm", "force": "N"},
    "thermal_steady": {"length": "mm", "temperature": "°C", "heat_flow": "W"},
    "thermal_transient": {"length": "mm", "temperature": "°C", "heat_flow": "W", "time": "s"},
    "thermomechanical": {"length": "mm", "force": "N", "stress": "MPa", "temperature": "°C"},
}


def material_values(mat: dict, analysis_type: str) -> dict:
    """The material values an analysis type uses, each with its unit and source."""
    out = {}
    for key in USED_VALUES[analysis_type]:
        where = f"ShapeBert FEA material table (cadkit/fea.py), {mat['name']}: {mat['grade']}"
        if key in THERMAL_VALUES and mat.get("thermal_values") == "typical":
            where += "; typical value, not from a datasheet"
        out[key] = {
            "value": mat[key],
            "unit": VALUE_UNITS[key],
            "source": {"type": "default", "where": where},
        }
    return out


def _change_pct(a, b):
    if a is None or b is None or a == 0:
        return None
    return abs(b - a) / abs(a) * 100


def convergence_summary(record: dict, current_mesh_mm: float | None) -> dict:
    """Change of each followed result from mesh to mesh; a result has converged when its
    last change is under the limit, the check when all of them have."""
    runs = record["runs"]
    quantities = {}
    for name in runs[-1]["values"]:
        values = [r["values"][name] for r in runs]
        changes = [_change_pct(a, b) for a, b in zip(values, values[1:], strict=False)]
        quantities[name] = {
            "values": values,
            "change_pct": [None if c is None else round(c, 3) for c in changes],
            "converged": changes[-1] is not None and changes[-1] < CONVERGED_PCT,
        }
    converged = [name for name, q in quantities.items() if q["converged"]]
    return {
        "quantities": quantities,
        "converged_quantities": converged,
        "not_converged": [name for name in quantities if name not in converged],
        "converged": len(converged) == len(quantities),
        "limit_pct": CONVERGED_PCT,
        "excluded_within_mm": record.get("excluded_within_mm"),
        "runs": [{k: v for k, v in r.items() if k != "values"} for r in runs],
        # Both sizes come from fea_run with the same rounding.
        "applies_to_this_mesh": runs[-1]["mesh_size_mm"] == current_mesh_mm,
    }


def _support_rows(setup: dict) -> list[dict]:
    rows = []
    for kind in ("fixed_faces", "sliding_faces"):
        for face in setup.get(kind, []):
            rows.append({"kind": kind.split("_")[0], **face})
    return rows


def _load_rows(setup: dict) -> list[dict]:
    rows = []
    for load in setup.get("loads", []):
        row = {"type": load["type"], "faces": load["face_info"]}
        if load["type"] == "force":
            row.update(value_n=load["value_n"], direction=load["direction"])
        else:
            row["value_mpa"] = load["value_mpa"]
        rows.append(row)
    return rows


def _warning(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _retry_warnings(retry: dict | None) -> list[dict]:
    if not retry:
        return []
    return [
        _warning(
            "solver_crash_retried",
            f"{retry['crash']} That was with {retry['modes_requested']} modes; solved again with "
            f"{retry['modes_solved']}, so only the lowest {retry['modes_solved']} modes are in "
            "these results. Lower frequencies are not affected.",
        )
    ]


def _element_warnings(element_type: str | None) -> list[dict]:
    order = ELEMENT_TYPES.get(element_type or "", (None,))[0]
    if order == 1:
        return [
            _warning(
                "first_order_elements",
                f"{element_type} elements are first order: too stiff in bending, so stress and "
                "deflection come out low. Use second-order (C3D10) elements, the default.",
            )
        ]
    if order is None:
        return [_warning("unknown_element_type", f"element type {element_type!r} is not a known tetrahedron")]
    return []


def _convergence_warnings(conv: dict | None, mesh_mm) -> list[dict]:
    if conv is None:
        return [
            _warning(
                "convergence_not_checked",
                "Mesh convergence not checked: run fea_convergence before calling this result final.",
            )
        ]
    if not conv["applies_to_this_mesh"]:
        finest = conv["runs"][-1]["mesh_size_mm"]
        return [
            _warning(
                "convergence_not_checked",
                f"The convergence check was made for a {finest} mm mesh, this result is from "
                f"{mesh_mm} mm: run fea_convergence again.",
            )
        ]
    if not conv["converged"]:
        details = []
        for name in conv["not_converged"]:
            last = conv["quantities"][name]["change_pct"][-1]
            details.append(
                f"{name} changed {last} %" if last is not None else f"{name} has no value to compare"
            )
        return [
            _warning(
                "mesh_not_converged",
                f"Not converged between the last two meshes (limit {CONVERGED_PCT} %): "
                f"{'; '.join(details)}. Converged: {', '.join(conv['converged_quantities']) or 'none'}. "
                "Use a smaller mesh_size_mm and check again.",
            )
        ]
    return []


def _load_warnings(flagged: list[dict], band_mm: float | None) -> list[dict]:
    out = []
    for load in flagged:
        if load["kind"] == "small loaded face":
            where = (
                f"{load['element']}, a face {load['extent_mm']} mm across, less than "
                f"2 x mesh size = {band_mm} mm"
            )
        else:
            where = f"{load['element']} ({load['kind']})"
        out.append(
            _warning(
                "load_singularity",
                f"{load['load']} acts on {where}: a concentrated load. The stress under it is "
                "singular and rises as the mesh is refined. Read stress outside "
                f"{band_mm} mm from it, or spread the load over the real contact area.",
            )
        )
    return out


def _singularity_warnings(peak: dict | None, probes: list[dict]) -> list[dict]:
    out = []
    near = (peak or {}).get("near")
    if near:
        away = peak.get("away")
        tail = (
            f" Away from those spots the peak is {away['max_von_mises_mpa']} MPa at {away['at_mm']} mm."
            if away
            else " No node lies outside that band, so the mesh is too coarse to say more."
        )
        out.append(
            _warning(
                "stress_at_singularity",
                f"The peak von Mises stress ({peak['max_von_mises_mpa']} MPa) is {near['distance_mm']} mm "
                f"from a {near['kind']}, within {peak['band_mm']} mm: a mesh singularity that grows as the "
                f"mesh is refined, not a real stress. Do not report it as the result.{tail}",
            )
        )
    for i, probe in enumerate(probes, 1):
        spot = probe.get("near_singularity")
        if spot:
            out.append(
                _warning(
                    "probe_at_singularity",
                    f"Probe {i} reads a node {spot['distance_mm']} mm from a {spot['kind']}: its stress "
                    "is not a real value there.",
                )
            )
    return out


def _defaults_warning(values: dict, setup: dict, analysis_type: str) -> list[dict]:
    named = [f"{key} {v['value']} {v['unit']}" for key, v in values.items()]
    text = f"material values from ShapeBert's table, not given by the user: {', '.join(named)}"
    if "initial_temperature_c" in setup.get("defaults", []) and analysis_type in (
        "thermomechanical",
        "thermal_transient",
    ):
        text += f"; initial (stress-free) temperature {DEFAULT_INITIAL_TEMPERATURE_C} °C"
    return [_warning("defaults_used", f"Defaults used: {text}. Report them as assumptions.")]


def assumptions(analysis_type: str, record: dict) -> dict:
    """The modelling assumptions behind one result, with warnings about its limits.

    `record` is what fea_results reads from the analysis in FreeCAD: setup, run,
    ccx, convergence runs, peak stress location and probes."""
    setup, run = record.get("setup"), record.get("run")
    if setup is None or run is None:
        return {
            "analysis_type": analysis_type,
            "warnings": [
                _warning(
                    "record_missing",
                    "This analysis has no setup or run record (made by an older ShapeBert, or not "
                    "solved yet): run fea_setup and fea_run again for the full assumptions.",
                )
            ],
        }
    mesh_mm = run["mesh_size_mm"]
    order, description = ELEMENT_TYPES.get(run["element_type"], (None, "unknown"))
    values = material_values(setup["material"], analysis_type)
    conv_record = record.get("convergence")
    conv = convergence_summary(conv_record, mesh_mm) if conv_record else None
    ccx = record.get("ccx") or {}
    block = {
        "analysis_type": analysis_type,
        "elements": {"type": run["element_type"], "order": order, "description": description},
        "mesh": {
            "max_element_size_mm": mesh_mm,
            "nodes": run["nodes"],
            "elements": run["elements"],
            "mesher": run["mesher"],
        },
        "material": {
            "name": setup["material"]["name"],
            "grade": setup["material"]["grade"],
            "values": values,
        },
        "supports": _support_rows(setup),
        "loads": _load_rows(setup),
        "temperatures": [
            {"temperature_c": t["temperature_c"], "faces": t["face_info"]}
            for t in setup.get("temperatures", [])
        ],
        "units": RESULT_UNITS[analysis_type],
        "solver": {
            "name": "CalculiX",
            "version": ccx.get("version", "unknown"),
            "threads": ccx.get("threads"),
            "mesh_s": run["mesh_s"],
            "solve_s": run["solve_s"],
        },
        "convergence": conv,
    }
    if setup.get("initial_temperature_c") is not None:
        source = (
            {"type": "default", "where": "fea_setup default when no initial_temperature_c is given"}
            if "initial_temperature_c" in setup.get("defaults", [])
            else {"type": "input", "where": "initial_temperature_c given to fea_setup"}
        )
        block["initial_temperature_c"] = {"value": setup["initial_temperature_c"], "source": source}
    if analysis_type in ("modal", "buckling"):
        block["modes"] = (run.get("retry") or {}).get("modes_solved", setup.get("modes"))
    if analysis_type == "thermal_transient":
        block["time"] = {"end_s": setup.get("time_end_s"), "step_s": setup.get("time_step_s")}
    block["warnings"] = (
        _retry_warnings(run.get("retry"))
        + _element_warnings(run["element_type"])
        + _load_warnings(record.get("flagged_loads") or [], (record.get("peak_stress") or {}).get("band_mm"))
        + _singularity_warnings(record.get("peak_stress"), record.get("probes") or [])
        + _convergence_warnings(conv, mesh_mm)
        + _defaults_warning(values, setup, analysis_type)
    )
    return block


def _faces(faces, what: str) -> list[str]:
    """Face names like 'Face1' or face selectors like 'top', in canonical form."""
    if not isinstance(faces, list) or not faces:
        raise ValueError(f"{what}: give a non-empty list of faces, e.g. ['top'] or ['Face1']")
    try:
        return selectors.parse_list(faces, lambda f: selectors.parse_face(f, allow_names=True), what)
    except selectors.SelectorError as e:
        raise ValueError(f"{what}: {e}") from None


def check_loads(loads: list[dict]) -> list[dict]:
    """Validated loads: {"type": "force", "faces", "value_n", "direction"} or
    {"type": "pressure", "faces", "value_mpa"}."""
    if not loads:
        raise ValueError("give at least one load")
    checked = []
    for i, load in enumerate(loads, 1):
        kind = load.get("type")
        faces = _faces(load.get("faces"), f"load {i}")
        if kind == "force":
            value = float(load["value_n"])
            direction = [float(c) for c in load.get("direction", [])]
            if len(direction) != 3 or not any(direction):
                raise ValueError(f"load {i}: direction must be a non-zero [x, y, z] vector")
            if value <= 0:
                raise ValueError(f"load {i}: value_n must be > 0; flip the direction instead")
            checked.append({"type": "force", "faces": faces, "value_n": value, "direction": direction})
        elif kind == "pressure":
            value = float(load["value_mpa"])
            if value == 0:
                raise ValueError(f"load {i}: value_mpa must not be 0")
            checked.append({"type": "pressure", "faces": faces, "value_mpa": value})
        else:
            raise ValueError(f"load {i}: type must be 'force' or 'pressure', not {kind!r}")
    return checked


def check_probes(probes) -> list[list[float]] | None:
    if not probes:
        return None
    if len(probes) > 50:
        raise ValueError("at most 50 probe points")
    points = [[float(c) for c in p] for p in probes]
    if any(len(p) != 3 for p in points):
        raise ValueError("each probe is a point [x, y, z] in mm")
    return points


CCX_THREADS_ENV = "FREECAD_MCP_CCX_THREADS"


def ccx_threads() -> int:
    """CalculiX thread count: 1 unless FREECAD_MCP_CCX_THREADS asks for more."""
    raw = os.environ.get(CCX_THREADS_ENV, "").strip()
    if not raw:
        return 1
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError(f"{CCX_THREADS_ENV}={raw!r}: use a whole number of 1 or more, or leave it unset")
    return int(raw)


def check_name(name: str) -> str:
    if not ANALYSIS_NAME.match(name):
        raise ValueError(f"analysis name {name!r}: use letters, digits and _ only, starting with a letter")
    return name


def check_temperatures(temperatures: list[dict]) -> list[dict]:
    """Validated fixed face temperatures: {"faces", "temperature_c"}."""
    if not temperatures:
        raise ValueError("give at least one face temperature")
    checked = []
    for i, entry in enumerate(temperatures, 1):
        faces = _faces(entry.get("faces"), f"temperature {i}")
        value = float(entry["temperature_c"])
        if value <= -273.15:
            raise ValueError(f"temperature {i}: {value} °C is below absolute zero")
        checked.append({"faces": faces, "temperature_c": value})
    return checked


MAX_TIME_STEPS = 500


def _check_time(end, step):
    if not end or not step or end <= 0 or step <= 0:
        raise ValueError("give time_end_s and time_step_s, both > 0")
    if step > end:
        raise ValueError("time_step_s must not be larger than time_end_s")
    if end / step > MAX_TIME_STEPS:
        raise ValueError(f"at most {MAX_TIME_STEPS} time steps; use a larger time_step_s")


# Inputs each analysis type requires, and those it can also take. "supports" means
# fixed_faces and/or sliding_faces.
ANALYSIS_TYPES = {
    "static": ({"supports", "loads"}, set()),
    "modal": ({"supports"}, set()),
    "thermal_steady": ({"temperatures"}, set()),
    "thermomechanical": ({"supports", "temperatures"}, {"loads"}),
    "buckling": ({"supports", "loads"}, set()),
    "thermal_transient": ({"temperatures", "time"}, set()),
}
INPUT_GROUP = {
    "fixed_faces": "supports",
    "sliding_faces": "supports",
    "loads": "loads",
    "temperatures": "temperatures",
    "time_end_s": "time",
    "time_step_s": "time",
}


def check_setup(
    analysis_type: str,
    mesh_size_mm: float,
    modes: int = 6,
    *,
    fixed_faces: list[str] | None = None,
    sliding_faces: list[str] | None = None,
    loads: list[dict] | None = None,
    temperatures: list[dict] | None = None,
    time_end_s: float | None = None,
    time_step_s: float | None = None,
) -> dict:
    """Checked inputs for one analysis type; refuses inputs it would ignore."""
    if analysis_type not in ANALYSIS_TYPES:
        raise ValueError(f"analysis_type must be one of {list(ANALYSIS_TYPES)}, not {analysis_type!r}")
    required, optional = ANALYSIS_TYPES[analysis_type]
    if not mesh_size_mm > 0:
        raise ValueError("mesh_size_mm must be > 0")
    if mesh_size_mm < MIN_MESH_SIZE_MM:
        raise ValueError(
            f"mesh_size_mm {mesh_size_mm} is below the {MIN_MESH_SIZE_MM} mm minimum; "
            "use a larger size, about a third of the thinnest wall"
        )
    given = {
        "fixed_faces": fixed_faces,
        "sliding_faces": sliding_faces,
        "loads": loads,
        "temperatures": temperatures,
        "time_end_s": time_end_s,
        "time_step_s": time_step_s,
    }
    unused = [k for k, v in given.items() if v and INPUT_GROUP[k] not in required | optional]
    if unused:
        raise ValueError(f"a {analysis_type} analysis does not use {unused}; leave them out")
    if "supports" in required and not (fixed_faces or sliding_faces):
        raise ValueError(
            "fixed_faces: give a non-empty list of faces, e.g. ['bottom'] or ['Face1'] (or sliding_faces)"
        )
    if "time" in required:
        _check_time(time_end_s, time_step_s)
    if analysis_type in ("modal", "buckling") and not 1 <= modes <= 50:
        raise ValueError("modes must be between 1 and 50")
    return {
        "fixed_faces": _faces(fixed_faces, "fixed_faces") if fixed_faces else [],
        "sliding_faces": _faces(sliding_faces, "sliding_faces") if sliding_faces else [],
        "loads": check_loads(loads or []) if "loads" in required or loads else [],
        "temperatures": check_temperatures(temperatures or []) if "temperatures" in required else [],
        "time_end_s": float(time_end_s) if "time" in required else None,
        "time_step_s": float(time_step_s) if "time" in required else None,
    }
