"""Face and edge selectors ("top", "bore", "edges of top", ...) resolved from geometry.

Parsing is plain Python. Resolution and RoundEdges run inside FreeCAD, which stores
RoundEdges in saved documents as shapebert_selectors.RoundEdges, so keep that name.
"""

import math
import re

MAX_SELECTORS = 20
MAX_TEXT = 100
# Fixed tolerances keep the result the same for the same part on every rebuild.
LIN_TOL_MM = 1e-3
DIR_TOL = 1e-6  # 1 - cos(angle) for "the same direction"
AREA_REL_TOL = 1e-6
EDGE_PROBE_MM = 0.01

SIDES = {
    "top": "+Z",
    "bottom": "-Z",
    "+x": "+X",
    "-x": "-X",
    "+y": "+Y",
    "-y": "-Y",
    "+z": "+Z",
    "-z": "-Z",
}
SIDE_NAMES = {"+Z": "top", "-Z": "bottom", "+X": "+X", "-X": "-X", "+Y": "+Y", "-Y": "-Y"}
SIDE_VECTORS = {
    "+X": (1, 0, 0),
    "-X": (-1, 0, 0),
    "+Y": (0, 1, 0),
    "-Y": (0, -1, 0),
    "+Z": (0, 0, 1),
    "-Z": (0, 0, -1),
}
FACE_NAME = re.compile(r"face([1-9]\d{0,5})")
NUMBER = r"(\d+(?:\.\d*)?|\.\d+)"
CYLINDER = re.compile(rf"(?:cylindrical faces?|cylinders?) (radius|diameter) {NUMBER}(?: ?mm)?")
FACE_FORMS = (
    "top, bottom, +X, -X, +Y, -Y, +Z, -Z (optionally followed by 'face' or 'side'), "
    "'largest planar face', 'cylindrical faces radius 4', 'cylindrical faces diameter 8', 'bore', "
    "'inclined planar faces'"
)
EDGE_FORMS = (
    "all, top, bottom, vertical, 'vertical edges', 'concave edges', "
    "'edges of <face selector>' (e.g. 'edges of top face', 'edges of bore')"
)


class SelectorError(ValueError):
    """A selector that is malformed, or matches nothing or more than one candidate."""

    def __init__(self, message, candidates=None):
        super().__init__(message)
        self.candidates = candidates or []


def _words(text):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise SelectorError(f"a selector must be text of 1 to {MAX_TEXT} characters")
    if any(ord(c) < 32 for c in text):
        raise SelectorError("a selector must not contain control characters")
    return " ".join(text.lower().split())


def parse_face(text, allow_names=False):
    """Canonical form of one face selector, e.g. 'top face' -> 'top', '+x side' -> '+X'."""
    words = _words(text)
    name = FACE_NAME.fullmatch(words)
    if name:
        if not allow_names:
            raise SelectorError(f"{text!r}: face numbers change when the part changes; use a selector")
        return f"Face{name.group(1)}"
    side = re.sub(r" (face|faces|side)$", "", words)
    if side in SIDES:
        return SIDE_NAMES[SIDES[side]]
    if words in ("largest planar face", "largest flat face"):
        return "largest planar face"
    if words in ("bore", "the bore"):
        return "bore"
    if words in ("inclined planar faces", "inclined faces", "inclined planar face"):
        return "inclined planar faces"
    cyl = CYLINDER.fullmatch(words)
    if cyl:
        value = float(cyl.group(2))
        if not 0 < value < 1e6:
            raise SelectorError(f"{text!r}: the {cyl.group(1)} must be greater than 0")
        return f"cylindrical faces {cyl.group(1)} {value:.10g}"
    raise SelectorError(f"unknown face selector {text!r}; use one of: {FACE_FORMS}")


def parse_edges(text):
    """Canonical form of one edge selector, e.g. 'edges of the top face' -> 'edges of top'."""
    words = _words(text)
    if words in ("all", "all edges"):
        return "all"
    if words in ("vertical", "vertical edges"):
        return "vertical"
    if words in ("concave", "concave edges"):
        return "concave edges"
    if words in ("top", "bottom"):
        return f"edges of {words}"
    if words.startswith("edges of "):
        target = words[len("edges of ") :].removeprefix("the ")
        return f"edges of {parse_face(target)}"
    if re.fullmatch(r"edge\d+", words):
        raise SelectorError(f"{text!r} is an edge number; give a list of names like ['Edge1'] instead")
    raise SelectorError(f"unknown edge selector {text!r}; use one of: {EDGE_FORMS}")


