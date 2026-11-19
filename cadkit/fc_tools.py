"""Functions that run inside FreeCAD.

server.py sends this file's source (after gear_profile.py) along with a single
call, so nothing has to be installed in FreeCAD's Python. Every public function returns a JSON-safe dict.
"""

import math
import os
import re

import FreeCAD as App
import Part

# Part.OCCError and Base.FreeCADError both subclass RuntimeError.
FREECAD_ERRORS = (RuntimeError, ValueError)

VIEWS = {
    "isometric": "viewIsometric",
    "front": "viewFront",
    "top": "viewTop",
    "right": "viewRight",
    "left": "viewLeft",
    "rear": "viewRear",
    "bottom": "viewBottom",
    "axonometric": "viewAxonometric",
}
SKIPPED_PROPERTIES = {"Shape", "Proxy", "ExpressionEngine", "Label2", "Visibility"}


def _doc(create=False):
    doc = App.ActiveDocument
    if doc is None and create:
        doc = App.newDocument("Unnamed")
    if doc is None:
        raise RuntimeError("No active FreeCAD document. Create or open one first.")
    return doc


def _obj(name):
    doc = _doc()
    obj = doc.getObject(name)
    if obj is None:
        by_label = doc.getObjectsByLabel(name)
        obj = by_label[0] if by_label else None
    if obj is None:
        existing = [o.Name for o in doc.Objects][:40]
        raise RuntimeError(f"Object {name!r} not found. Existing: {existing}")
    return obj


def _shape(name_or_path):
    if os.path.isfile(str(name_or_path)):
        shape = Part.Shape()
        shape.read(str(name_or_path))
        return shape
    obj = _obj(name_or_path)
    if not _has_shape(obj):
        raise RuntimeError(f"{name_or_path} has no shape")
    return obj.Shape


def _r(x, digits=3):
    return round(float(x), digits)


def _vec(v):
    return [_r(v.x), _r(v.y), _r(v.z)]


def _size(bb):
    return [_r(bb.XLength), _r(bb.YLength), _r(bb.ZLength)]


def _bbox(bb):
    return {
        "min_mm": [_r(bb.XMin), _r(bb.YMin), _r(bb.ZMin)],
        "max_mm": [_r(bb.XMax), _r(bb.YMax), _r(bb.ZMax)],
        "size_mm": _size(bb),
    }


def _has_shape(obj):
    # FEM mesh objects have a Shape property that links to the part instead, and FEM
    # analyses and datum lines carry an empty shape with an invalid bounding box.
    shape = getattr(obj, "Shape", None)
    return isinstance(shape, Part.Shape) and not shape.isNull() and shape.BoundBox.isValid()


def _is_top_level(obj):
    return not any(_has_shape(parent) for parent in obj.InList)


def _top_level_shapes(doc):
    return [o for o in doc.Objects if _has_shape(o) and _is_top_level(o)]


def _center_of_mass(shape):
    solids = shape.Solids
    if len(solids) == 1:
        return solids[0].CenterOfMass
    total = sum(s.Volume for s in solids) or 1.0
    center = App.Vector()
    for s in solids:
        center += s.CenterOfMass * (s.Volume / total)
    return center


def doc_info():
    doc = App.ActiveDocument
    if doc is None:
        return {"document": None, "objects": [], "note": "no active document"}
    rows = []
    for o in doc.Objects:
        row = {"name": o.Name, "label": o.Label, "type": o.TypeId, "top_level": _is_top_level(o)}
        if _has_shape(o):
            row["valid"] = bool(o.Shape.isValid())
            row["solids"] = len(o.Shape.Solids)
            row["volume_mm3"] = _r(o.Shape.Volume)
            row["size_mm"] = _size(o.Shape.BoundBox)
        rows.append(row)
    return {"document": doc.Name, "file": doc.FileName or None, "objects": rows}


def _plain(value):
    if hasattr(value, "Value") and hasattr(value, "Unit"):
        return str(value)
    if isinstance(value, App.Placement):
        rot = value.Rotation
        return {
            "base_mm": _vec(value.Base),
            "rotation_axis": _vec(rot.Axis),
            "rotation_deg": _r(math.degrees(rot.Angle)),
        }
    if isinstance(value, App.Vector):
        return _vec(value)
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 20:
        return [getattr(x, "Name", str(x)) for x in value]
    return str(value)[:200]


def inspect_object(name):
    obj = _obj(name)
    props = {}
    for prop in obj.PropertiesList:
        if prop in SKIPPED_PROPERTIES:
            continue
        try:
            props[prop] = _plain(obj.getPropertyByName(prop))
        except (AttributeError, RuntimeError):
            continue
    return {
        "name": obj.Name,
        "label": obj.Label,
        "type": obj.TypeId,
        "properties": props,
        "expressions": dict(obj.ExpressionEngine),
        "depends_on": [x.Name for x in obj.OutList],
        "used_by": [x.Name for x in obj.InList],
    }


