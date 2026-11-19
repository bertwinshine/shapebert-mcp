# Domain: Sheet metal

Covers laser/punch + press-brake bent parts: brackets, enclosures, panels, chassis.
Compute the flat pattern (section 3) and run the DFM checks (section 4/7) BEFORE
fixing dimensions. Ask the section-2 questions first.
Tags: [CODIFIED] = in a standard, [RULE] = industry rule of thumb,
[CERT] = needs a formal/certified calculation.

---

## 1. Reality check to tell the user
- Flat patterns depend on the real K-factor, which depends on the material and the
  shop's tooling. Table K-factors are a starting point; a measured test-bend value
  from the fabricator overrides them.
- Structural/fatigue adequacy of a loaded bracket is [CERT] (FEA or hand calc).

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Material grade and temper (e.g. DC01/DC04 mild steel, 1.4301/304 stainless,
   5754-H22 / 6061-T6 aluminium). Temper changes the minimum radius a lot.
2. Sheet thickness t (from a stocked series).
3. Bending method / tooling: air bending (most common), bottoming, coining; and the
   available V-die / punch radii - or let the K-factor and radius come from the shop.
4. Which dimensions are critical (inside vs outside), and the general tolerance class.
5. Coating/finish (powder coat, galvanising add thickness), grain-direction limits,
   hardware (PEM inserts) and quantity (prototype vs progressive die).
If the user says "just pick sensible values", use section-3 defaults and REPORT each.

## 3. Core calculations (run before assigning values)
Symbols: t = thickness, R = inside bend radius, A = bend angle [deg] (90 for an L),
K = K-factor, beta = DIN opening angle = 180 - A.
- K-factor: K = t_n / t (t_n = inside surface to neutral axis). Neutral radius R_n = R + K*t.
- Bend allowance: BA = (pi/180) * A * (R + K*t)
- Outside setback: OSSB = tan(A/2) * (R + t)
- Bend deduction: BD = 2*OSSB - BA
- Flat length: L_flat = sum(outside flange dims) - sum(BD)  [= sum(flats) + sum(BA)]
- Back-calc K from a test bend: K = (180*BA)/(pi*A*t) - R/t  (test bends beat tables)
- Y-factor (some CAD): Y = K*pi/2
DIN 6935 method (German practice) - choose ONE convention and keep it:
- correction factor k = 0.65 + 0.5*lg(r/s), k=1 for r/s>5; neutral fibre at (s/2)*k.
- NOTE DIN k is NOT the US K-factor; relation K = k/2. Don't mix them.
Air-bending geometry:
- inside radius R_i ~= 0.16*V (mild steel air-forms 15-17% of die opening; 304 ~20-22%)
- die opening V ~= 8*t start (range 6-12*t); min flange b_min ~= 0.77*V (Bystronic)
Press-brake force (air, metric): F[kN] ~= 1.42 * Rm[MPa] * t^2[mm] * L[m] / V[mm].
  Bottoming needs up to ~5x, coining ~5-30x that force. Doubling t quadruples force.
Springback: grows with yield and R/t; air bending compensates by overbending, so no
CAD compensation is needed - just the finished angle and tolerance.

## 4. Verification checks (must verify, report result)
1. Flat pattern closes: unfolded length = folded outside dims minus BD per bend.
   Cross-check FreeCAD SheetMetal "Unfold" against a hand BA/BD for one bend.
2. R_i >= material minimum for the grade/temper (cracking risk at R/t < 1 for hard tempers).
3. Every flange >= b_min for the chosen V-die (>= ~4*t, or 4*t + R conservative).
4. Feature-to-bend and feature-to-edge distances meet section-7 rules.
5. Reliefs exist where a bend ends at a cut edge or meets another bend; box corners relieved.
6. Longest bend within machine tonnage and brake length.
7. Uniform thickness throughout - one thickness per part.
8. Loaded brackets: structural/fatigue check [CERT].

