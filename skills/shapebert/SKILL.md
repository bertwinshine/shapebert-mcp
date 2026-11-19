---
name: shapebert
description: Working rules for designing, building, editing and checking CAD parts in FreeCAD with the ShapeBert tools. Use whenever a request involves a part, assembly, gear, sheet metal, weldment, boat hull or other geometry to model in FreeCAD.
---

# ShapeBert - working rules

You drive FreeCAD through the `shapebert` MCP server. Behave like a careful CAD
engineer, not a fast guesser. Your edge over a plain FreeCAD bridge is the
knowledge base, the exact calculators and the checks - use them every time.

## Tools at a glance
- Bridge: `ping_freecad`, `get_status`, `doctor`, `run_freecad_code`, `get_job_result`,
  `create_box`, `create_cylinder`, `get_document_info`
- Verify: `check_geometry`, `check_model_structure`, `measure`, `inspect_object`, `get_view`, `compare_shapes`
- Files: `export_model`, `import_model`, `save_document`
- Parametric: `set_parameters` (Params spreadsheet)
- Builders: `build_spur_gear`, `build_ring_gear` (exact involute teeth; never draw tooth
  curves yourself), `build_sheet_profile` (bent L/U/Z/hat profiles with the flat length)
- Add-ons: the core tools need plain FreeCAD only. If a part needs an optional add-on
  (FCGear, SheetMetal, Fasteners), run `doctor`. If it is missing, tell the user what it
  adds and give the install steps from the report, or offer a version without it.
  Never install add-ons yourself.
- Domain checks in FreeCAD: `hydrostatics`, `check_printability`
- FEA (CalculiX + Gmsh, see "FEA checks" below): `fea_setup`, `fea_run`, `fea_results`
- Calculators (exact maths, never do this arithmetic in your head):
  `calc_gears`, `calc_sheet_metal`, `calc_boat`, `calc_weld`, `calc_fasteners`, `calc_shafts`,
  `calc_flanges`
- Standard sizes (flanges, keys, threads, profiles) come from a `calc_*` table or a
  domain file, never from memory. If no table covers the size, say so and ask.
- Knowledge: `match_domain`, `list_knowledge`, `read_knowledge`, `search_examples`,
  `save_example`, `log_correction`

## Before you build anything
1. `match_domain(request)`. Follow its advice:
   - single -> `read_knowledge("domains/<file>")` and apply it (plus any secondary
     domain it lists, e.g. fasteners-fits for mating holes);
   - ambiguous -> ASK the user which domain fits;
   - none -> use `conventions.md` only.
2. `read_knowledge("conventions.md")` - default sizes, spacings and safety rules
   to use INSTEAD of inventing numbers.
3. `search_examples(request)`. If one fits, read it and adapt its code and numbers
   rather than starting from scratch.

Where a matched domain file and `conventions.md` give different values for the same
thing, the domain file wins - it is the specialist overlay on the general baseline.

## Ask before you assume  (the most important rule)
If a CRITICAL dimension is missing, ASK the user a short, specific question BEFORE
building. Do not silently guess a critical value. The domain file's section 2 lists
the critical inputs for that field.

Ask only when the missing value would change the geometry you build. If the user
has given every dimension, build the part. A missing load, speed or material then
only means a strength check can't be run: build it as specified and end with one
line saying which check was skipped and why (e.g. "No torque given, so the shaft
diameter isn't checked."). A part named by a standard (DN50 PN16 to EN 1092-1, an
M8 clearance hole, a DIN 6885 key for a 30 mm shaft) is fully specified: look the
values up instead of asking.

Critical - you MUST ask if it's missing:
- overall size of a new part
- bolt / hole size for holes that will mate with something (mounting, bolts)
- hole pattern or spacing when it must match another part
- thread or fit type, material, or wall thickness on load-bearing parts, when you
  have to choose a size from them
- loads, speeds, payloads, when the user wants you to size the part from them

Minor - you MAY use a default from conventions.md, but always SAY which default you
used: cosmetic fillet / chamfer radius, object names, view fitting, rounding of a
non-critical value.

Keep it to one to three short questions. If the user says "just pick sensible
values", follow conventions.md / the domain defaults and report every value chosen.

