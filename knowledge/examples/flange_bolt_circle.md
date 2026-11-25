# Example: flange with a bolt circle whose hole COUNT is a parameter

**Prompt it answers:** "flange 160 mm, 16 thick, 60 bore, six M12 holes on a 125 mm pitch circle"

**Domain:** fasteners-fits

**Ask first if not given:** outside diameter, thickness, bore? bolt size, count and
pitch circle? (For a standard pipe flange use `calc_flanges` instead of asking.)

**Conventions used:** clearance hole from `calc_fasteners bolt_hole`; the holes are a
Draft polar array whose count is bound to Params, so changing NHoles from 6 to 8 adds
holes - a Python loop could not do that.

**Verified FreeCAD code (change the values in `params` to fit the request):**

```python
import Draft
import FreeCAD as App

doc = App.ActiveDocument or App.newDocument()

params = {
    "FlangeD": "160 mm",
    "Thk": "16 mm",
    "BoreD": "60 mm",
    "PCD": "125 mm",
    "HoleD": "13.5 mm",  # M12 medium clearance
    "NHoles": "6",  # a count: no unit
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


disk = doc.addObject("Part::Cylinder", "Disk")
bind(disk, {"Radius": "Params.FlangeD / 2", "Height": "Params.Thk"})

bore = doc.addObject("Part::Cylinder", "Bore")
bind(bore, {"Radius": "Params.BoreD / 2", "Height": "Params.Thk"})

# One hole on the pitch circle, then a polar array around Z with the count from Params.
hole = doc.addObject("Part::Cylinder", "BoltHole")
bind(hole, {"Radius": "Params.HoleD / 2", "Height": "Params.Thk", "Placement.Base.x": "Params.PCD / 2"})
holes = Draft.make_polar_array(hole, number=6, angle=360, use_link=False)
holes.Label = "BoltHoles"
holes.setExpression("NumberPolar", "Params.NHoles")

cut_tools = doc.addObject("Part::MultiFuse", "CutTools")
cut_tools.Shapes = [bore, holes]

part = doc.addObject("Part::Cut", "Flange")
part.Base = disk
part.Tool = cut_tools
part.Label = "Result"
doc.recompute()

result = {"valid": part.Shape.isValid(), "volume_mm3": round(part.Shape.Volume, 1)}
```

**To change the part later:** set `NHoles` to 8 and recompute: the array adds the holes
evenly. The same pattern works for any repeated feature (slots, ribs, spokes).

**Edge distance:** this prompt leaves 17.5 mm from hole centre to rim, less than the
`machined` minimum `calc_fasteners bolt_hole(size="M12")` gives, so the `edge_distance`
check fails. The sizes are the user's: build them, keep the failing check in the report
and tell the user (a larger outside diameter or a smaller pitch circle would fix it).

**Verified by:** author (live FreeCAD test, Nov 2026)