## 5. Vocabulary / forms
flat pattern/blank, unfold/refold, bend line, inside/outside radius, neutral axis,
K-factor, Y-factor, DIN k, bend allowance/deduction, outside setback, flange, return
flange, edge/miter flange, jog/offset, hem (open/closed/teardrop), curl, bend relief
(rectangular/obround/tear), corner relief, notch, tab, slot, lance, louver,
emboss/bead/rib, dimple, extruded/flanged hole, countersink, PEM hardware, air
bending, bottoming, coining, V-die opening, tonnage, springback, grain direction.

## 6. Standards to respect (paraphrased - do not reproduce standards text)
- DIN 6935 - cold bending of flat steel: min radii, factor k, stretched-length v.
- ISO 2768-1/-2 - general linear/angular and geometrical tolerances (-m or -c common).
- ISO 7438 - bend test (material ductility, not a design rule).
- EN 10130 (DC01-DC07 grades) and DIN EN 10131 (cold-rolled tolerances, 0.35-3 mm).
- EN 10088 (stainless), EN 485 / EN 573 (aluminium sheet).
- ISO 9013 - thermal-cut (laser/plasma) classification and tolerances.
Tell the user that measured test-bend K and shop tooling override these tables.

## 7. Manufacturing limits and design rules (all [RULE]; confirm with fabricator)
- Uniform wall; use the same inside radius on all bends to avoid tool changes.
- Min flange length >= 4*t (or 0.77*V-die; conservative 4*t + R).
- Holes: dia >= t (punched; stainless >= 2*t); hole-edge to part-edge >= 1.5*t;
  hole to hole >= 2*t; hole-edge to bend >= 2*t from tangent (or 2.5*t + R from bend line).
- Bend relief: width >= t, depth >= R + t (or 1.5*t). Corner reliefs at box corners.
- Notch width >= t (>= 1 mm), tab width >= 2*t (>= 3.2 mm); cutout inside corners >= 0.5*t.
- Hems: open-hem return >= 4*t (some shops 6*t); avoid closed flat hems in hard tempers.
- Countersink: depth <= 0.6*t; to edge >= 4*t; to bend >= 3*t.
- Keep louvers/embosses/lances >= ~3*t from holes and clear of bends (>= ~3*t + R).
- Process: laser mild steel commonly to ~20-25 mm; turret punch thin sheet to ~6 mm;
  bend sequence must avoid punch/die collision with already-formed flanges.

## 8. CAD approach in FreeCAD
- Profiles bent in one direction only (L, U/channel, Z, hat, any row of bends): use
  `build_sheet_profile` (no addon needed). It takes the OUTSIDE flange dimensions and
  signed bend angles and returns the solid plus the flat length (same maths as
  calc_sheet_metal flat_length). Cut holes and notches afterwards.
- Parts folded in several directions (boxes, enclosures, trays): use the SheetMetal
  workbench (addon): base wall, then bends (set t, R_i, K), then "Unfold" to get the
  flat. Drive t, R, K and relief sizes from a Spreadsheet. Run `doctor` first; if it is
  missing, tell the user and give the install steps, never install it yourself.
- Pick ONE K convention (US K-factor vs DIN k) and store it per material.
- Recompute, verify the solid, and report t, R_i, K, flat-pattern length and bend count.

## 9. Build sequence
1. Ask section-2 questions; stop only if an input you need to choose a dimension is missing.
2. Choose t, R_i (default 1*t) and K (default 0.44 air/mild) - report them.
3. Model walls and bends; add reliefs; place holes/features per section-7 distances.
4. Unfold; cross-check the flat length against a hand BA/BD for one bend.
5. Check flange >= b_min, feature distances, press force within tonnage.
6. Report all values with tags; flag any loaded-bracket strength check as [CERT].

## 10. Default values (state the tag when used)
- inside radius R_i = 1*t [RULE] (mild/stainless/soft alu); 6061-T6 needs ~2-4*t
- K-factor air bending: mild steel/5052 ~0.44, soft alu ~0.33, stainless ~0.40-0.48 [RULE]
- die opening V = 8*t [RULE]; min flange ~4*t or 0.77*V [RULE]
- metric stock t: 0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10 mm
- general tolerance ISO 2768-m; per-bend dimension ~+/-0.2-0.5 mm, angle ~+/-0.5deg

## 11. Always be honest about limits
- Say which numbers were assumed vs given.
- Table K-factors are preliminary; the fabricator's measured value wins.