def parse_list(values, parse, what):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_SELECTORS:
        raise SelectorError(f"{what}: give 1 to {MAX_SELECTORS} selectors")
    out = []
    for value in values:
        canonical = parse(value)
        if canonical not in out:
            out.append(canonical)
    return out


def _r(x, digits=3):
    value = round(float(x), digits)
    return 0.0 if value == 0 else value


def _v(vec, digits=4):
    return [_r(vec.x, digits), _r(vec.y, digits), _r(vec.z, digits)]


def _canonical_axis(axis):
    """The same line direction either way round: first non-zero component positive."""
    for c in (axis.x, axis.y, axis.z):
        if abs(c) > DIR_TOL:
            return axis * (1 if c > 0 else -1)
    return axis


def _surface_kind(face):
    name = face.Surface.__class__.__name__
    return {
        "Plane": "plane",
        "Cylinder": "cylinder",
        "Cone": "cone",
        "Sphere": "sphere",
        "Toroid": "torus",
        "BSplineSurface": "bspline",
        "BezierSurface": "bezier",
        "SurfaceOfExtrusion": "extrusion",
        "SurfaceOfRevolution": "revolution",
    }.get(name, name.lower())


def _mid_normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)


def describe_face(face, index):
    """Name, surface type, centre, area, bbox and the type's own data (normal, axis...)."""
    bb = face.BoundBox
    info = {
        "name": f"Face{index}",
        "type": _surface_kind(face),
        "centre_mm": _v(face.CenterOfMass, 3),
        "area_mm2": _r(face.Area, 3),
        "bbox_mm": {
            "min": [_r(bb.XMin), _r(bb.YMin), _r(bb.ZMin)],
            "max": [_r(bb.XMax), _r(bb.YMax), _r(bb.ZMax)],
        },
    }
    surface = face.Surface
    if info["type"] == "plane":
        info["normal"] = _v(_mid_normal(face))
    elif info["type"] in ("cylinder", "cone"):
        axis = _canonical_axis(surface.Axis)
        info["axis"] = _v(axis)
        info["axis_point_mm"] = _v(_axis_point(surface.Center, axis), 3)
        if info["type"] == "cylinder":
            info["radius_mm"] = _r(surface.Radius)
            info["internal"] = _is_internal(face)
        else:
            info["half_angle_deg"] = _r(math.degrees(surface.SemiAngle))
    elif info["type"] == "sphere":
        info["radius_mm"] = _r(surface.Radius)
        info["sphere_centre_mm"] = _v(surface.Center, 3)
    return info


def _axis_point(point, axis):
    """Where the axis line passes closest to the origin, so one line has one point."""
    return point - axis * point.dot(axis)


def _is_internal(face):
    """A hole wall: the outward normal points towards the cylinder axis."""
    u0, u1, v0, v1 = face.ParameterRange
    u, v = (u0 + u1) / 2, (v0 + v1) / 2
    point, normal = face.valueAt(u, v), face.normalAt(u, v)
    surface = face.Surface
    offset = point - surface.Center
    radial = offset - surface.Axis * offset.dot(surface.Axis)
    return normal.dot(radial) < 0


def _close(a, b, tol=LIN_TOL_MM):
    return abs(a - b) <= tol


def _same_line(a, b):
    axis_a, axis_b = _canonical_axis(a.Surface.Axis), _canonical_axis(b.Surface.Axis)
    if axis_a.dot(axis_b) < 1 - DIR_TOL:
        return False
    return (
        _axis_point(a.Surface.Center, axis_a) - _axis_point(b.Surface.Center, axis_b)
    ).Length <= LIN_TOL_MM


def _faces_of(shape, predicate):
    return [(i, f) for i, f in enumerate(shape.Faces, 1) if predicate(f)]


def _summaries(shape, indexed, limit=12):
    return [describe_face(f, i) for i, f in indexed[:limit]]


def _side(shape, axis_name):
    import FreeCAD as App

    direction = App.Vector(*SIDE_VECTORS[axis_name])
    planes = _faces_of(shape, lambda f: _surface_kind(f) == "plane")
    facing = [(i, f) for i, f in planes if _mid_normal(f).dot(direction) >= 1 - DIR_TOL]
    if not facing:
        raise SelectorError(
            f"no flat face faces {axis_name}; the flat faces are listed as candidates",
            _summaries(shape, planes),
        )
    extreme = max(f.CenterOfMass.dot(direction) for _, f in facing)
    return [i for i, f in facing if _close(f.CenterOfMass.dot(direction), extreme)]