def measure(name, density_kg_m3=None):
    shape = _shape(name)
    out = {
        "object": name,
        "volume_mm3": _r(shape.Volume),
        "area_mm2": _r(shape.Area),
        "bbox": _bbox(shape.BoundBox),
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
    }
    if shape.Solids:
        out["center_of_mass_mm"] = _vec(_center_of_mass(shape))
    if density_kg_m3:
        out["density_kg_m3"] = density_kg_m3
        out["mass_kg"] = _r(shape.Volume * 1e-9 * float(density_kg_m3), 6)

    # Grouping cylinders by diameter is how callers check "4 holes of 6.6 mm";
    # the axis distances let them check a bolt circle as well.
    center = shape.BoundBox.Center
    by_diameter, axes = {}, []
    for face in shape.Faces:
        surface = face.Surface
        if surface.__class__.__name__ != "Cylinder":
            continue
        dia = _r(2 * surface.Radius, 2)
        by_diameter[dia] = by_diameter.get(dia, 0) + 1
        offset = surface.Center - center
        radial = offset - surface.Axis * offset.dot(surface.Axis)
        axes.append(
            {"diameter_mm": dia, "axis_from_center_mm": _r(radial.Length, 2), "axis": _vec(surface.Axis)}
        )
    out["cylindrical_faces_by_diameter_mm"] = {str(d): n for d, n in sorted(by_diameter.items())}
    out["cylinders"] = axes[:60]
    return out


def check_geometry(name):
    shape = _shape(name)
    issues = []
    valid = bool(shape.isValid())
    if not valid:
        issues.append("shape.isValid() is False")
    try:
        shape.check(True)
    except FREECAD_ERRORS as e:
        issues.append(f"BOP check: {str(e).strip()[:500]}")

    open_shells = sum(1 for shell in shape.Shells if not shell.isClosed())
    tiny_edges = sum(1 for edge in shape.Edges if edge.Length < 1e-3)
    if not shape.Solids:
        issues.append(f"no solids (only {len(shape.Shells)} shells / {len(shape.Faces)} faces)")
    if open_shells:
        issues.append(f"{open_shells} open shell(s) - not watertight")
    if len(shape.Solids) > 1:
        issues.append(f"{len(shape.Solids)} separate solids - fuse them if this should be one part")
    if tiny_edges:
        issues.append(f"{tiny_edges} edges shorter than 0.001 mm (can break fillets/meshing)")
    return {
        "object": name,
        "valid": valid and not issues,
        "solids": len(shape.Solids),
        "shells": len(shape.Shells),
        "faces": len(shape.Faces),
        "issues": issues,
    }


def screenshot(path, view="isometric", width=900, height=700, fit=True):
    if not App.GuiUp:
        raise RuntimeError("Screenshots need the FreeCAD GUI (listener is headless).")
    import FreeCADGui as Gui

    if Gui.ActiveDocument is None:
        raise RuntimeError("No active document to view.")
    view3d = Gui.ActiveDocument.ActiveView
    if not hasattr(view3d, "saveImage"):
        raise RuntimeError(
            "The active tab is not a 3D view (e.g. TechDraw page). Switch to the 3D view first."
        )

    # With animation on, saveImage captures the camera halfway through the turn.
    animated = view3d.isAnimationEnabled()
    view3d.setAnimationEnabled(False)
    try:
        getattr(view3d, VIEWS.get(view, "viewIsometric"))()
        if fit:
            view3d.fitAll()
        Gui.updateGui()
    finally:
        view3d.setAnimationEnabled(animated)
    view3d.saveImage(path, int(width), int(height), "White")
    return {"path": path, "view": view}


def _mesh_of(objs):
    import MeshPart

    meshes = [
        MeshPart.meshFromShape(
            Shape=o.Shape, LinearDeflection=0.05, AngularDeflection=math.radians(10), Relative=False
        )
        for o in objs
    ]
    combined = meshes[0]
    for mesh in meshes[1:]:
        combined.addMesh(mesh)
    return combined


def export_shapes(names, path):
    objs = [_obj(n) for n in names] if names else _top_level_shapes(_doc())
    if not objs:
        raise RuntimeError("Nothing to export.")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    ext = os.path.splitext(path)[1].lower()
    if ext in (".brep", ".brp"):
        Part.makeCompound([o.Shape for o in objs]).exportBrep(path)
    elif ext in (".step", ".stp", ".iges", ".igs"):
        import Import

        Import.export(objs, path)
    elif ext in (".stl", ".3mf", ".obj", ".amf", ".ply"):
        _mesh_of(objs).write(path)
    else:
        raise RuntimeError(f"Unsupported format {ext} (use step, iges, brep, stl, 3mf, obj)")
    return {"path": path, "objects": [o.Name for o in objs], "bytes": os.path.getsize(path)}


