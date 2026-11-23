"""FEA functions that run inside FreeCAD: CalculiX setup, mesh and solve, results.

server.py appends this file to fc_tools.py and uses its helpers (_doc, _obj, _has_shape).
"""

FEA_ELEMENT_ORDER = "2nd"
# CalculiX writes these next to the .inp; any left from an earlier run would be read
# back as this run's results if ccx stopped before overwriting them.
RESULT_SUFFIXES = (".frd", ".dat", ".sta", ".cvg")
# For eigenvalue runs the .sta lists no steps, so ccx's own last line is the only
# sign that the job got to the end.
CCX_FINISHED = "Job finished"
STA_STEP_ROW = re.compile(r"^\s*\d+\s+\d+\s+\d+\s+\d+\s+\S+", re.M)
# A table counts only with its first numbered row, not just the heading.
EIGEN_TABLES = {
    "buckling": (
        re.compile(r"B U C K L I N G\s+F A C T O R\s+O U T P U T.*?^\s*1\s+[-+0-9.]+E[-+]\d+", re.S | re.M),
        "buckling factors",
    ),
    "frequency": (
        re.compile(r"E I G E N V A L U E\s+O U T P U T.*?^\s*1\s+[-+0-9.]+E[-+]\d+", re.S | re.M),
        "eigenvalues",
    ),
}
TAIL_LINES = 30
CCX_VERSION = re.compile(r"CalculiX Version (\S+?),")
# CalculiX prints one line per fixed set: "total force (fx,fy,fz) for set FIXED and time 1.0"
# followed by the three components.
REACTION_LINE = re.compile(r"total force \(fx,fy,fz\) for set (\S+) and time\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)")


def _unique_obj(doc, name):
    """The one object whose Name or Label is `name`; refuses if several match."""
    matches = {o.Name: o for o in doc.getObjectsByLabel(name)}
    by_name = doc.getObject(name)
    if by_name is not None:
        matches[by_name.Name] = by_name
    if len(matches) > 1:
        raise RuntimeError(
            f"{name!r} matches several objects ({', '.join(sorted(matches))}); "
            "give the part's unique Name instead, or rename the others"
        )
    return next(iter(matches.values())) if matches else _obj(name)


def _fea_analysis(name):
    analysis = _doc().getObject(name)
    if analysis is None or analysis.TypeId != "Fem::FemAnalysis":
        raise RuntimeError(f"No FEA analysis named {name!r}. Run fea_setup first.")
    return analysis


def _members(analysis, type_id=None, base=None):
    return [
        o
        for o in analysis.Group
        if (type_id is None or o.TypeId == type_id) and (base is None or o.isDerivedFrom(base))
    ]


def _face_info(shape, entries):
    """Face names or selectors resolved to faces, each with the entry that found it."""
    sel = _selectors()
    rows, seen = [], set()
    for entry in entries:
        for index in sel.resolve_face(shape, entry):
            if index in seen:
                continue
            seen.add(index)
            face = shape.Faces[index - 1]
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            rows.append(
                {
                    "face": f"Face{index}",
                    "selector": entry,
                    "centre_mm": _vec(face.CenterOfMass),
                    "normal": _vec(normal),
                    "area_mm2": _r(face.Area, 2),
                    "planar": face.Surface.TypeId == "Part::GeomPlane",
                }
            )
    return rows


def _names(rows):
    return [row["face"] for row in rows]


def _remove_analysis(doc, analysis):
    from femresult.resulttools import purge_results

    purge_results(analysis)
    for member in list(analysis.Group):
        doc.removeObject(member.Name)
    doc.removeObject(analysis.Name)


def _direction_line(doc, name, direction):
    # A force without a Direction link is reset to the face normal on recompute, so
    # point a datum line along the wanted direction and link the force to it.
    line = doc.addObject("App::Line", name)
    target = App.Vector(*direction)
    line.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), target))
    line.Visibility = False
    return line


