# Example: plate with counterbored holes for socket-head screws

**Prompt it answers:** "plate 80 x 50 x 12 with two counterbored holes for M6 socket-head screws"

**Domain:** fasteners-fits

**Ask first if not given:** plate size? screw size? where the holes sit?

**Conventions used:** clearance, counterbore diameter and depth from `calc_fasteners
bolt_hole(size="M6", head="socket")`; every size in Params; counterbore measured from
the top face so it follows a thickness change.

**Verified FreeCAD code (change the values in `params` to fit the request):**

```python
import FreeCAD as App

doc = App.ActiveDocument or App.newDocument()

params = {
    "PlateL": "80 mm",
    "PlateW": "50 mm",
    "Thk": "12 mm",
    "HoleD": "6.6 mm",  # M6 medium clearance
    "CbD": "11 mm",  # counterbore for an ISO 4762 M6 head
    "CbDepth": "6.4 mm",  # head height 6 mm + 0.4 mm so the head sits below the surface
    "Edge": "15 mm",  # hole centre from each short edge, on the long centre line
}
sheet = doc.getObject("Params") or doc.addObject("Spreadsheet::Sheet", "Params")
for row, (alias, value) in enumerate(params.items(), start=1):
    sheet.set(f"A{row}", alias)
    sheet.set(f"B{row}", f"={value}")
    sheet.setAlias(f"B{row}", alias)
doc.recompute()


def bind(obj, expressions):
    for prop, expr in expressions.items():
        obj.setExpression(prop, expr)


plate = doc.addObject("Part::Box", "Plate")
bind(plate, {"Length": "Params.PlateL", "Width": "Params.PlateW", "Height": "Params.Thk"})

tools = []
for i, x in enumerate(("Params.Edge", "Params.PlateL - Params.Edge"), start=1):
    hole = doc.addObject("Part::Cylinder", f"Hole{i}")
    bind(
        hole,
        {
            "Radius": "Params.HoleD / 2",
            "Height": "Params.Thk",
            "Placement.Base.x": x,
            "Placement.Base.y": "Params.PlateW / 2",
        },
    )
    # The counterbore hangs from the top face: its base is Thk - CbDepth.
    counterbore = doc.addObject("Part::Cylinder", f"Counterbore{i}")
    bind(
        counterbore,
        {
            "Radius": "Params.CbD / 2",
            "Height": "Params.CbDepth",
            "Placement.Base.x": x,
            "Placement.Base.y": "Params.PlateW / 2",
            "Placement.Base.z": "Params.Thk - Params.CbDepth",
        },
    )
    tools += [hole, counterbore]
hole_tools = doc.addObject("Part::MultiFuse", "HoleTools")
hole_tools.Shapes = tools

part = doc.addObject("Part::Cut", "CounterboredPlate")
part.Base = plate
part.Tool = hole_tools
part.Label = "Result"
doc.recompute()

result = {"valid": part.Shape.isValid(), "volume_mm3": round(part.Shape.Volume, 1)}
```

**To change the part later:** change `Thk` and the counterbores stay at the top face;
change `Edge` and both holes move symmetrically.

**Verified by:** author (live FreeCAD test, Nov 2026)
