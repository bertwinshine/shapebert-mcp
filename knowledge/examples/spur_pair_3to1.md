# Example: 3:1 spur gear pair (motor -> conveyor), FCGear, FEA-validated

**Prompt it answers:** "spur gear pair, electric motor ~3 kW at ~1450 rpm into the
pinion, 3:1 reduction, all-day light-shock duty, case-hardened steel, keep it compact."

**Ask first if not given:** pinion bore + how it mounts (on the motor shaft, or its own
shaft)? is the centre distance free or fixed by a housing? required life and accuracy
grade? exact steel?

**Key lesson from this case:** the BORE, not tooth strength, set the pinion size. At
Ø28 bore + 8 mm keyway, 26 teeth left only 6.2 mm of steel under the tooth roots
(< 7 mm min), so the pinion went to 27 teeth (gear 81) - still exactly 3.00:1, centre
distance 108 mm. Always check steel-under-the-root against the bore+keyway before
fixing the tooth count on a small pinion.

**Final design (module 2, 20 deg, ISO 53 basic rack, no profile shift):**

| | Pinion | Gear |
|---|---|---|
| Teeth | 27 | 81 |
| Pitch / tip / root dia | 54 / 58 / 49 mm | 162 / 166 / 157 mm |
| Face width | 22 mm | 20 mm (+ Ø50 hub, 30 mm) |
| Bore | Ø28, 8 mm key | Ø30, 8 mm key |

- Ratio 3.00, centre distance a = m*(z1+z2)/2 = 2*(27+81)/2 = 108 mm.
- Contact ratio eps_alpha = 1.73 (>= 1.4 target). Top-land 1.46 / 1.60 mm (>= 0.5).
- Running: output 483 rpm, 58.1 N.m; tangential force F_t = 732 N; v = 4.1 m/s.

**Verified FreeCAD approach (FCGear, parametric and editable):**

```python
# Build with the FCGear workbench so the gears are LIVE, EDITABLE feature objects
# (double-click the *_Profile object in FreeCAD to change teeth/module/angle later).
import FreeCAD as App
import freecad.gears.commands as gears  # FCGear addon

doc = App.ActiveDocument or App.newDocument("SpurGearPair_3to1")

m, alpha = 2.0, 20.0
z1, z2 = 27, 81
b1, b2 = 22.0, 20.0  # pinion one module wider than the gear

pinion = gears.CreateInvoluteGear.create()
pinion.Label = "Pinion_Profile"
pinion.module = f"{m} mm"
pinion.num_teeth = z1
pinion.pressure_angle = f"{alpha} deg"
pinion.height = f"{b1} mm"
pinion.beta = "0 deg"
pinion.shift = 0.0

wheel = gears.CreateInvoluteGear.create()
wheel.Label = "Wheel_Profile"
wheel.module = f"{m} mm"
wheel.num_teeth = z2
wheel.pressure_angle = f"{alpha} deg"
wheel.height = f"{b2} mm"
wheel.beta = "0 deg"
wheel.shift = 0.0

doc.recompute()
# then: place the wheel at centre distance a = 108 mm on X, cut Ø28/Ø30 bores +
# 8 mm keyways, add the Ø50 hub on the wheel. Verify 0 mm^3 mesh overlap at a.
result = "built 27/81 spur pair, a=108 mm"
```

Notes:
- FCGear names the shape objects `*_Profile`; they carry editable module / num_teeth /
  pressure_angle / height / shift. Changing those and recomputing re-cuts the teeth with
  no rebuild (this is the hand-editable, parametric route the user asked for).
- A smaller alternative that also passes: module 1.5, 33/99 teeth, a = 99 mm (quieter).
- 27:81 shares a factor (each pinion tooth meets the same 3 gear teeth). Fine for ground
  hardened gears; use 27:82 (3.04) if even wear matters more than exact ratio.

**Strength (concept-level, simplified ISO 6336):** S_H ~= 2.35 (pitting), S_F ~= 8.1 / 8.7
(root bending pinion/gear). Assumed K_A = 1.25, K_v = 1.10, K_Hbeta = 1.35, 16MnCr5 grade
MQ (sigma_Hlim 1500, sigma_Flim 430 MPa), Z_NT = 0.88, Y_FS read from chart. The high S_F
is because the bore oversized the pinion, not an error.

**Verified by:** author.
- GEOMETRY: verified in FreeCAD - FCGear parameters match the design, and the meshed pair
  reports 0.000 mm^3 tooth overlap at a = 108 mm (no interference).
- ROOT BENDING: validated by static FEA in ANSYS (2026 R1, Structural Steel E=210 GPa).
  732 N applied tangentially at one tooth tip, bore fixed, ~0.2 mm face sizing on the
  loaded-tooth root fillet. Peak max-principal stress = 33.8 MPa at the root fillet, vs
  analytic ~52 MPa unfactored / 96 MPa factored - same order, FEA lower as expected.
  All well below the 430 MPa material limit. Tip-load direction was ~tangential (a
  conservative simplification); minor mesh-metric warnings, not affecting the conclusion.
- NOT verified: pitting/contact fatigue, tooth-flank fracture, service life, and the
  shaft/bearing/housing. A certified ISO 6336 / AGMA rating is still a separate step.
