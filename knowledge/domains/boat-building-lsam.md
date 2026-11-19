# Domain: Boat building (payload craft) for LSAM manufacture

Use this file for any boat / hull / deck / marine-craft request. Do the
calculations in section 3 and the checks in section 4 BEFORE assigning hull
dimensions or building geometry. Ask the section-2 questions first.

Scope: normal small craft up to ~24 m hull length, with a stated payload /
person capacity, intended to be made by Large Scale Additive Manufacturing (LSAM)
— either the hull directly, or (more realistic today) an LSAM mould/plug.

---

## 1. Reality check to tell the user
- Full-size one-piece 3D-printed FRP hulls are still experimental (e.g. the
  University of Maine "3Dirigo" demo). The proven marine use of LSAM today is
  printing **moulds / plugs**, then laying up the hull in the mould.
- So by default, treat the LSAM output as a **mould or a segmented hull**, not a
  finished one-piece structural hull, unless the user explicitly wants a direct
  print and accepts the limitations in section 7.
- Prompt-to-CAD can give a fair *concept / parametric* hull to a target
  displacement. A production-quality faired surface still needs refinement in the
  Ship workbench or dedicated hull software, and a human fairing check.

---

## 2. Ask the user first (critical inputs — do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Intended water / use → design category: A ocean, B offshore, C inshore,
   D sheltered waters.
2. Payload: number of persons and total max load (kg), plus fresh or salt water.
3. Hull type wanted: displacement, semi-displacement, or planing.
4. Principal dimensions OR a target: either give L, B, T, or give target
   displacement / capacity and let the tool solve for size.
5. Design speed (knots) — needed to choose Cp and check the speed regime.
6. Manufacture intent: LSAM direct hull, LSAM mould, or segmented print.
7. Material (if LSAM): e.g. chopped-carbon-fibre reinforced thermoplastic.

If the user says "just pick sensible values", use the ranges below and REPORT
every value chosen.

---

## 3. Core calculations (run these before assigning values)

Symbols: L = waterline length (m), B = beam (m), T = draft (m),
rho = water density (seawater 1025 kg/m^3, fresh 1000 kg/m^3), g = 9.81 m/s^2.

- Displaced volume:            nabla = L * B * T * Cb        (m^3)
- Displacement (mass):         Delta = nabla * rho           (kg)
- Archimedes (must balance):   Delta = light_mass + max_load (the boat must float
  carrying its own weight + payload; buoyancy = weight)
- Block coefficient:           Cb = nabla / (L * B * T)
- Midship coefficient:         Cm = Am / (B * T)   (Am = midship section area)
- Prismatic coefficient:       Cp = nabla / (Am * L) = Cb / Cm
- Waterplane coefficient:      Cwp = Awp / (L * B)  (Awp = waterplane area)
- Froude number:               Fn = V / sqrt(g * L)   (V in m/s; 1 knot = 0.5144 m/s)

Typical target ranges (small craft):
- Cb: fine/fast ~0.40-0.55; moderate ~0.55-0.65; full displacement up to ~0.85.
- Cp: fine hulls ~0.55-0.65; optimum rises with speed (Troost: Fn 0.20 -> Cp~0.62,
  Fn 0.30 -> Cp~0.74).
- Speed regime by Fn: displacement roughly Fn < 0.4; semi-displacement ~0.4-1.0;
  planing Fn > ~1.0. Pick hull type consistent with the user's speed.

Payload / capacity:
- Delta (fully loaded) = light craft mass + maximum load (ISO 14946 basis:
  persons + stores + tank contents + ballast).
- Check the chosen hull at design draft actually displaces >= Delta_loaded.
  If not, increase size or Cb, or reduce payload — tell the user.

---

## 4. Stability check (must verify, report result)
- Metacentric height:  GM = KB + BM - KG
  - KB = vertical centre of buoyancy above keel (approx 0.5*T for simple forms)
  - BM = I_T / nabla   (I_T = transverse second moment of the waterplane area)
  - KG = vertical centre of gravity above keel (from the loaded weight layout)
- Require GM > 0 (positive initial stability). A very small GM = "tender"
  (slow, rolly); a very large GM = "stiff" (short, uncomfortable roll).
- GM is only valid for small heel (~0-15 deg). Full assessment and the design
  category (A/B/C/D) are governed by ISO 12217 — flag that a formal check is
  needed for certification.

---

## 5. Hull and deck forms (vocabulary to build with)
Hull types:
- Displacement: pushes water aside, slow, efficient, stable (round-bilge common).
- Planing: rises and skims at speed; usually V-bottom with hard chines.
- Semi-displacement: hybrid; V-bottom, part lift part displacement.
Bottom shapes: flat bottom (simple planing), V-bottom / deep-V (rougher water),
round-bilge (displacement), hard-chine (planing, easier to panel/print).
Key hull curves to loft through: a series of transverse "station" sections from
bow to stern, plus sheer line (deck edge), chine line, and keel line.
Deck: typically a separate part joined to the hull; has sheer (curve fore-aft)
and camber (crown across the beam) for water run-off and strength.

---

