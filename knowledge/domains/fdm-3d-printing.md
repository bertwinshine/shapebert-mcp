# Domain: FDM 3D printing (desktop / industrial filament printers)

Covers parts printed on filament (FFF/FDM) printers, build volumes up to ~1 m:
PLA, PETG, CF-PETG/CF-PA, ABS/ASA, TPU. For large-scale pellet printing of boats
and moulds use boat-building-lsam.md (same physics, larger beads). Use
`check_printability` (process='fdm') after building.
Tags: [CODIFIED] = in a standard, [RULE] = industry rule of thumb,
[CERT] = needs a formal/certified calculation.

---

## 1. Reality check to tell the user
- Printed parts are anisotropic: across layers (Z) they can be 30-60 % weaker than
  along them. Load-bearing printed parts need testing; numbers here are guides.
- Clearances depend on the printer, nozzle and slicer: the values below are a start;
  a printed test coupon beats any table.

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Printer / build volume and nozzle size (0.4 mm default).
2. Material (PLA, PETG, CF-PETG, ABS/ASA, PA, TPU) and the use temperature.
3. Is the part load-bearing? Which direction does the main load act?
4. Mating parts: what fits with what (press, slide, snap), and are screws used
   (self-tapping, heat-set inserts, nuts)?
5. Surface/appearance needs (which face may show support marks).
If the user says "just pick sensible values": 0.4 mm nozzle, PETG, 0.2 mm layers,
3 perimeters, 20-30 % infill, and REPORT each choice.

## 3. Core calculations (run before assigning values)
- Wall thickness = n_perimeters x line width (0.4 mm nozzle -> ~0.45 mm lines):
  2 walls 0.9, 3 walls 1.35, 4 walls 1.8 mm. Design walls as whole multiples [RULE].
  Absolute minimum wall ~2 x line width (~0.8-1.0 mm); structural >= 1.6-2.4 mm.
- Overhang: <= 45 deg from vertical prints without support [RULE] (PLA up to
  ~55-60 deg on a tuned printer); horizontal bridges up to ~10-20 mm are OK.
- Holes in the XY plane come out undersize: add +0.2-0.3 mm to diameter, or
  model a teardrop / flat top for horizontal holes (axis in XY).
- Clearances between printed parts [RULE]: press 0.0-0.1 mm, snug/slide 0.2 mm,
  free/loose 0.3-0.5 mm per side (print-in-place hinges 0.4-0.5 mm).
- Heat-set inserts: hole per insert maker (e.g. M3 short insert ~4.0-4.2 mm
  diameter); boss OD ~2-2.5 x insert OD. Self-tapping into plastic: hole ~0.85 d.
- Layer height <= 75-80 % of nozzle diameter; 0.2 mm for 0.4 mm nozzle.
- Mass estimate: `measure(name, density)` x (shell share + infill share) -
  PLA 1240, PETG 1270, CF-PETG ~1300, ABS 1040, PA ~1140 kg/m^3.

## 4. Verification checks (must verify, report result)
1. `check_printability(name, process='fdm', build_volume_mm=[...])`:
   needs_support false (or support accepted), fits build volume.
2. Thin walls: no samples below 2 x line width; structural walls >= 1.6 mm.
3. Orientation: the main load runs along the layers, not across them.
4. First layer: a flat face of decent area on the bed (add a chamfer, not a
   fillet, on bed edges to avoid elephant-foot problems).
5. Fits: every mating clearance chosen from section 3 and stated.

## 5. Vocabulary / forms
layer height, line width, perimeter/wall, top/bottom layers, infill, overhang,
bridge, support, brim, raft, elephant foot, warping, seam, teardrop hole,
heat-set insert, print-in-place, snap fit, living hinge, anisotropy, slicer.

## 6. Standards to respect (paraphrased - never reproduce standards text)
- ISO/ASTM 52900 - additive manufacturing terminology.
- ISO/ASTM 52910 - design requirements and guidelines for AM.
- ISO/ASTM 52902 - test artefacts for geometric capability (good for calibration).
Tell the user structural use of printed parts needs testing [CERT].

## 7. Manufacturing limits and design rules
- Replace steep overhangs by 45 deg chamfers; avoid flat ceilings > bridge length.
- Fillet vertical edges (stress), chamfer bed edges (adhesion).
- Avoid tiny features < 2 x line width; text >= 0.6 mm stroke, >= 0.4 mm deep.
- Split big parts with dowel/registration features; joints away from peak stress.
- Warping: large flat ABS/PA parts need enclosure/brim; PETG/PLA less so.

## 8. CAD approach in FreeCAD
- Build in PartDesign with a Params spreadsheet holding wall, clearance and
  nozzle values so fits can be retuned after a test print.
- Export with `export_model(path.3mf or .stl)`; 3MF keeps units and is preferred.
- Run `check_printability` and `measure` before exporting.

## 9. Build sequence the assistant should follow
1. Ask section-2 questions; stop if printer/material/load direction are unknown
   and you must choose the sizes of a structural part.
2. Pick wall multiples, clearances and orientation (section 3).
3. Build; check_geometry; check_printability; adjust overhangs/walls.
4. Export 3MF/STL; report settings, clearances and orientation.

## 10. Always be honest about limits
- State that clearances are starting values to be confirmed with a test print.
- Do not claim a printed part's strength without test data.