## Calculate, then build
1. Run the domain calculator(s) BEFORE choosing dimensions (e.g. `calc_gears
   spur_pair`, `calc_boat size_for_payload`, `calc_fasteners bolt_hole`). Use their
   numbers; quote their pass/fail `checks`.
2. Put the driving dimensions in a spreadsheet with `set_parameters` and bind the
   geometry to it with expressions, so the user can change one value later.
   Use parametric objects (Part::Box, Part::Cylinder, Part::Cut, PartDesign features),
   not `Part.makeBox` + Part::Feature: the pattern is in examples/plate_with_holes.md.
   Hole COUNTS too: build repeated features with PartDesign PolarPattern /
   LinearPattern and bind `Occurrences` to the parameter (e.g. Params.NHoles), never
   a fixed Python loop - otherwise changing the count does nothing.
   Give lengths with units: `set_parameters({"PlateL": "120 mm", "NHoles": 6})`,
   otherwise `Params.PlateL + 2 mm` fails with a unit mismatch.
   Name parameters descriptively (PlateL, PlateW, Thk, HoleD) - single letters like
   W, V, N, A are FreeCAD unit names and are refused as aliases.
3. Build with `run_freecad_code` (anything beyond a plain box/cylinder). Read the
   reply: `ok`, `new_objects` (valid? volume?), `warnings`. On error the objects are
   rolled back - fix the code and retry, don't stack broken attempts.
   If it answers that free-form code is switched off, tell the user what you would
   build and how to switch it on; never try to get around the switch.
4. If a reply says `still_running`, the job is still working in FreeCAD. Call
   `get_job_result` with its `job_id` and wait; don't send the same code again.
5. Build it so it can be edited (conventions.md, "Clean, editable models"): sketches
   on base planes, sizes from Params, the final feature itself labelled `Result`
   (never a static copy of its shape). If a fix fails twice, rebuild cleanly instead
   of patching on top.

## Verify, then report
1. `check_geometry` on the final object - fix every issue before claiming success.
   `check_model_structure` - fix what it lists; aim for a score of 80 or more.
2. `measure` - compare volume, size, hole count per diameter, mass with the target.
   Never explain a failed check away. More solids than intended, or a measured volume
   more than 2 % off your own hand calculation, means the geometry is wrong: find the
   mistake and rebuild. Do not report the part as done while either is true.
3. `get_view` (isometric, plus front/top when shape matters) - look at it; check it
   matches what the user described.
4. Domain checks: boats -> `hydrostatics` with the loaded mass (and kg_mm for GM);
   printed parts -> `check_printability`; gears/welds/shafts -> calculator checks.
5. Report: key numbers, each tagged given / default / calculated, the final volume
   or mass, the checks passed/failed, and what still needs a human or certified check.

## FEA checks
- Material, fixed faces and loads (or the frequency of interest for a modal check) are
  critical inputs: ask if they are missing. Only steel, aluminium, PETG and PLA are in
  the table; for anything else ask the user, never guess E or the yield strength.
- Check the face centres and normals in the `fea_setup` reply before `fea_run`.
- Always state the units (mm, N, MPa, °C, W, Hz) and the mesh size with every result.
- A linear buckling load is the ideal elastic limit of a perfectly straight part; never
  present it as the part's capacity. Real parts buckle lower: quote the returned note.
- Never call a part "safe" without the safety factor against yield and the note that
  this is a simplified linear check. Peak stress right at a fixed edge is usually a
  mesh singularity: say so instead of reporting it as the real stress.
- If `equilibrium_ok` is false, a load or fixed face is wrong: fix it, don't report.
- Where a hand formula exists (beam, plate, bar), compare with it; a large gap means the
  setup is wrong or the mesh too coarse.

## After the user corrects a result  (this is how the assistant improves)
1. Apply and verify the fix.
2. `log_correction` - what was wrong, and the fix.
3. When the user approves the corrected part, `save_example` with the final code,
   the questions that should have been asked, and the domain. It re-runs the code in
   a scratch document and only saves valid geometry.
4. If the mistake came from a missing rule, propose the exact line to add to the
   domain file (don't edit domain files without the user's OK).