def save_document(path=None):
    doc = _doc()
    if path:
        doc.saveAs(path)
    elif doc.FileName:
        doc.save()
    else:
        raise RuntimeError("Document was never saved; give a path ending in .FCStd")
    return {"saved": doc.FileName}


def import_file(path):
    doc = _doc(create=True)
    before = {o.Name for o in doc.Objects}
    if os.path.splitext(path)[1].lower() in (".stl", ".obj", ".3mf", ".ply"):
        import Mesh

        Mesh.insert(path, doc.Name)
    else:
        import Import

        Import.insert(path, doc.Name)
    doc.recompute()
    return {"imported": [o.Name for o in doc.Objects if o.Name not in before]}


def _cell_content(value):
    # "100 mm" must be stored as the formula "=100 mm"; plain text would be a string
    # cell, and a bare number has no unit, so "Params.L + 2 mm" would fail.
    if isinstance(value, str) and not value.startswith("="):
        return f"={value}"
    return str(value)


def set_parameters(params, sheet="Params"):
    """Write ``params`` into a spreadsheet as aliased cells (bind with ``Params.<name>``).

    Give lengths with units ("100 mm"); plain numbers stay unitless (counts, factors).
    """
    doc = _doc(create=True)
    sh = doc.getObject(sheet) or doc.addObject("Spreadsheet::Sheet", sheet)

    rows = {}
    next_row = 1
    while sh.getContents(f"A{next_row}"):
        rows[sh.getContents(f"A{next_row}").lstrip("'")] = next_row
        next_row += 1

    rejected = []
    for key, value in params.items():
        row = rows.get(key)
        if row is None:
            row = next_row
            next_row += 1
            sh.set(f"A{row}", key)
        sh.set(f"B{row}", _cell_content(value))
        try:
            sh.setAlias(f"B{row}", key)
        except ValueError:  # unit names (W, V, N, mm) and reserved words
            rejected.append(key)

    sh.recompute()
    doc.recompute()
    out = {
        "sheet": sh.Name,
        "set": {k: v for k, v in params.items() if k not in rejected},
        "objects_with_errors_after_recompute": [o.Name for o in doc.Objects if "Invalid" in (o.State or [])],
    }
    if rejected:
        out["ok"] = False
        out["rejected_aliases"] = rejected
        out["error"] = (
            f"FreeCAD refused these alias names: {', '.join(rejected)}. Single letters such as W, V or N "
            "are unit names; use descriptive names like PlateW or PlateL."
        )
    return out


def compare_shapes(candidate, reference):
    """IoU = Vol(common) / Vol(fuse), plus volume, size and centre-of-mass differences."""
    a, b = _shape(candidate), _shape(reference)
    union = a.fuse(b).Volume
    iou = a.common(b).Volume / union if union > 0 else 0.0
    center_a = a.Solids[0].CenterOfMass if a.Solids else a.BoundBox.Center
    center_b = b.Solids[0].CenterOfMass if b.Solids else b.BoundBox.Center
    return {
        "iou": _r(iou, 4),
        "volume_candidate_mm3": _r(a.Volume),
        "volume_reference_mm3": _r(b.Volume),
        "volume_error_pct": _r(100 * (a.Volume - b.Volume) / b.Volume, 2) if b.Volume else None,
        "bbox_candidate_mm": _size(a.BoundBox),
        "bbox_reference_mm": _size(b.BoundBox),
        "center_offset_mm": _r((center_a - center_b).Length),
    }


def _outer_faces(shape, z):
    """Faces bounded by the outer loops of a horizontal slice at height ``z``.

    A thin-walled hull slices into an outer and an inner skin loop. Keeping only the
    outer loop counts the air inside the boat as displaced volume, which is what
    actually floats it. A catamaran gives two outer loops.
    """
    try:
        wires = shape.slice(App.Vector(0, 0, 1), z)
    except FREECAD_ERRORS:
        return []
    faces = []
    for wire in wires:
        if not wire.isClosed():
            continue
        try:
            face = Part.Face(wire)
        except FREECAD_ERRORS:
            continue
        if face.Area > 1e-6:
            faces.append(face)

    outer = []
    for face in sorted(faces, key=lambda f: f.Area, reverse=True):
        if not any(big.isInside(face.CenterOfMass, 1e-6, True) for big in outer):
            outer.append(face)
    return outer


def _volume_table(shape, slices):
    """Cumulative displaced volume and its first moment about the keel, per slice height."""
    z0, z1 = shape.BoundBox.ZMin, shape.BoundBox.ZMax
    eps = (z1 - z0) * 1e-4  # slicing exactly at the keel or sheer gives degenerate faces
    heights = [z0 + eps + (z1 - z0 - 2 * eps) * i / slices for i in range(slices + 1)]
    areas = [sum(f.Area for f in _outer_faces(shape, z)) for z in heights]

    volume, moment = [0.0], [0.0]
    for i in range(1, len(heights)):
        dz = heights[i] - heights[i - 1]
        volume.append(volume[-1] + 0.5 * (areas[i] + areas[i - 1]) * dz)
        arm = areas[i] * (heights[i] - z0) + areas[i - 1] * (heights[i - 1] - z0)
        moment.append(moment[-1] + 0.5 * arm * dz)
    return heights, volume, moment