def _largest_planar(shape):
    planes = _faces_of(shape, lambda f: _surface_kind(f) == "plane")
    if not planes:
        raise SelectorError("the part has no flat faces")
    largest = max(f.Area for _, f in planes)
    tied = [(i, f) for i, f in planes if f.Area >= largest * (1 - AREA_REL_TOL)]
    if len(tied) > 1:
        raise SelectorError(
            f"'largest planar face' is ambiguous: {len(tied)} flat faces have {largest:.3f} mm^2; "
            "pick one with a side selector such as top or bottom",
            _summaries(shape, tied),
        )
    return [tied[0][0]]


def _cylinders(shape, kind, value):
    radius = value / 2 if kind == "diameter" else value
    cylinders = _faces_of(shape, lambda f: _surface_kind(f) == "cylinder")
    found = [i for i, f in cylinders if _close(f.Surface.Radius, radius)]
    if not found:
        radii = sorted({_r(f.Surface.Radius) for _, f in cylinders})
        raise SelectorError(
            f"no cylindrical face has {kind} {value:g} mm; the part's cylinder radii are {radii} mm",
            _summaries(shape, cylinders),
        )
    return found


def _group_lines(indexed):
    """(number, face) pairs grouped by cylinder: faces on one axis line with one radius."""
    lines = []
    for i, f in indexed:
        for line in lines:
            if _same_line(line[0][1], f) and _close(line[0][1].Surface.Radius, f.Surface.Radius):
                line.append((i, f))
                break
        else:
            lines.append([(i, f)])
    return lines


def holes(shape, numbers):
    """The holes among the given faces: internal cylinders, one entry per hole even
    when FreeCAD splits its wall into several faces. Each has its face names,
    diameter, axis and axis point (where the axis passes closest to the origin)."""
    walls = [(n, shape.Faces[n - 1]) for n in numbers]
    walls = [(n, f) for n, f in walls if _surface_kind(f) == "cylinder" and _is_internal(f)]
    out = []
    for line in _group_lines(walls):
        surface = line[0][1].Surface
        axis = _canonical_axis(surface.Axis)
        out.append(
            {
                "faces": [f"Face{n}" for n, _ in line],
                "diameter": 2 * surface.Radius,
                "axis": axis,
                "axis_point": _axis_point(surface.Center, axis),
            }
        )
    return out


def _inclined(shape):
    import FreeCAD as App

    axes = [App.Vector(*v) for v in SIDE_VECTORS.values()]
    planes = _faces_of(shape, lambda f: _surface_kind(f) == "plane")
    found = [i for i, f in planes if all(_mid_normal(f).dot(a) < 1 - DIR_TOL for a in axes)]
    if not found:
        raise SelectorError(
            "no flat face is inclined: every flat face faces along X, Y or Z (no chamfer)",
            _summaries(shape, planes),
        )
    return found


def _bore(shape):
    holes = _faces_of(shape, lambda f: _surface_kind(f) == "cylinder" and _is_internal(f))
    if not holes:
        raise SelectorError("the part has no bore (no internal cylindrical face)")
    largest = max(f.Surface.Radius for _, f in holes)
    lines = _group_lines([(i, f) for i, f in holes if _close(f.Surface.Radius, largest)])
    if len(lines) > 1:
        raise SelectorError(
            f"'bore' is ambiguous: {len(lines)} separate holes have the largest radius "
            f"{largest:.3f} mm; use 'cylindrical faces radius {largest:g}' for all of them",
            _summaries(shape, [line[0] for line in lines]),
        )
    return [i for i, _ in lines[0]]


def resolve_face(shape, selector):
    """1-based face numbers for one canonical face selector (see parse_face)."""
    if selector.startswith("Face"):
        index = int(selector[4:])
        if index > len(shape.Faces):
            raise SelectorError(f"{selector} does not exist; the part has {len(shape.Faces)} faces")
        return [index]
    side = {v: k for k, v in SIDE_NAMES.items()}.get(selector)
    if side:
        return _side(shape, side)
    if selector == "largest planar face":
        return _largest_planar(shape)
    if selector == "bore":
        return _bore(shape)
    if selector == "inclined planar faces":
        return _inclined(shape)
    kind, value = selector.split()[-2:]
    return _cylinders(shape, kind, float(value))


def resolve_faces(shape, selectors):
    """Face numbers for several selectors, as {selector: [numbers]}, in the given order."""
    return {s: sorted(resolve_face(shape, parse_face(s, allow_names=True))) for s in selectors}


