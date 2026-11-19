# Example: rectangular plate with two mounting holes and a central post

**Prompt it answers:** "make a plate with two mounting holes and a post in the centre"

**Ask first if not given:** plate size? which bolt for the holes (M3/M4/M5/M6)?
post diameter and height?

**Conventions used:** clearance holes per conventions.md; edge distance = 2 x hole
diameter; features centred; every driving size in Params ("Clean, editable models").

**Verified FreeCAD code (change the values in `params` to fit the request):**

```python
import FreeCAD as App

doc = App.ActiveDocument or App.newDocument()

# Every driving size lives in the spreadsheet. Change one there and the part rebuilds.
params = {
    "PlateL": "60 mm",
    "PlateW": "30 mm",
    "Thk": "5 mm",
    "HoleD": "4.5 mm",  # M4 medium clearance (conventions.md)
    "Edge": "9 mm",  # edge distance = 2 x hole diameter
    "PostD": "16 mm",
    "PostH": "30 mm",
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


# Parametric primitives, not Part.makeBox: their sizes and positions are expressions.
plate = doc.addObject("Part::Box", "Plate")
bind(plate, {"Length": "Params.PlateL", "Width": "Params.PlateW", "Height": "Params.Thk"})

holes = []
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
    holes.append(hole)
hole_tools = doc.addObject("Part::MultiFuse", "HoleTools")
hole_tools.Shapes = holes

drilled = doc.addObject("Part::Cut", "DrilledPlate")
drilled.Base = plate
drilled.Tool = hole_tools

post = doc.addObject("Part::Cylinder", "Post")
bind(
    post,
    {
        "Radius": "Params.PostD / 2",
        "Height": "Params.PostH",
        "Placement.Base.x": "Params.PlateL / 2",
        "Placement.Base.y": "Params.PlateW / 2",
        "Placement.Base.z": "Params.Thk",
    },
)

# The final feature itself is the result: no copy into a static Part::Feature.
part = doc.addObject("Part::Fuse", "PlateWithPost")
part.Base = drilled
part.Tool = post
part.Label = "Result"
doc.recompute()

result = {"valid": part.Shape.isValid(), "volume_mm3": round(part.Shape.Volume, 1)}
```

**To change the part later:** edit a value in the Params sheet (for example `Thk` to
8 mm) and recompute; holes and post follow. For a hole COUNT that changes, use a
PartDesign PolarPattern / LinearPattern with `Occurrences` bound to Params instead of
the loop above.

**Notes:** holes sit symmetric along the length and centred across the width. Before
shrinking the plate, check the material left between each hole and the plate edge still
meets conventions.md. For a small plate, a large bolt may not fit - warn instead of
overlapping material.

**Verified by:** author (visual check in FreeCAD); rewritten parametric in Nov 2026