def _interpolate(xs, ys, x):
    for i in range(1, len(xs)):
        if xs[i] >= x:
            span = xs[i] - xs[i - 1]
            t = (x - xs[i - 1]) / span if span else 0.0
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def _waterplane(shape, z):
    """Waterplane area, transverse second moment I_T, and waterline length/beam."""
    faces = _outer_faces(shape, z)
    if not faces:
        return 0.0, 0.0, 0.0, 0.0
    area = sum(f.Area for f in faces)
    length_along_x = shape.BoundBox.XLength >= shape.BoundBox.YLength
    cx = sum(f.CenterOfMass.x * f.Area for f in faces) / area
    cy = sum(f.CenterOfMass.y * f.Area for f in faces) / area

    # MatrixOfInertia of a planar face is taken about its own centroid; shift each
    # face to the combined centroid (parallel-axis theorem) to get the whole I_T.
    i_t = 0.0
    for f in faces:
        m = f.MatrixOfInertia
        if length_along_x:
            i_t += m.A11 + f.Area * (f.CenterOfMass.y - cy) ** 2
        else:
            i_t += m.A22 + f.Area * (f.CenterOfMass.x - cx) ** 2

    bb = Part.makeCompound(faces).BoundBox
    if length_along_x:
        return area, i_t, bb.XLength, bb.YLength
    return area, i_t, bb.YLength, bb.XLength


def hydrostatics(name, mass_kg=None, draft_mm=None, rho_kg_m3=1000.0, kg_mm=None, slices=80):
    """Float a hull with Z up. Give ``mass_kg`` to find the draft, or ``draft_mm``."""
    shape = _shape(name)
    z0, z1 = shape.BoundBox.ZMin, shape.BoundBox.ZMax
    heights, volume, moment = _volume_table(shape, slices)
    rho = float(rho_kg_m3)
    max_disp_kg = volume[-1] * 1e-9 * rho
    out = {
        "object": name,
        "rho_kg_m3": rho,
        "hull_depth_mm": _r(z1 - z0),
        "max_displacement_kg": _r(max_disp_kg, 2),
    }

    if mass_kg is not None:
        target = float(mass_kg) / rho * 1e9
        if target >= volume[-1]:
            out["floats"] = False
            out["note"] = "Load exceeds buoyancy of the closed hull up to the sheer."
            return out
        waterline = _interpolate(volume, heights, target)
    elif draft_mm is not None:
        waterline = z0 + float(draft_mm)
    else:
        raise RuntimeError("Give mass_kg or draft_mm.")

    displaced = _interpolate(heights, volume, waterline)
    kb = _interpolate(heights, moment, waterline) / displaced if displaced > 0 else 0.0
    area, i_t, lwl, bwl = _waterplane(shape, waterline)
    bm = i_t / displaced if displaced > 0 else 0.0
    draft = waterline - z0

    out.update(
        {
            "floats": True,
            "draft_mm": _r(draft, 1),
            "freeboard_mm": _r(z1 - waterline, 1),
            "displaced_volume_m3": _r(displaced * 1e-9, 5),
            "displacement_kg": _r(displaced * 1e-9 * rho, 2),
            "reserve_buoyancy_kg": _r(max_disp_kg - displaced * 1e-9 * rho, 2),
            "waterline_length_mm": _r(lwl, 1),
            "waterline_beam_mm": _r(bwl, 1),
            "waterplane_area_m2": _r(area * 1e-6, 4),
            "Cb": _r(displaced / (lwl * bwl * draft), 3) if lwl and bwl and draft else None,
            "Cwp": _r(area / (lwl * bwl), 3) if lwl and bwl else None,
            "KB_mm": _r(kb, 1),
            "BM_mm": _r(bm, 1),
            "KM_mm": _r(kb + bm, 1),
            "length_axis": "X" if shape.BoundBox.XLength >= shape.BoundBox.YLength else "Y",
            "method": f"{slices} horizontal slices, outer loops only (interior counts as buoyant)",
        }
    )
    if kg_mm is not None:
        gm = kb + bm - float(kg_mm)
        out["KG_mm"] = float(kg_mm)
        out["GM_mm"] = _r(gm, 1)
        out["stability"] = "positive" if gm > 0 else "NEGATIVE - capsizes"
    return out


def _overhangs(mesh, z_bed, max_overhang_deg):
    limit = -math.sin(math.radians(max_overhang_deg))
    total = overhang = worst = 0.0
    for facet in mesh.Facets:
        total += facet.Area
        nz = facet.Normal.z
        on_bed = nz < -0.999 and min(p[2] for p in facet.Points) - z_bed < 1e-3
        if nz < limit and not on_bed:
            overhang += facet.Area
            worst = max(worst, math.degrees(math.asin(min(1.0, -nz))))
    return total, overhang, worst