def _add_load(doc, analysis, part, index, load):
    import ObjectsFem

    faces = tuple(load["faces"])
    if load["type"] == "force":
        con = ObjectsFem.makeConstraintForce(doc, f"{analysis.Name}_Force{index}")
        con.Force = f"{load['value_n']} N"
        line = _direction_line(doc, f"{analysis.Name}_Dir{index}", load["direction"])
        analysis.addObject(line)
        con.Direction = (line, [""])
        con.Reversed = False
    else:
        con = ObjectsFem.makeConstraintPressure(doc, f"{analysis.Name}_Pressure{index}")
        con.Pressure = f"{abs(load['value_mpa'])} MPa"
        # FreeCAD pressure pushes on the face; Reversed makes it pull.
        con.Reversed = load["value_mpa"] < 0
    con.References = [(part, faces)]
    analysis.addObject(con)
    return con


def _configure_solver(solver, analysis_type, modes, time_end_s=None, time_step_s=None):
    if analysis_type == "modal":
        solver.AnalysisType = "frequency"
        solver.EigenmodesCount = modes
    elif analysis_type == "thermal_steady":
        solver.AnalysisType = "thermomech"
        solver.ThermoMechType = "pure heat transfer"
        solver.ThermoMechSteadyState = True
    elif analysis_type == "thermal_transient":
        solver.AnalysisType = "thermomech"
        solver.ThermoMechType = "pure heat transfer"
        solver.ThermoMechSteadyState = False
        # Fixed steps (DIRECT), so the reported times are exactly the requested ones.
        solver.AutomaticIncrementation = False
        solver.TimePeriod = f"{time_end_s} s"
        solver.TimeInitialIncrement = f"{time_step_s} s"
        solver.TimeMaximumIncrement = f"{time_step_s} s"
    elif analysis_type == "buckling":
        solver.AnalysisType = "buckling"
        solver.BucklingFactors = modes
    elif analysis_type == "thermomechanical":
        solver.AnalysisType = "thermomech"
        solver.ThermoMechType = "uncoupled"
        solver.ThermoMechSteadyState = True


AXES = {0: "x", 1: "y", 2: "z"}


def _add_sliding(doc, analysis, part, faces):
    """Each face may slide in its own plane but not move along its normal."""
    import ObjectsFem

    for info in _face_info(part.Shape, faces):
        normal = [abs(c) for c in info["normal"]]
        axis = max(range(3), key=normal.__getitem__)
        if not info["planar"] or normal[axis] < 1 - 1e-9:
            raise RuntimeError(
                f"sliding face {info['face']} must be flat and face along x, y or z "
                f"(normal {info['normal']}); use fixed_faces there instead"
            )
        con = ObjectsFem.makeConstraintDisplacement(doc, f"{analysis.Name}_Slide{info['face']}")
        con.References = [(part, (info["face"],))]
        setattr(con, f"{AXES[axis]}Free", False)
        analysis.addObject(con)


def _material_map(material, reference_k):
    return {
        "Name": material["name"],
        "YoungsModulus": f"{material['E_mpa']} MPa",
        "PoissonRatio": str(material["nu"]),
        "Density": f"{material['density_kg_m3']} kg/m^3",
        "YieldStrength": f"{material['yield_mpa']} MPa",
        "ThermalConductivity": f"{material['k_w_mk']} W/m/K",
        "SpecificHeat": f"{material['cp_j_kgk']} J/kg/K",
        "ThermalExpansionCoefficient": f"{material['alpha_1_k'] * 1e6} um/m/K",
        "ThermalExpansionReferenceTemperature": f"{reference_k} K",
    }


def _add_temperatures(doc, analysis, part, temperatures, initial_k):
    import ObjectsFem

    for i, entry in enumerate(temperatures, 1):
        con = ObjectsFem.makeConstraintTemperature(doc, f"{analysis.Name}_Temp{i}")
        con.References = [(part, tuple(entry["faces"]))]
        con.Temperature = f"{entry['temperature_c'] + 273.15} K"
        analysis.addObject(con)
    init = ObjectsFem.makeConstraintInitialTemperature(doc, f"{analysis.Name}_InitialTemp")
    init.initialTemperature = f"{initial_k} K"
    analysis.addObject(init)


