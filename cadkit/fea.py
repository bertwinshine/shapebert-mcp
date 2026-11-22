"""Material table and input checks for the CalculiX FEA tools (plain Python)."""

import os
import re

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

FACE_NAME = re.compile(r"^Face[1-9]\d*$")
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


def _faces(faces, what: str) -> list[str]:
    if not isinstance(faces, list) or not faces:
        raise ValueError(f"{what}: give a non-empty list of face names like ['Face1']")
    bad = [f for f in faces if not isinstance(f, str) or not FACE_NAME.match(f)]
    if bad:
        raise ValueError(f"{what}: {bad} are not face names like 'Face1'")
    return faces


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
        raise ValueError("fixed_faces: give a non-empty list of face names like ['Face1'] (or sliding_faces)")
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
