# Example: welded rectangular frame from square hollow section (SHS), mitred corners

**Prompt it answers:** "welded frame 800 x 500 mm lying flat, from SHS 50x50x4, mitred corners, one solid"

**Domain:** weldments

**Ask first if not given:** outside size? profile and wall thickness? lying flat or standing?

**Conventions used:** sharp-cornered profile (corner radii ignored unless asked); every
size in Params. A mitred rectangular frame of one profile is the same solid as a closed
hollow ring, so it is built as a ring: no rotated mitre cuts needed.

**The trap:** the tube is closed on top and bottom. The cavity is only `S - 2*T` high and
starts at `z = T`. A cavity as tall as the tube cuts through the top and bottom walls
and leaves two separate thin rings (2 solids, about half the volume).

**Check:** volume = centre-line length x profile area = 2*((L - S) + (W - S)) x (S^2 - (S - 2T)^2).
Here 2*(750 + 450) x (2500 - 1764) = 2400 x 736 = 1,766,400 mm^3.

**Verified FreeCAD code (change the values in `params` to fit the request):**

```python
import FreeCAD as App

doc = App.ActiveDocument or App.newDocument()

params = {
    "FrameL": "800 mm",
    "FrameW": "500 mm",
    "ProfS": "50 mm",  # outside size of the square tube
    "Wall": "4 mm",  # wall thickness of the tube
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


def box(name, expressions):
    obj = doc.addObject("Part::Box", name)
    bind(obj, expressions)
    return obj


def cut(name, base, tool):
    obj = doc.addObject("Part::Cut", name)
    obj.Base = base
    obj.Tool = tool
    return obj


# Solid ring: outside rectangle minus the opening in the middle.
outer = box("Outer", {"Length": "Params.FrameL", "Width": "Params.FrameW", "Height": "Params.ProfS"})
opening = box(
    "Opening",
    {
        "Length": "Params.FrameL - 2 * Params.ProfS",
        "Width": "Params.FrameW - 2 * Params.ProfS",
        "Height": "Params.ProfS",
        "Placement.Base.x": "Params.ProfS",
        "Placement.Base.y": "Params.ProfS",
    },
)
ring = cut("SolidRing", outer, opening)

# Cavity ring inside the tubes: inset by the wall on all sides, including top and bottom.
cavity_outer = box(
    "CavityOuter",
    {
        "Length": "Params.FrameL - 2 * Params.Wall",
        "Width": "Params.FrameW - 2 * Params.Wall",
        "Height": "Params.ProfS - 2 * Params.Wall",
        "Placement.Base.x": "Params.Wall",
        "Placement.Base.y": "Params.Wall",
        "Placement.Base.z": "Params.Wall",
    },
)
cavity_inner = box(
    "CavityInner",
    {
        "Length": "Params.FrameL - 2 * Params.ProfS + 2 * Params.Wall",
        "Width": "Params.FrameW - 2 * Params.ProfS + 2 * Params.Wall",
        "Height": "Params.ProfS - 2 * Params.Wall",
        "Placement.Base.x": "Params.ProfS - Params.Wall",
        "Placement.Base.y": "Params.ProfS - Params.Wall",
        "Placement.Base.z": "Params.Wall",
    },
)
cavity = cut("Cavity", cavity_outer, cavity_inner)

part = cut("Frame", ring, cavity)
part.Label = "Result"
doc.recompute()

shape = part.Shape
expected = 2 * (800 - 50 + 500 - 50) * (50**2 - 42**2)
result = {
    "valid": shape.isValid(),
    "solids": len(shape.Solids),
    "volume_mm3": round(shape.Volume, 1),
    "expected_mm3": expected,
}
```

**To change the part later:** change `FrameL`, `FrameW`, `ProfS` or `Wall` in Params; the
ring and the cavity follow. For a different profile per side, or gussets and cross
members, build each member separately and fuse them.

**Verified by:** author (live FreeCAD test, Nov 2026)