def fea_setup(
    part,
    material,
    fixed_faces,
    loads,
    mesh_size_mm,
    name,
    analysis_type="static",
    modes=6,
    temperatures=(),
    initial_temperature_c=20.0,
    sliding_faces=(),
    time_end_s=None,
    time_step_s=None,
    *,
    max_elements,
):
    """Build (or replace) a CalculiX analysis of one part."""
    import ObjectsFem

    doc = _doc()
    obj = _unique_obj(doc, part)
    if not _has_shape(obj) or not obj.Shape.Solids:
        raise RuntimeError(f"{part} has no solid to analyse")
    shape = obj.Shape
    _check_element_count(shape.Volume, mesh_size_mm, max_elements)
    try:
        fixed_info = _face_info(shape, fixed_faces)
        sliding_info = _face_info(shape, sliding_faces)
        load_faces = [_face_info(shape, load["faces"]) for load in loads]
        temp_faces = [_face_info(shape, t["faces"]) for t in temperatures]
    except _selectors().SelectorError as e:
        return _selector_refusal(e)
    fixed_faces, sliding_faces = _names(fixed_info), _names(sliding_info)
    loads = [{**load, "faces": _names(info)} for load, info in zip(loads, load_faces, strict=True)]
    temperatures = [{**t, "faces": _names(info)} for t, info in zip(temperatures, temp_faces, strict=True)]
    initial_k = initial_temperature_c + 273.15

    old = doc.getObject(name)
    if old is not None:
        if old.TypeId != "Fem::FemAnalysis":
            raise RuntimeError(f"{name!r} is already used by a {old.TypeId}; choose another name")
        _remove_analysis(doc, old)

    analysis = ObjectsFem.makeAnalysis(doc, name)
    solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, f"{name}_Solver")
    _configure_solver(solver, analysis_type, modes, time_end_s, time_step_s)
    analysis.addObject(solver)
    mat = ObjectsFem.makeMaterialSolid(doc, f"{name}_Material")
    mat.Material = _material_map(material, initial_k)
    analysis.addObject(mat)
    if fixed_faces:
        fixed = ObjectsFem.makeConstraintFixed(doc, f"{name}_Fixed")
        fixed.References = [(obj, tuple(fixed_faces))]
        analysis.addObject(fixed)
    if sliding_faces:
        _add_sliding(doc, analysis, obj, sliding_faces)
    constraints = [_add_load(doc, analysis, obj, i, load) for i, load in enumerate(loads, 1)]
    if temperatures:
        _add_temperatures(doc, analysis, obj, temperatures, initial_k)
    mesh = ObjectsFem.makeMeshGmsh(doc, f"{name}_Mesh")
    mesh.Shape = obj
    mesh.CharacteristicLengthMax = f"{mesh_size_mm} mm"
    mesh.ElementOrder = FEA_ELEMENT_ORDER
    analysis.addObject(mesh)
    doc.recompute()

    for con, load in zip(constraints, loads, strict=True):
        if load["type"] == "force":
            want = App.Vector(*load["direction"]).normalize()
            if (con.DirectionVector - want).Length > 1e-6:
                raise RuntimeError(f"{con.Name} points along {con.DirectionVector}, not {want}")

    return {
        "analysis": name,
        "analysis_type": analysis_type,
        "modes": modes if analysis_type == "modal" else None,
        "replaced_old_analysis": old is not None,
        "part": obj.Name,
        "fixed_faces": fixed_info,
        "sliding_faces": sliding_info,
        "loads": [{**load, "face_info": info} for load, info in zip(loads, load_faces, strict=True)],
        "temperatures": [{**t, "face_info": info} for t, info in zip(temperatures, temp_faces, strict=True)],
        "initial_temperature_c": initial_temperature_c if temperatures else None,
        "time_end_s": time_end_s,
        "time_step_s": time_step_s,
        "mesh_size_mm": mesh_size_mm,
        "element_order": "2nd order (10-node tetrahedra)",
    }


