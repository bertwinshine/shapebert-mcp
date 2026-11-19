# Example: shaft with a DIN 6885 form A keyway (rounded ends)

**Prompt it answers:** "40 mm shaft, 120 mm long, with a standard keyway 45 mm long in the middle"

**Domain:** shafts-bearings

**Ask first if not given:** shaft diameter and length? keyway length and position?

**Conventions used:** key width b and shaft groove depth t1 from `calc_shafts
key(d_mm=40)` (DIN 6885: b = 12 mm, t1 = 5.0 mm); shaft along +Z from Z = 0; keyway on
the +X side; every size in Params.

**Verified FreeCAD code (change the values in `params` to fit the request):**

```python
import FreeCAD as App

doc = App.ActiveDocument or App.newDocument()

params = {
    "ShaftD": "40 mm",
    "ShaftL": "120 mm",
    "KeyB": "12 mm",  # DIN 6885 width for 38 < d <= 44
    "KeyT1": "5 mm",  # DIN 6885 shaft groove depth
    "KeyL": "45 mm",  # overall keyway length including the rounded ends
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


shaft = doc.addObject("Part::Cylinder", "Shaft")
bind(shaft, {"Radius": "Params.ShaftD / 2", "Height": "Params.ShaftL"})

# Form A keyway = a straight slot plus a round end at each side, cut from +X.
# The tools stick out 1 mm past the surface so the cut is clean.
floor_x = "Params.ShaftD / 2 - Params.KeyT1"
first_end_z = "(Params.ShaftL - Params.KeyL) / 2 + Params.KeyB / 2"
second_end_z = "(Params.ShaftL + Params.KeyL) / 2 - Params.KeyB / 2"

slot = doc.addObject("Part::Box", "KeySlot")
bind(
    slot,
    {
        "Length": "Params.KeyT1 + 1 mm",
        "Width": "Params.KeyB",
        "Height": "Params.KeyL - Params.KeyB",
        "Placement.Base.x": floor_x,
        "Placement.Base.y": "-Params.KeyB / 2",
        "Placement.Base.z": first_end_z,
    },
)
ends = []
for i, z in enumerate((first_end_z, second_end_z), start=1):
    end = doc.addObject("Part::Cylinder", f"KeyEnd{i}")
    end.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), 90)  # cylinder axis along +X
    bind(
        end,
        {
            "Radius": "Params.KeyB / 2",
            "Height": "Params.KeyT1 + 1 mm",
            "Placement.Base.x": floor_x,
            "Placement.Base.z": z,
        },
    )
    ends.append(end)
keyway = doc.addObject("Part::MultiFuse", "Keyway")
keyway.Shapes = [slot, *ends]

part = doc.addObject("Part::Cut", "KeyedShaft")
part.Base = shaft
part.Tool = keyway
part.Label = "Result"
doc.recompute()

result = {"valid": part.Shape.isValid(), "volume_mm3": round(part.Shape.Volume, 1)}
```

**To change the part later:** change `ShaftL` and the keyway stays centred; for another
diameter take the new `KeyB` and `KeyT1` from `calc_shafts key`.

**Verified by:** author (live FreeCAD test, Nov 2026)
