# CAD conventions and default values

Follow these unless the user says otherwise. They replace guessing.

## Units
- All dimensions in millimetres (mm) unless stated.

## Metric clearance holes (medium fit, ISO 273)
Hole diameter for a bolt passing THROUGH:
- M3 -> 3.4 mm
- M4 -> 4.5 mm
- M5 -> 5.5 mm
- M6 -> 6.6 mm
- M8 -> 9.0 mm

## Default fastener choice
- There is NO safe default bolt size for mounting holes - ask the user which bolt
  (M3 / M4 / M5 / M6) the part must take.
- Only if they decline to choose, use M4 for a general bracket and say so.

## Spacing and material rules (keep parts manufacturable)
- Edge distance: a hole centre must be at least 2 x hole diameter from any edge.
  (Plates and brackets. Bolted circular flanges: see fasteners-fits.md, ~1.1-1.5 x d.)
- Between two holes: at least 1 x hole diameter of solid material between their edges.
- Between a hole and another feature (e.g. a boss): at least 1.5 mm of material.
- If the requested holes do NOT fit these rules on the given part, SAY SO and suggest
  a smaller hole or a bigger part - do not silently overlap material.

## Fillets and chamfers
- "Rounded edges" with no size -> use a 1 mm fillet and report it.
- Never make a fillet/chamfer larger than half the thinnest adjacent wall.

## Positioning
- "Centre" = the geometric middle of the parent face or part. Compute it; never just
  drop the feature at the origin.
- Keep features symmetric unless told otherwise.

## FreeCAD 1.x API
- For a symmetric Pad or Pocket, set the `SideType` property to its symmetric option
  instead of `Midplane = True`, which still works but prints a deprecation warning.
  `feature.getEnumerationsOfProperty("SideType")` lists the option names.

## Always verify
- Recompute after each change.
- Confirm the result is a single valid solid, and report its volume in mm^3.

## Clean, editable models
A part is only finished when someone can change a size and it still rebuilds.
- Every driving size (lengths, diameters, counts) lives in the Params spreadsheet
  (`set_parameters`) and the features read it with expressions.
- Attach sketches to the base planes (XY, XZ, YZ) or to datum planes, never to a face
  of an earlier feature: face names change when the geometry changes.
- Prefer one PartDesign Body or a clean chain of Part features. Name features after
  what they are (Plate, BoltHoles, Bore), not Pad001 / Cut003.
- The final feature itself carries the label `Result`. Never copy its shape into a
  new Part::Feature: a copy is frozen and ignores every later change.
- Patterns for repeated features, with the count bound to Params.
- If a fix fails twice, rebuild the part cleanly instead of patching on top.
- Check with `check_model_structure` and fix what it lists before reporting.
- Worked parametric examples: plate_with_holes (holes, post), counterbored_plate,
  keyed_shaft (rounded keyway), flange_bolt_circle (hole COUNT as a parameter),
  shs_frame (hollow-profile frame; the tube cavity is closed top and bottom).
- How to bind, in short (full pattern: examples/plate_with_holes.md):
  `box = doc.addObject("Part::Box", "Plate")` then
  `box.setExpression("Height", "Params.Thk")`, and for positions
  `hole.setExpression("Placement.Base.x", "Params.Edge")`. Combine with Part::Cut /
  Part::Fuse / Part::MultiFuse objects. `Part.makeBox(...)` + `Part::Feature` gives a
  frozen shape that ignores Params - use it only for throw-away checks.