def _check_element_count(volume_mm3, mesh_size_mm, max_elements):
    # A cube of edge h splits into about 6 tetrahedra, so volume / h^3 * 6 elements.
    estimate = volume_mm3 / mesh_size_mm**3 * 6
    if estimate > max_elements:
        smallest = (volume_mm3 * 6 / max_elements) ** (1 / 3)
        raise RuntimeError(
            f"mesh_size_mm {mesh_size_mm} would give about {estimate:,.0f} elements for this part "
            f"({volume_mm3:,.0f} mm^3), more than the {max_elements:,} limit. "
            f"Use mesh_size_mm {math.ceil(smallest * 100) / 100} or larger."
        )


def _request_heat_flow(inp_path, node_sets):
    # FreeCAD asks CalculiX for reaction forces at fixed faces but not for the heat
    # flow at fixed temperatures, so add that request to the step.
    with open(inp_path, encoding="utf-8") as f:
        text = f.read()
    cut = text.rfind("*END STEP")
    if cut < 0:
        raise RuntimeError("CalculiX input file has no *END STEP")
    request = "".join(f"*NODE PRINT, NSET={s}, TOTALS=ONLY\nRFL\n" for s in node_sets)
    with open(inp_path, "w", encoding="utf-8") as f:
        f.write(text[:cut] + request + text[cut:])


def _remove_old_results(base):
    for suffix in RESULT_SUFFIXES:
        if os.path.exists(base + suffix):
            os.remove(base + suffix)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _solver_problem(base, exit_code, started, stdout, analysis_type):
    """Why this run's result files can't be trusted, or None if they can."""
    if exit_code:
        return f"CalculiX stopped with exit code {exit_code}"
    for suffix in (".frd", ".dat"):
        path = base + suffix
        if not os.path.isfile(path):
            return f"CalculiX wrote no {os.path.basename(path)}"
        # One second of slack for file systems that store coarse modification times.
        if os.path.getmtime(path) < started - 1:
            return f"{os.path.basename(path)} is older than this run, so it is from an earlier analysis"
    if CCX_FINISHED not in stdout:
        return f"CalculiX did not report '{CCX_FINISHED}'"
    dat = _read(base + ".dat")
    if analysis_type in EIGEN_TABLES:
        table, what = EIGEN_TABLES[analysis_type]
        if not table.search(dat):
            return f"the .dat file has no {what}"
    elif not STA_STEP_ROW.search(_read(base + ".sta")):
        return "the .sta file shows no finished step"
    return None


def _solver_failure(base, problem, stdout, stderr):
    output = (stdout + "\n" + stderr).strip() or _read(base + ".sta").strip()
    tail = "\n".join(output.splitlines()[-TAIL_LINES:])
    message = f"CalculiX results not used: {problem}. Last {TAIL_LINES} lines of its output:\n{tail}"
    # Console output gets past the listener's capture, so the listener log shows it too.
    App.Console.PrintError(f"fea_run: {message}\n")
    return RuntimeError(message)


