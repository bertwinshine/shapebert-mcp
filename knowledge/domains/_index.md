# Domain index

This is the catalogue of expert domains. Read it (or call `match_domain`) to decide
which domain file to load for a request. Match the request against the trigger
words; if one domain matches, open its file. If several or none match, ask the user.

| Domain | Trigger words (any of these in the request) | File | Status |
|--------|---------------------------------------------|------|--------|
| Boat building for LSAM | boat, hull, deck, marine, vessel, yacht, catamaran, trimaran, dinghy, kayak, pontoon, LSAM hull | boat-building-lsam.md | complete |
| Gears and power transmission | gear, pinion, spur, helical, bevel, worm, planetary, module, gearbox, transmission, sprocket | gears-power-transmission.md | complete |
| Sheet metal | sheet metal, bend, sheet flange, bent flange, bracket, enclosure, chassis, press brake, K-factor, flat pattern, laser cut | sheet-metal.md | complete |
| Weldments and welded frames | weldment, welded frame, weld, fillet weld, RHS, SHS, CHS, I-beam, IPE, HEA, HEB, UPN, angle, gusset, tube frame | weldments.md | complete |
| Fasteners, holes and fits | bolt, screw, thread, tapped, tap drill, counterbore, countersink, clearance hole, bolt pattern, bolt hole, pitch circle, PCD, M3, M4, M5, M6, M8, M10, M12, M16, M20, dowel, fit, tolerance, press fit, H7, insert | fasteners-fits.md | complete |
| Shafts, keys and bearings | shaft, axle, keyway, key, spline, bearing, ball bearing, roller bearing, circlip, retaining ring, journal, L10 | shafts-bearings.md | complete |
| FDM 3D printing | 3D print, 3D printed, printable, FDM, FFF, PLA, PETG, ABS, ASA, TPU, filament, slicer, heat-set insert, print-in-place | fdm-3d-printing.md | complete |

## Which tools go with which domain

| Domain file | Calculator (exact maths) | Model checks (inside FreeCAD) |
|-------------|--------------------------|-------------------------------|
| boat-building-lsam.md | `calc_boat` | `hydrostatics`, `check_printability(process='lsam')` |
| gears-power-transmission.md | `calc_gears` | `measure` (tip/root dia), `check_geometry` |
| sheet-metal.md | `calc_sheet_metal` | `measure` (flat length vs calc) |
| weldments.md | `calc_weld` | `measure(density=7850)` for frame mass |
| fasteners-fits.md | `calc_fasteners` | `measure` (holes by diameter) |
| shafts-bearings.md | `calc_shafts` | `measure` |
| fdm-3d-printing.md | - | `check_printability(process='fdm')`, `measure` |

Domains often combine: a gearbox = gears + shafts-bearings + fasteners-fits; a
printed bracket = fdm-3d-printing + fasteners-fits. Load the main domain first,
then the secondary ones for the features they cover.

## How to add a new domain (3 steps)
1. Copy `_template.md` to `<your-domain>.md` and fill in its sections.
2. Add one row to the table above: name, trigger words, filename, status.
3. Done. `CLAUDE.md` and `match_domain` find it automatically through this index.
   (Optional 4th step: add a calculator module in `cadkit/calculators/` + a test.)

Notes:
- Keep trigger words specific enough not to collide with other domains.
- Mark Status as `stub` while a file is still a skeleton, `complete` once its
  calculations, standards and limits are filled and checked.
- Files beginning with `_` (this index, the template) are NOT domains - skip them
  when matching a request.