def _is_seam(shape, edge):
    faces = shape.ancestorsOfType(edge, _part().Face)
    return all(f.isSame(faces[0]) for f in faces)


def _part():
    import Part

    return Part


def _usable_edges(shape):
    """(number, edge) of every real edge: no seams of round faces, no collapsed edges."""
    return [(i, e) for i, e in enumerate(shape.Edges, 1) if e.Length > LIN_TOL_MM and not _is_seam(shape, e)]


def _is_vertical(edge):
    bb = edge.BoundBox
    return bb.XLength < LIN_TOL_MM and bb.YLength < LIN_TOL_MM and bb.ZLength > LIN_TOL_MM


def _normal_at(face, point):
    u, v = face.Surface.parameter(point)
    return face.normalAt(u, v)


def _is_concave(shape, edge):
    """Inside corner: the material angle between the two faces is over 180 degrees.

    Outward normals n1, n2: a point just off the edge along n1 - n2 lies inside the
    material only where the faces meet in an inside corner.
    """
    faces = []
    for face in shape.ancestorsOfType(edge, _part().Face):
        if not any(face.isSame(f) for f in faces):
            faces.append(face)
    if len(faces) != 2:
        return False
    first, last = edge.ParameterRange
    point = edge.valueAt((first + last) / 2)
    n1, n2 = (_normal_at(f, point) for f in faces)
    if n1.dot(n2) >= 1 - DIR_TOL:
        return False
    probe = point + (n1 - n2).normalize() * EDGE_PROBE_MM
    return shape.isInside(probe, LIN_TOL_MM / 10, True)


def _edges_matching(shape, selector, usable):
    if selector == "all":
        return [i for i, _ in usable]
    if selector == "vertical":
        return [i for i, e in usable if _is_vertical(e)]
    if selector == "concave edges":
        return [i for i, e in usable if _is_concave(shape, e)]
    faces = [shape.Faces[n - 1] for n in resolve_face(shape, selector[len("edges of ") :])]
    return [i for i, e in usable if any(any(e.isSame(fe) for fe in f.Edges) for f in faces)]


def resolve_edges(shape, selectors):
    """Sorted 1-based edge numbers matching any of the canonical edge selectors."""
    usable = _usable_edges(shape)
    numbers = set()
    for selector in selectors:
        found = _edges_matching(shape, selector, usable)
        if not found:
            counts = {s: len(_edges_matching(shape, s, usable)) for s in ("all", "vertical", "concave edges")}
            raise SelectorError(f"no edges match {selector!r}; edge counts on this part: {counts}")
        numbers.update(found)
    return sorted(numbers)


class RoundEdges:
    """Fillet or chamfer whose edges are chosen by selectors again on every recompute."""

    def __init__(self, obj, kind, base, size, selectors):
        obj.addProperty("App::PropertyLink", "Base", "RoundEdges", "Solid to round")
        obj.addProperty("App::PropertyEnumeration", "Kind", "RoundEdges", "Fillet or chamfer")
        obj.addProperty("App::PropertyLength", "Size", "RoundEdges", "Fillet radius or chamfer size")
        obj.addProperty("App::PropertyStringList", "Selectors", "RoundEdges", "Edge selectors")
        obj.addProperty(
            "App::PropertyStringList", "ResolvedEdges", "RoundEdges", "Edges found at the last recompute"
        )
        obj.setEditorMode("ResolvedEdges", 1)
        obj.Kind = ["Fillet", "Chamfer"]
        obj.Kind = kind
        obj.Base = base
        obj.Size = size
        obj.Selectors = list(selectors)
        obj.Proxy = self
        if obj.ViewObject is not None:
            # 0 selects FreeCAD's own view provider; without a Proxy the GUI sets no
            # display mode and the result is never drawn.
            obj.ViewObject.Proxy = 0

    def execute(self, obj):
        shape = obj.Base.Shape
        selectors = [parse_edges(s) for s in obj.Selectors]
        numbers = resolve_edges(shape, selectors)
        edges = [shape.Edges[n - 1] for n in numbers]
        size = obj.Size.Value
        obj.Shape = shape.makeFillet(size, edges) if obj.Kind == "Fillet" else shape.makeChamfer(size, edges)
        names = [f"Edge{n}" for n in numbers]
        if list(obj.ResolvedEdges) != names:
            obj.ResolvedEdges = names

    def dumps(self):
        return None

    def loads(self, state):
        return None