def fea_run(name, work_dir, threads=1):
    """Mesh with Gmsh and solve with CalculiX; results land in the analysis.

    Multithreaded CalculiX builds (SPOOLES with threads) are unreliable: on CI the same
    buckling input gave 0.96, 8.4 and 1728 run to run, and static runs failed the
    equilibrium check now and then. One thread is the default for that reason."""
    import time

    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools

    started = time.time()
    doc = _doc()
    analysis = _fea_analysis(name)
    solvers = _members(analysis, base="Fem::FemSolverObjectPython")
    meshes = _members(analysis, base="Fem::FemMeshObject")
    meshes = [m for m in meshes if m.Name == f"{name}_Mesh"]
    if not solvers or not meshes:
        raise RuntimeError(f"{name} has no solver or mesh. Run fea_setup again.")
    mesh = meshes[0]
    ccx = _find_program(["ccx.exe", "ccx"], FEM_PARAMS + "/Ccx", "ccxBinaryPath")
    if not ccx:
        raise RuntimeError("CalculiX (ccx) was not found. Run doctor for the install steps.")

    GmshTools(mesh).create_mesh()
    doc.recompute()
    if mesh.FemMesh.VolumeCount == 0:
        raise RuntimeError("Gmsh made no volume mesh. Try a larger or smaller mesh_size_mm.")
    meshed = time.time()

    # ccx_run() and run() open a modal dialog on errors when the GUI is up, which
    # would hang the listener, so drive the steps one by one.
    fea = ccxtools.FemToolsCcx(analysis, solvers[0])
    fea.update_objects()
    fea.setup_working_dir(work_dir)
    problems = fea.check_prerequisites()
    if problems:
        raise RuntimeError(f"CalculiX cannot start: {problems.strip()}")
    fea.purge_results()
    fea.write_inp_file()
    base = os.path.splitext(fea.inp_file_name)[0]
    _remove_old_results(base)
    temperature_sets = [c.Name for c in _members(analysis, type_id="Fem::ConstraintTemperature")]
    if temperature_sets:
        _request_heat_flow(fea.inp_file_name, temperature_sets)
    fea.setup_ccx(ccx_binary=ccx)
    if not fea.ccx_binary_present:
        raise RuntimeError(f"{ccx} did not answer like CalculiX. Run doctor.")
    analysis_type = solvers[0].AnalysisType
    solve_started = time.time()
    code, stdout, stderr = _run_ccx(ccx, fea.inp_file_name, threads)
    problem = _solver_problem(base, code, solve_started, stdout, analysis_type)
    if problem:
        raise _solver_failure(base, problem, stdout, stderr)
    ccx_info = _record_ccx(solvers[0], ccx, stdout, threads)
    try:
        fea.load_results()
    except ValueError as exc:
        # FreeCAD 1.1 keys its result display pipeline by frequency and fails when two
        # modes share one (any symmetric part). The result objects are loaded by then;
        # only the pipeline and the .dat file are missing.
        if "unique" not in str(exc):
            raise
        fea.load_results_ccxdat()
    if not _members(analysis, base="Fem::FemResultObject"):
        raise RuntimeError("CalculiX ran but no results were loaded.")
    return {
        "analysis": name,
        "nodes": mesh.FemMesh.NodeCount,
        "elements": mesh.FemMesh.VolumeCount,
        "mesh_size_mm": _r(mesh.CharacteristicLengthMax.Value, 3),
        "element_order": "2nd order (10-node tetrahedra)",
        "mesh_s": _r(meshed - started, 1),
        "solve_s": _r(time.time() - meshed, 1),
        "ccx": ccx_info,
    }


