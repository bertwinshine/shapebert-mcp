# Domain: Fasteners, holes, threads and fits

Covers every hole that takes a bolt, screw, pin, insert or shaft: clearance and
tapped holes, counterbores/countersinks, thread engagement, hole patterns, and
ISO 286 fits for shafts/bores/bearing seats. This domain is a SECONDARY overlay:
load it together with the main domain (bracket, gearbox, weldment, printed part)
whenever the part has mating holes. Use `calc_fasteners` for all numbers.
Tags: [CODIFIED] = in a standard, [RULE] = industry rule of thumb,
[CERT] = needs a formal/certified calculation.

---

## 1. Reality check to tell the user
- Hole sizes, counterbores and fits here are standard values for modelling and
  drawings. Bolt preload/strength of a critical joint (VDI 2230) is [CERT].
- CAD models are built at NOMINAL size; tolerances and fits belong on the drawing
  (or in the STEP PMI), not in the solid. Exception: 3D-printed parts, where the
  printed clearance must be modelled (see fdm-3d-printing.md).

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Which screw/bolt size (M3...M20) and head type (socket cap, countersunk, hex).
2. Is the hole a CLEARANCE hole (bolt passes through) or TAPPED (thread in this
   part)? If tapped: the part material (steel, aluminium, plastic) - sets depth.
3. Does the hole pattern have to MATCH another part? Then get the exact pattern
   (pitch circle, spacing) - never invent it.
4. For shafts/bores: nominal diameter and the function (free running, sliding,
   located, pressed, bearing seat) - this picks the fit.
5. Manufacturing route: machined, laser-cut, printed (changes what is modelled).
If the user says "just pick sensible values": medium clearance holes, socket cap
screws, H7/g6 for sliding, H7/k6 for keyed hubs, and REPORT each choice.

## 3. Core calculations (run before assigning values) -> `calc_fasteners`
- Clearance hole (ISO 273 fine/medium/coarse): `bolt_hole(size, fit)`;
  medium is the default; coarse for laser-cut/welded parts with poor positioning.
- Tap drill (coarse thread) ~= d - P (M6: 5.0, M8: 6.8, M10: 8.5) [CODIFIED].
- Thread engagement (length in the TAPPED part) [RULE]:
  steel ~1.0 d, cast iron/brass ~1.25 d, aluminium ~1.5-2 d, plastic ~2 d or use
  inserts. Tapped hole depth ~ engagement + 3P; drill depth ~ tapped depth + 0.5 d.
- Counterbore for ISO 4762 socket cap (DIN 974-1): M3 6.5, M4 8, M5 10, M6 11,
  M8 15, M10 18, M12 20 mm; depth ~ head height k (= d) + 0.4 mm.
- Countersink 90 deg for ISO 10642: diameter ~ 2 d + 0.4 mm [RULE].
- Fits (ISO 286): `fit(d_mm, "H7/g6")` -> limits, min/max clearance, type.
  Common hole-basis fits:
  - H8/f7 running (plain bearings), H7/g6 sliding/locating,
  - H7/h6 location with clearance (assemble by hand),
  - H7/k6 transition (keyed gears/couplings, light press),
  - H7/n6 firm transition, H7/p6 light press without key.
- Rolling-bearing seats [RULE]: rotating inner ring under load -> shaft k5/k6/m6;
  stationary outer ring -> housing H7 (J7 if it must not creep).
- Dowel pins (ISO 8734 m6 pins): hole H7 in both parts, or H7 in one and a slip
  fit in the other for removability.

## 4. Verification checks (must verify, report result)
1. Edge distance and hole pitch: the minimums from `calc_fasteners` (conventions.md,
   "Spacing and material rules"); custom circular flanges use the same rule. For
   sheet metal use the sheet-metal rules instead.
   Standard pipe flanges (EN 1092-1, from `calc_flanges`): the standard fixes the
   outside diameter, bolt circle and hole size, and its rim is narrower than these
   rules. Build it as the standard gives, leave out the edge-distance check, and say so.
2. Counterbore/countersink does not break through the part or into a neighbour.
3. Tapped depth < part thickness - 1 mm (or a through tap is intended).
4. Wrench/hex-key access: clear space above the head >= head height + key length.
5. Pattern matches the mating part exactly (measure both with `measure`; the
   cylindrical_faces_by_diameter output confirms hole count and size).

## 5. Vocabulary / forms
clearance hole, tapped/threaded hole, tap drill, thread pitch, coarse/fine thread,
engagement length, blind/through hole, counterbore (spotface), countersink,
socket head cap screw (SHCS), countersunk screw, hex bolt, nut, washer, helicoil,
heat-set insert, dowel pin, pitch circle diameter (PCD), bolt pattern, fit,
tolerance zone, IT grade, hole basis, clearance/transition/interference fit.

## 6. Standards to respect (paraphrased - never reproduce standards text)
- ISO 273 - clearance holes for bolts and screws (fine/medium/coarse series).
- ISO 261 / ISO 965 - ISO metric threads, pitches and tolerances.
- ISO 4762 (socket cap), ISO 10642 (countersunk socket), ISO 4014/4017 (hex).
- DIN 974-1 - counterbore diameters; ISO 15065 - countersinks for screws.
- ISO 286-1/-2 - limits and fits; ISO 2768 - general tolerances (m = medium).
- ISO 8734 - dowel pins; VDI 2230 - systematic bolted-joint calculation [CERT].
- EN 1993-1-8 Table 3.3 - minimum end/edge distance and bolt spacing in structural
  steelwork (`calc_fasteners` rule `steel_structure`).
Tell the user bolt strength/preload for a critical joint is a separate VDI 2230 step.

## 7. Manufacturing limits and design rules
- Prefer the same screw size on one part (fewer tools, fewer mistakes).
- Blind tapped holes: leave thread run-out; edge distance as section 4 (d0 = tap drill).
- Laser/plasma-cut holes: min hole diameter ~ 1 x material thickness [RULE].
- Printed holes shrink: model printed clearance holes +0.2-0.3 mm, or drill out.
- Never thread directly into soft plastic for repeated assembly: use inserts.

## 8. CAD approach in FreeCAD
- Model holes at nominal size with `Part.makeCylinder` cuts or PartDesign Hole
  (PartDesign::Hole supports ISO threads, counterbores and countersinks and
  records the thread for the drawing - preferred when building in a Body).
- Put screw size and pattern in the Params spreadsheet so the pattern can change.
- After building: `measure` -> check the hole count per diameter matches.

## 9. Build sequence the assistant should follow
1. Ask the section-2 questions; stop only if an input you need to choose a dimension is missing.
2. `calc_fasteners bolt_hole` for each screw size; `fit` for each shaft/bore.
3. Check edge distances and access (section 4) on paper before modelling.
4. Build holes; verify with `measure` / `check_geometry`.
5. Report sizes, fits and anything that needs a VDI 2230 check.

## 10. Always be honest about limits
- Say which sizes were given vs defaulted (e.g. "medium clearance by default").
- Tables are the common published values; check the standard/supplier for production.