def _wall_samples(shape, mesh, samples):
    """Wall thickness at sampled surface points, measured along the inward normal."""
    facets = mesh.Facets
    reach = shape.BoundBox.DiagonalLength
    walls = []
    for facet in facets[:: max(1, len(facets) // samples)]:
        normal = App.Vector(*facet.Normal)
        center = App.Vector(*[sum(p[k] for p in facet.Points) / 3.0 for k in range(3)])
        try:
            ray = Part.LineSegment(center + normal * 0.01, center - normal * reach).toShape()
            inside = ray.common(shape)
        except FREECAD_ERRORS:
            continue
        # The first inside segment starts at the sample point; its length is the wall.
        for edge in inside.Edges:
            if min((v.Point - center).Length for v in edge.Vertexes) < 0.05:
                walls.append(edge.Length)
                break
    return sorted(walls)


def printability(name, max_overhang_deg=45.0, build_volume_mm=None, min_wall_mm=None, samples=150):
    """Overhangs, wall thickness and build-volume fit for printing along +Z."""
    import Mesh

    shape = _shape(name)
    bb = shape.BoundBox
    mesh = Mesh.Mesh(shape.tessellate(max(0.05, bb.DiagonalLength / 400.0)))
    total, overhang, worst = _overhangs(mesh, bb.ZMin, float(max_overhang_deg))
    out = {
        "object": name,
        "print_direction": "+Z",
        "max_overhang_deg": max_overhang_deg,
        "overhang_area_mm2": _r(overhang, 1),
        "overhang_area_pct": _r(100 * overhang / total, 2) if total else 0,
        "worst_overhang_deg_from_vertical": _r(worst, 1),
        "needs_support": overhang > 0.001 * total,
    }

    walls = _wall_samples(shape, mesh, int(samples))
    if walls:
        out["wall_min_mm"] = _r(walls[0], 2)
        out["wall_p05_mm"] = _r(walls[max(0, int(0.05 * len(walls)) - 1)], 2)
        out["wall_median_mm"] = _r(walls[len(walls) // 2], 2)
        if min_wall_mm is not None:
            thin = sum(1 for w in walls if w < float(min_wall_mm))
            out["min_wall_required_mm"] = float(min_wall_mm)
            out["thin_wall_samples_pct"] = _r(100.0 * thin / len(walls), 1)

    if build_volume_mm:
        bx, by, bz = (float(x) for x in build_volume_mm)
        sx, sy, sz = bb.XLength, bb.YLength, bb.ZLength
        out["build_volume_mm"] = [bx, by, bz]
        out["part_size_mm"] = [_r(sx), _r(sy), _r(sz)]
        out["fits_build_volume"] = sz <= bz and ((sx <= bx and sy <= by) or (sy <= bx and sx <= by))
    return out


def _segment_edge(segment):
    kind = segment[0]
    if kind == "spline":
        curve = Part.BSplineCurve()
        curve.interpolate([App.Vector(x, y, 0) for x, y in segment[1]])
        return curve.toShape()
    points = [App.Vector(x, y, 0) for x, y in segment[1:]]
    if kind == "arc":
        return Part.Arc(*points).toShape()
    return Part.LineSegment(*points).toShape()


def spur_gear(
    module, teeth, width, bore=0.0, profile_shift=0.0, pressure_angle_deg=20.0, keyway=None, name="Gear"
):
    """Exact involute spur gear as one solid, axis +Z, bottom face at z=0."""
    # spur_outline and spur_radii come from gear_profile.py, which server.py sends first.
    edges = [_segment_edge(s) for s in spur_outline(module, teeth, profile_shift, pressure_angle_deg)]  # noqa: F821
    solid = Part.Face(Part.Wire(edges)).extrude(App.Vector(0, 0, width))
    if bore:
        solid = solid.cut(Part.makeCylinder(bore / 2, width))
        if keyway:
            # keyway = [width, depth of the hub groove beyond the bore] (DIN 6885 t2)
            key_width, key_depth = keyway
            slot = Part.makeBox(key_width, bore / 2 + key_depth, width, App.Vector(-key_width / 2, 0, 0))
            solid = solid.cut(slot)

    doc = _doc(create=True)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = solid
    # The solid is not parametric, so keep the inputs on it for whoever edits it later.
    for prop, kind, value in (
        ("Module", "App::PropertyFloat", module),
        ("Teeth", "App::PropertyInteger", teeth),
        ("FaceWidth", "App::PropertyFloat", width),
        ("Bore", "App::PropertyFloat", bore),
        ("ProfileShift", "App::PropertyFloat", profile_shift),
        ("PressureAngle", "App::PropertyFloat", pressure_angle_deg),
    ):
        obj.addProperty(kind, prop, "Gear", "Input used to build the teeth")
        setattr(obj, prop, value)
    doc.recompute()

    radii = spur_radii(module, teeth, profile_shift, pressure_angle_deg)  # noqa: F821
    alpha = math.radians(pressure_angle_deg)
    z_min = 2 / math.sin(alpha) ** 2
    out = {
        "name": obj.Name,
        "valid": solid.isValid(),
        "solids": len(solid.Solids),
        "faces": len(solid.Faces),
        "volume_mm3": _r(solid.Volume),
        "pitch_diameter_mm": _r(2 * radii["pitch"]),
        "tip_diameter_mm": _r(2 * radii["tip"]),
        "root_diameter_mm": _r(2 * radii["root"]),
        "base_diameter_mm": _r(2 * radii["base"]),
    }
    x_min = (z_min - teeth) / z_min
    if profile_shift < x_min - 1e-6:
        out["undercut_warning"] = (
            f"{teeth} teeth at {pressure_angle_deg} deg are below the undercut limit "
            f"(z_min {z_min:.1f}); real teeth need profile shift >= {x_min:.3f}. "
            "The model shows the teeth without undercut."
        )
    return out


def ring_gear(
    module, teeth, width, outer_diameter, profile_shift=0.0, pressure_angle_deg=20.0, name="RingGear"
):
    """Internal involute ring gear as one solid, axis +Z, bottom face at z=0."""
    # ring_radii and ring_cutter_outline come from gear_profile.py, sent first by server.py.
    radii = ring_radii(module, teeth, profile_shift, pressure_angle_deg)  # noqa: F821
    if outer_diameter / 2 <= radii["root"]:
        raise ValueError(
            f"outer diameter {outer_diameter} must be larger than the root diameter {2 * radii['root']:.3f}"
        )
    segments = ring_cutter_outline(module, teeth, profile_shift, pressure_angle_deg)  # noqa: F821
    cutter = Part.Face(Part.Wire([_segment_edge(s) for s in segments])).extrude(App.Vector(0, 0, width))
    solid = Part.makeCylinder(outer_diameter / 2, width).cut(cutter)

    doc = _doc(create=True)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = solid
    for prop, kind, value in (
        ("Module", "App::PropertyFloat", module),
        ("Teeth", "App::PropertyInteger", teeth),
        ("FaceWidth", "App::PropertyFloat", width),
        ("OuterDiameter", "App::PropertyFloat", outer_diameter),
        ("ProfileShift", "App::PropertyFloat", profile_shift),
        ("PressureAngle", "App::PropertyFloat", pressure_angle_deg),
    ):
        obj.addProperty(kind, prop, "Gear", "Input used to build the teeth")
        setattr(obj, prop, value)
    doc.recompute()

    rim = outer_diameter / 2 - radii["root"]
    tooth_depth = radii["root"] - radii["tip"]
    out = {
        "name": obj.Name,
        "valid": solid.isValid(),
        "solids": len(solid.Solids),
        "faces": len(solid.Faces),
        "volume_mm3": _r(solid.Volume),
        "pitch_diameter_mm": _r(2 * radii["pitch"]),
        "tip_diameter_mm (inner)": _r(2 * radii["tip"]),
        "root_diameter_mm (outer)": _r(2 * radii["root"]),
        "base_diameter_mm": _r(2 * radii["base"]),
        "rim_thickness_mm": _r(rim),
    }
    warnings = []
    if radii["tip"] < radii["base"]:
        warnings.append(
            "tip circle lies inside the base circle, so the flanks there are not involute: "
            "use a larger profile shift or more teeth"
        )
    if rim / tooth_depth < 1.2:
        warnings.append(
            f"rim backup ratio {rim / tooth_depth:.2f} < 1.2 (ISO 6336-3): the rim is thin "
            "for the tooth depth, make the outer diameter larger"
        )
    if warnings:
        out["warnings"] = warnings
    return out


def sheet_profile(thickness, inner_radius, flanges, angles, length, name="SheetProfile"):
    """Bent sheet-metal profile as one solid: cross-section in XY, extruded along +Z."""
    # profile_outline and profile_layout come from sheet_profile.py, sent first by server.py.
    segments = profile_outline(thickness, inner_radius, flanges, angles)  # noqa: F821
    layout = profile_layout(thickness, inner_radius, flanges, angles)  # noqa: F821
    face = Part.Face(Part.Wire([_segment_edge(s) for s in segments]))
    solid = face.extrude(App.Vector(0, 0, length))

    doc = _doc(create=True)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = solid
    for prop, kind, value in (
        ("Thickness", "App::PropertyFloat", thickness),
        ("InnerRadius", "App::PropertyFloat", inner_radius),
        ("Flanges", "App::PropertyFloatList", flanges),
        ("BendAngles", "App::PropertyFloatList", angles),
        ("ProfileLength", "App::PropertyFloat", length),
    ):
        obj.addProperty(kind, prop, "SheetMetal", "Input used to build the profile")
        setattr(obj, prop, value)
    doc.recompute()

    expected = thickness * layout["centre_line_length"] * length
    bb = solid.BoundBox
    return {
        "name": obj.Name,
        "valid": solid.isValid(),
        "solids": len(solid.Solids),
        "faces": len(solid.Faces),
        "volume_mm3": _r(solid.Volume),
        "expected_volume_mm3": _r(expected),
        "bbox_mm": [_r(bb.XLength), _r(bb.YLength), _r(bb.ZLength)],
        "straight_lengths_mm": [_r(x) for x in layout["straights"]],
    }


# Optional add-ons: what each one adds, and how a user installs it. The core tools
# never need them; the AI should say what is missing instead of failing or installing.
OPTIONAL_ADDONS = {
    "FCGear (freecad.gears)": {
        "modules": ["freecad.gears"],
        "needed_for": "bevel, worm, cycloid, rack and crown gears. Spur and ring gears are "
        "built in (build_spur_gear, build_ring_gear).",
    },
    "SheetMetal": {
        "modules": ["SheetMetalCmd", "SheetMetalTools"],
        "needed_for": "parts folded in several directions (boxes, enclosures) and their "
        "unfolded flat pattern. Single-direction profiles use build_sheet_profile.",
    },
    "Fasteners": {
        "modules": ["FastenersCmd"],
        "needed_for": "3D models of bolts, nuts and washers. Hole and bolt sizes come from "
        "calc_fasteners without it.",
    },
}
ADDON_INSTALL = (
    "In FreeCAD: Tools > Addon manager, search for '{name}', click Install, then restart "
    "FreeCAD. Only install it if you need it; the assistant never installs add-ons itself."
)


def _module_found(name):
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _find_program(names, param_path, param_key):
    """A solver program from FreeCAD's FEM settings, its own bin folder or the PATH."""
    import shutil

    configured = App.ParamGet(param_path).GetString(param_key, "")
    if configured and os.path.isfile(configured):
        return configured
    for name in names:
        candidate = os.path.join(App.getHomePath(), "bin", name)
        if os.path.isfile(candidate):
            return candidate
        found = shutil.which(name)
        if found:
            return found
    return None


def doctor_freecad():
    """What this FreeCAD install can do: version, optional add-ons, FEM programs."""
    addons = {}
    for name, info in OPTIONAL_ADDONS.items():
        installed = any(_module_found(m) for m in info["modules"])
        entry = {"installed": installed, "needed_for": info["needed_for"]}
        if not installed:
            entry["how_to_install"] = ADDON_INSTALL.format(name=name.split(" ")[0])
        addons[name] = entry
    return {
        "freecad_version": ".".join(App.Version()[:3]),
        "optional_addons": addons,
        "fem": fem_programs(),
    }


FEM_PARAMS = "User parameter:BaseApp/Preferences/Mod/Fem"
FEM_INSTALL = (
    "{name} was not found. FreeCAD's own installers include it: reinstall FreeCAD with the "
    "FEM components ticked (Windows installer, or the AppImage/.dmg on Linux/macOS), or "
    "install {name} yourself ({hint}) and set its path under Edit > Preferences > FEM > "
    "{page}. Restart FreeCAD afterwards. The assistant never installs programs itself."
)


def fem_programs():
    """FEM workbench, CalculiX and Gmsh paths, with install steps for what is missing."""
    ccx = _find_program(["ccx.exe", "ccx"], FEM_PARAMS + "/Ccx", "ccxBinaryPath")
    gmsh = _find_program(["gmsh.exe", "gmsh"], FEM_PARAMS + "/Gmsh", "gmshBinaryPath")
    report = {
        "fem_workbench": _module_found("ObjectsFem"),
        "calculix": ccx or "not found",
        "gmsh": gmsh or "not found",
        "note": "Needed for fea_setup / fea_run / fea_results.",
    }
    if not ccx:
        report["calculix_how_to_install"] = FEM_INSTALL.format(
            name="CalculiX (ccx)", hint="e.g. 'apt install calculix-ccx' on Debian/Ubuntu", page="CalculiX"
        )
    if not gmsh:
        report["gmsh_how_to_install"] = FEM_INSTALL.format(
            name="Gmsh", hint="from gmsh.info or 'apt install gmsh'", page="Gmsh"
        )
    return report


# Plain shape containers and housekeeping objects; everything else that has a Shape
# is a modelling feature that should be driven by the Params spreadsheet.
NON_FEATURE_TYPES = {
    "App::Origin",
    "App::Line",
    "App::Plane",
    "App::Part",
    "App::DocumentObjectGroup",
    "PartDesign::Body",
    "Sketcher::SketchObject",
    "Spreadsheet::Sheet",
}
DATUM_TYPES = {"App::Plane", "App::Origin", "PartDesign::Plane", "Part::DatumPlane"}


# FreeCAD 1.1 gives a Body's origin a newer type than App::Origin, so compare by
# ancestry and name rather than by one exact type string.
REFERENCE_BASES = (
    "App::Origin",
    "App::LocalCoordinateSystem",
    "App::DatumElement",
    "App::Line",
    "App::Plane",
)


def _is_reference(obj):
    if (
        obj.TypeId in NON_FEATURE_TYPES | DATUM_TYPES
        or "Origin" in obj.TypeId
        or "CoordinateSystem" in obj.TypeId
    ):
        return True
    for base in REFERENCE_BASES:
        try:
            if obj.isDerivedFrom(base):
                return True
        except (RuntimeError, TypeError, ValueError):  # type unknown in this FreeCAD version
            continue
    return False


def _is_static(obj):
    # Draft arrays and other scripted objects are Part::FeaturePython with a Proxy that
    # rebuilds them; a plain Part::Feature, or one without a Proxy, is a frozen shape.
    return obj.TypeId == "Part::Feature" or (
        obj.TypeId == "Part::FeaturePython" and getattr(obj, "Proxy", None) is None
    )


def _attachment(obj):
    support = getattr(obj, "AttachmentSupport", None)
    if support is None:
        support = getattr(obj, "Support", None)
    return support or []


def _sketches_on_faces(doc):
    found = []
    for obj in doc.Objects:
        if obj.TypeId != "Sketcher::SketchObject":
            continue
        for link, subs in _attachment(obj):
            names = [subs] if isinstance(subs, str) else list(subs)
            if not _is_reference(link) and any(n.startswith("Face") for n in names):
                found.append(f"{obj.Label} on {link.Label}.{','.join(names)}")
    return found


def _alias_names(doc):
    names = []
    for sheet in doc.Objects:
        if sheet.TypeId != "Spreadsheet::Sheet":
            continue
        cells = sheet.getNonEmptyCells() if hasattr(sheet, "getNonEmptyCells") else []
        names += [a for a in (sheet.getAlias(c) for c in cells) if a]
    return names


def _sheet_formulas(doc):
    formulas = []
    for sheet in doc.Objects:
        if sheet.TypeId == "Spreadsheet::Sheet" and hasattr(sheet, "getNonEmptyCells"):
            formulas += [sheet.getContents(c) for c in sheet.getNonEmptyCells()]
    return [f for f in formulas if f.startswith("=")]


def model_structure():
    """How editable the active document is: Params use, sketch attachment, static
    copies, errors and leftovers, with a 0-100 score and the reasons."""
    doc = _doc()
    aliases = _alias_names(doc)
    expressions = {o.Name: [e for _, e in o.ExpressionEngine] for o in doc.Objects if o.ExpressionEngine}
    words = {w for exprs in expressions.values() for e in exprs for w in re.findall(r"[A-Za-z_]\w*", e)}
    used = sorted(a for a in aliases if a in words)
    # A parameter is unused if neither a feature nor another cell (e.g. "=PlateL/2") reads it.
    cell_words = {w for f in _sheet_formulas(doc) for w in re.findall(r"[A-Za-z_]\w*", f)}
    unused = sorted(a for a in aliases if a not in words and a not in cell_words)
    features = [o for o in doc.Objects if _has_shape(o) and not _is_reference(o)]
    parametric = [o for o in features if not _is_static(o)]
    driven = [o.Label for o in parametric if o.Name in expressions]
    static = [o.Label for o in features if _is_static(o)]
    on_faces = _sketches_on_faces(doc)
    broken = [o.Label for o in doc.Objects if {"Invalid", "Error"} & set(o.State or [])]
    # A PartDesign Body's origin axes and planes are not leftovers.
    tops = [o.Label for o in _top_level_shapes(doc) if not _is_reference(o)]

    issues, score = [], 100
    if not aliases:
        issues.append("No Params spreadsheet: every size is hard-coded. Use set_parameters.")
        score -= 40
    elif not used:
        issues.append("Params exist but no feature uses them: bind sizes with setExpression.")
        score -= 35
    elif parametric and len(driven) < len(parametric) / 2:
        issues.append(f"Only {len(driven)} of {len(parametric)} features are driven by Params.")
        score -= 15
    if used and unused:
        issues.append(f"Parameters nothing uses (duplicates or leftovers, remove them): {unused}")
        score -= 5
    if on_faces:
        issues.append(f"Sketches attached to generated faces (break on edits): {on_faces}")
        score -= 15 * min(len(on_faces), 2)
    if static:
        issues.append(f"Static shape copies that do not follow parameter changes: {static}")
        score -= 20
    if broken:
        issues.append(f"Objects with recompute errors: {broken}")
        score -= 20
    if len(tops) > 1:
        issues.append(f"{len(tops)} visible top-level shapes; keep only the final part: {tops}")
        score -= 5
    return {
        "score": max(score, 0),
        "issues": issues,
        "params": aliases,
        "params_used": used,
        "params_unused": unused,
        "features": len(features),
        "driven_by_params": driven,
        "static_copies": static,
        "sketches_on_faces": on_faces,
        "top_level": tops,
    }