def _run_ccx(ccx, inp_file, threads):
    """Run CalculiX on `inp_file`; the thread settings go to this process only."""
    import subprocess

    env = dict(os.environ, OMP_NUM_THREADS=str(threads))
    if threads == 1:
        env["CCX_NPROC_EQUATION_SOLVER"] = "1"
    folder, job = os.path.split(os.path.splitext(inp_file)[0])
    proc = subprocess.run(
        [ccx, "-i", job], cwd=folder, env=env, capture_output=True, text=True, errors="replace", check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def _record_ccx(solver, binary, stdout, threads):
    match = CCX_VERSION.search(stdout)
    info = {"binary": binary, "version": match.group(1) if match else "unknown", "threads": threads}
    for prop, kind in (("CcxBinary", "App::PropertyString"), ("CcxVersion", "App::PropertyString")):
        if prop not in solver.PropertiesList:
            solver.addProperty(kind, prop, "ShapeBert", "CalculiX that ran the last fea_run")
    if "CcxThreads" not in solver.PropertiesList:
        solver.addProperty(
            "App::PropertyInteger", "CcxThreads", "ShapeBert", "CalculiX threads in the last fea_run"
        )
    solver.CcxBinary, solver.CcxVersion, solver.CcxThreads = info["binary"], info["version"], threads
    return info


def _ccx_info(solver):
    if "CcxBinary" not in solver.PropertiesList:
        return None
    return {"binary": solver.CcxBinary, "version": solver.CcxVersion, "threads": solver.CcxThreads}


def _reactions(analysis):
    texts = _members(analysis, type_id="App::TextDocument")
    sums = {}
    for match in REACTION_LINE.finditer(texts[-1].Text if texts else ""):
        sums[match.group(1)] = [_r(float(c), 3) for c in match.group(2, 3, 4)]
    return sums


def _applied_loads(analysis):
    """Sum of applied forces in N, or None when a pressure acts on a curved face."""
    total = App.Vector()
    for con in _members(analysis, type_id="Fem::ConstraintForce"):
        total += con.DirectionVector.normalize() * con.Force.getValueAs("N").Value
    for con in _members(analysis, type_id="Fem::ConstraintPressure"):
        p = con.Pressure.getValueAs("MPa").Value * (-1 if con.Reversed else 1)
        for part, subs in con.References:
            for sub in subs:
                face = part.Shape.getElement(sub)
                if face.Surface.TypeId != "Part::GeomPlane":
                    return None
                u0, u1, v0, v1 = face.ParameterRange
                total -= face.normalAt((u0 + u1) / 2, (v0 + v1) / 2) * (p * face.Area)
    return total


def _node_position(result, index):
    return _vec(result.Mesh.FemMesh.Nodes[result.NodeNumbers[index]])


def _modal_results(analysis, results, mat):
    rows = []
    for res in sorted(results, key=lambda r: r.Eigenmode):
        vectors = res.DisplacementVectors
        i_peak = max(range(len(vectors)), key=lambda i: vectors[i].Length)
        rows.append(
            {
                "mode": res.Eigenmode,
                "frequency_hz": _r(res.EigenmodeFrequency, 2),
                "peak_motion_direction": _vec(App.Vector(vectors[i_peak]).normalize()),
                "peak_at_mm": _node_position(res, i_peak),
            }
        )
    for a, b in zip(rows, rows[1:], strict=False):
        # Symmetric sections vibrate in pairs; the pair's shape can point any way in its plane.
        if abs(b["frequency_hz"] - a["frequency_hz"]) <= 1e-3 * a["frequency_hz"]:
            a["repeated_with_mode"], b["repeated_with_mode"] = b["mode"], a["mode"]
    mesh = _members(analysis, base="Fem::FemMeshObject")[0]
    density = App.Units.Quantity(mat["Density"]).getValueAs("kg/mm^3").Value
    return {
        "analysis": analysis.Name,
        "analysis_type": "modal",
        "units": {"length": "mm", "frequency": "Hz", "mass": "kg"},
        "mesh_size_mm": _r(mesh.CharacteristicLengthMax.Value, 3),
        "nodes": len(results[0].NodeNumbers),
        "material": mat["Name"],
        "part_mass_kg": _r(mesh.Shape.Shape.Volume * density, 4),
        "modes": rows,
    }


HEAT_LINE = re.compile(r"total heat generation for set (\S+) and time\s+\S+\s+(\S+)")


def _mesh_size(analysis):
    return _r(_members(analysis, base="Fem::FemMeshObject")[0].CharacteristicLengthMax.Value, 3)


def _heat_flows(analysis):
    """Heat flow in W into the part at each fixed temperature (CalculiX prints mW)."""
    texts = _members(analysis, type_id="App::TextDocument")
    flows = {
        m.group(1): float(m.group(2)) / 1000 for m in HEAT_LINE.finditer(texts[-1].Text if texts else "")
    }
    rows = []
    for con in _members(analysis, type_id="Fem::ConstraintTemperature"):
        flow = flows.get(con.Name.upper())  # CalculiX prints set names in capitals
        rows.append(
            {
                "faces": list(con.References[0][1]),
                "temperature_c": _r(con.Temperature.getValueAs("K").Value - 273.15, 2),
                "heat_flow_in_w": None if flow is None else _r(flow, 4),
            }
        )
    return rows


def _nearest_node(res, point):
    target = App.Vector(*point)
    nodes = res.Mesh.FemMesh.Nodes
    numbers = list(res.NodeNumbers)
    return min(range(len(numbers)), key=lambda i: (nodes[numbers[i]] - target).Length)


def _probe(res, point, temperature, mechanics):
    i = _nearest_node(res, point)
    row = {"point_mm": [float(c) for c in point], "node_at_mm": _node_position(res, i)}
    if temperature:
        row["temperature_c"] = _r(res.Temperature[i] - 273.15, 3)
    if mechanics:
        row["displacement_mm"] = [_r(c, 5) for c in res.DisplacementVectors[i]]
        row["von_mises_mpa"] = _r(res.vonMises[i], 3)
    return row


def _temperature_range(res):
    temps = list(res.Temperature)
    i_lo = min(range(len(temps)), key=temps.__getitem__)
    i_hi = max(range(len(temps)), key=temps.__getitem__)
    return {
        "min_temperature_c": _r(temps[i_lo] - 273.15, 3),
        "min_temperature_at_mm": _node_position(res, i_lo),
        "max_temperature_c": _r(temps[i_hi] - 273.15, 3),
        "max_temperature_at_mm": _node_position(res, i_hi),
    }


def _thermal_results(analysis, res, mat):
    flows = _heat_flows(analysis)
    out = {
        "units": {"length": "mm", "temperature": "°C", "heat_flow": "W"},
        "mesh_size_mm": _mesh_size(analysis),
        "nodes": len(res.Temperature),
        "material": mat["Name"],
        **_temperature_range(res),
        "heat_flow_by_face": flows,
    }
    known = [f["heat_flow_in_w"] for f in flows if f["heat_flow_in_w"] is not None]
    if known:
        # With no other heat sources, what flows in at one face must leave at another.
        scale = max(abs(q) for q in known) or 1.0
        out["heat_balance_ok"] = abs(sum(known)) <= 0.01 * scale
    return out


def _static_results(analysis, res, mat):
    vm = list(res.vonMises)
    i_vm = max(range(len(vm)), key=vm.__getitem__)
    disp = list(res.DisplacementLengths)
    i_d = max(range(len(disp)), key=disp.__getitem__)
    yield_mpa = App.Units.Quantity(mat["YieldStrength"]).getValueAs("MPa").Value
    reactions = _reactions(analysis)
    reaction_total = [_r(sum(v[k] for v in reactions.values()), 3) for k in range(3)]
    applied = _applied_loads(analysis)
    out = {
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "mesh_size_mm": _mesh_size(analysis),
        "nodes": len(vm),
        "material": mat["Name"],
        "yield_mpa": _r(yield_mpa, 1),
        "max_von_mises_mpa": _r(vm[i_vm], 2),
        "max_von_mises_at_mm": _node_position(res, i_vm),
        "max_displacement_mm": _r(disp[i_d], 4),
        "max_displacement_at_mm": _node_position(res, i_d),
        "max_displacement_vector_mm": [_r(c, 4) for c in res.DisplacementVectors[i_d]],
        "reaction_force_sum_n": reaction_total,
        "reaction_force_by_set_n": reactions,
        "safety_factor_vs_yield": _r(yield_mpa / vm[i_vm], 2) if vm[i_vm] > 0 else None,
    }
    if applied is not None:
        out["applied_force_sum_n"] = _vec(applied)
        # The supports must carry exactly what is applied; if not, a load or fixed face is
        # wrong. Thermal stress alone loads the supports against each other, so compare
        # with the largest single reaction too.
        biggest = max([applied.Length] + [App.Vector(*v).Length for v in reactions.values()])
        off = (App.Vector(*reaction_total) + applied).Length
        out["equilibrium_ok"] = off <= 0.01 * max(biggest, 1e-9)
    return out


BUCKLING_TABLE = re.compile(r"B U C K L I N G\s+F A C T O R\s+O U T P U T(.*?)(?:E I G E N|\Z)", re.S)
BUCKLING_ROW = re.compile(r"^\s*(\d+)\s+([-+0-9.Ee]+)\s*$", re.M)


def _buckling_results(analysis, res, mat):
    texts = _members(analysis, type_id="App::TextDocument")
    table = BUCKLING_TABLE.search(texts[-1].Text if texts else "")
    if table is None:
        raise RuntimeError("CalculiX printed no buckling factors")
    factors = [float(m.group(2)) for m in BUCKLING_ROW.finditer(table.group(1))]
    applied = _applied_loads(analysis)
    rows = [{"mode": i, "load_factor": _r(f, 3)} for i, f in enumerate(factors, 1)]
    if applied is not None:
        for row in rows:
            row["critical_load_n"] = _r(row["load_factor"] * applied.Length, 1)
    positive = [f for f in factors if f > 0]
    return {
        "units": {"length": "mm", "force": "N"},
        "mesh_size_mm": _mesh_size(analysis),
        "nodes": len(res.NodeNumbers),
        "material": mat["Name"],
        "applied_force_sum_n": _vec(applied) if applied is not None else None,
        "lowest_load_factor": _r(min(positive), 3) if positive else None,
        "modes": rows,
    }


def _thermomech_results(analysis, res, mat):
    out = _static_results(analysis, res, mat)
    out["units"]["temperature"] = "°C"
    out.update(_temperature_range(res))
    return out


def _history(results, point):
    """Temperature over time at the node nearest to `point` (transient runs)."""
    i = _nearest_node(results[0], point)
    return [[_r(r.Time, 3), _r(r.Temperature[i] - 273.15, 3)] for r in results]


def fea_results(name, probes=None):
    """Summary of a solved analysis, plus values at the nodes nearest to `probes`."""
    analysis = _fea_analysis(name)
    results = _members(analysis, base="Fem::FemResultObject")
    if not results:
        raise RuntimeError(f"{name} has no results yet. Run fea_run first.")
    mat = _members(analysis, base="App::MaterialObjectPython")[0].Material
    solver = _members(analysis, base="Fem::FemSolverObjectPython")[0]
    ccx = _ccx_info(solver)
    if solver.AnalysisType == "frequency":
        return {"analysis": name, **_modal_results(analysis, results, mat), "ccx": ccx}
    results = sorted(results, key=lambda r: r.Time)
    res = results[-1]
    if solver.AnalysisType == "buckling":
        return {
            "analysis": name,
            "analysis_type": "buckling",
            **_buckling_results(analysis, res, mat),
            "ccx": ccx,
        }
    if solver.AnalysisType != "thermomech":
        kind, summary = "static", _static_results
    elif solver.ThermoMechType != "pure heat transfer":
        kind, summary = "thermomechanical", _thermomech_results
    elif solver.ThermoMechSteadyState:
        kind, summary = "thermal_steady", _thermal_results
    else:
        kind, summary = "thermal_transient", _thermal_results
    out = {"analysis": name, "analysis_type": kind, **summary(analysis, res, mat), "ccx": ccx}
    if kind == "thermal_transient":
        out["time_s"] = _r(res.Time, 3)
        out["time_steps"] = len(results)
    if probes:
        temperature, mechanics = kind != "static", kind not in ("thermal_steady", "thermal_transient")
        out["probes"] = [_probe(res, p, temperature, mechanics) for p in probes]
        if kind == "thermal_transient":
            for row, point in zip(out["probes"], probes, strict=True):
                row["history_s_c"] = _history(results, point)
    return out