## 6. Standards to respect (paraphrased — do not reproduce the standards text)
- ISO 8666 — principal data and dimensions; keeps all the numbers consistent.
- ISO 12215 — hull construction and scantlings (Part 5: monohull design
  pressures and scantling determination; Part 7: multihulls; Parts 2/3 materials).
- ISO 12217 — stability and buoyancy assessment and design category (Part 1
  non-sailing >=6 m, Part 2 sailing >=6 m, Part 3 boats <6 m).
- ISO 14946 — maximum load capacity (defines what counts toward max load).
- ISO 12216 — cockpit/window openings & flooding; ISO 15083 — bilge pumping.
- EU Recreational Craft Directive 2013/53/EU — CE marking, design categories.
- ASTM F2792 — standard terminology for additive manufacturing.
Treat these as "what to check against", and tell the user a formal, certified
calculation is a separate step beyond the CAD concept.

---

## 7. LSAM manufacturing limits and design rules
Process facts:
- Bead-based extrusion: layer width ~120-180% of nozzle diameter; layer height
  ~1/4 to 2/3 of layer width. Typical bead/layer ~2-10 mm.
- High deposition (e.g. Oak Ridge BAAM up to ~45 kg/h) but coarse resolution.
- Material often chopped-carbon-fibre reinforced thermoplastic (e.g. ~20% CF).

Design rules to bake into geometry:
- Minimum wall = about 2 x bead width (a double bead); minimum feature size also
  about 2 x bead width. Don't design walls thinner than one bead.
- Anisotropy: layer (Z) direction is the WEAK direction. Orient the part so
  primary structural loads run along the beads (in-plane), not across layers.
- Overhangs: 3-axis printing cannot self-support steep overhangs. Keep overhang
  within a self-supporting angle, print the shape as an open mould, or segment it.
- Surface finish is rough: add a machining allowance (a few mm) on any surface
  that must seal, mate, or be smooth (e.g. mould face, hull-to-deck joint).
- Warping / thermal distortion: large flat spans warp. Prefer curved/ribbed forms,
  design shrinkage allowance, and avoid large unsupported flats.
- Print envelope: if the hull exceeds the machine volume, SEGMENT it into
  printable sections with jointing features, and tell the user.
- Design FOR the bead, not just for the 45 deg rule (a multi-hull concept failed
  exactly this):
  - Every feature must grow out of the main body as a wide, stiff form (walls,
    closed sections, solid fillets). Thin struts or webs that lean out across open
    air between separate bodies (e.g. multi-hull connectors) are NOT printable in
    one piece, even at exactly 45 deg: warm thin PETG sags, wobbles and gets pushed
    by the nozzle. Make those separate parts, or close the gap with a solid form.
  - A per-face slope check misses bridges. A 45 deg face meeting a face that is
    vertical in print leaves an edge hanging in air. Also check layer by layer:
    slice the part every half bead height and look for islands with no support below.
  - A 45 deg plate must grow from its lowest end (floor or wall), never from a
    free edge. In print orientation, crosswise items (seats, backrests, bulkheads)
    can only lean one way; plan the layout around that.
  - Faces at exactly 45 deg are at the limit. Say so, and suggest a test print.
  - If the user asks for innovation, a bold form that the process cannot build is
    NOT a valid answer. Check printability of the concept BEFORE showing it as an
    option, and label anything that is form-only as "concept, not LSAM".

When the user wants a MOULD instead of a direct hull:
- Model the hull surface, then offset it to make a mould/tool; the mould face is
  the surface that needs the machining allowance and smoothest finish.

---

## 8. FreeCAD geometry approach (splines / lofts / sweeps)
- Build station sections as wires (BSpline or polyline), then loft through them:
  `Part.makeLoft([wire1, wire2, ...], True)` for a solid, or sections + rails.
- Deck/keel/chine as guide curves; sweep profiles along them where useful
  (`Part.BRepOffsetAPI.MakePipeShell` / `makePipe`).
- Prefer the **Ship workbench** if installed — it is purpose-built for hull
  definition and hydrostatics (volume, Cb, GM). Call it via run_freecad_code.
- Always recompute, check the solid is valid, and measure `Shape.Volume` to
  compare against the target displacement from section 3. Iterate until it matches.

---

## 9. Build sequence the assistant should follow
1. Ask the section-2 questions; stop only if an input you need to choose a dimension is missing.
2. Choose hull type + coefficient targets (section 3) for the stated speed.
3. Solve principal dimensions to meet target displacement AND payload.
4. Build station sections, loft the hull, recompute, measure volume.
5. Compare measured volume to target; adjust and re-loft until within tolerance.
6. Do the stability sanity check (section 4); report GM and note ISO 12217 is the
   formal authority.
7. Apply LSAM design rules (section 7) to wall thickness, orientation, segments,
   and machining allowance — or produce a mould if requested.
8. Report every value used, the final volume, and what still needs a human /
   certified check.

---

## 10. Always be honest about limits
- Say which numbers were assumed vs given.
- Say that the hull surface is a concept and needs fairing/verification.
- Say that stability and scantlings here are sanity checks, not certification.
