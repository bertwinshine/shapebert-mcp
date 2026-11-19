# Domain: Gears and power transmission

Covers spur, helical, bevel, worm and planetary gears up to concept/parametric
level. Run the section-3 calculations and the section-4 checks BEFORE assigning any
tooth count, module or face width. Ask the section-2 questions first.
Tags: [CODIFIED] = in a standard, [RULE] = industry rule of thumb,
[CERT] = needs a formal/certified calculation beyond concept-level CAD.

---

## 1. Reality check to tell the user
- This produces concept-level geometry and first-pass sizing only. A production gear
  needs a certified rating (ISO 6336 / AGMA) with the real load spectrum, plus shaft,
  bearing and housing checks. Say so.
- Lewis bending here is a quick sanity check, not a rating. Final strength is [CERT].

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Power P [kW] OR torque T [N.m] at a named shaft, and input speed n [rpm].
2. Required ratio i (and tolerance), and shaft layout: parallel (spur/helical),
   intersecting (bevel), crossed (worm).
3. Duty/shock: driver (motor, engine) and driven machine (uniform / moderate /
   heavy shock) -> sets application factor K_A. Daily hours and required life.
4. Space envelope: max centre distance, max outside diameter, face width limit.
   Is the centre distance fixed? (a fixed centre distance forces profile shift.)
5. Material / heat treatment preference and manufacturing route (hobbed, moulded,
   3D-printed). Accuracy/noise (ISO 1328 grade) and backlash need.
If the user says "just pick sensible values", use section-3 defaults and REPORT each.

## 3. Core calculations (run before assigning values)
Power/torque/force:
- T [N.m] = 9550 * P [kW] / n [rpm];  omega = 2*pi*n/60
- Tangential force F_t [N] = 2000 * T [N.m] / d [mm]
- Pitch-line velocity v [m/s] = pi * d[mm] * n / 60000

Spur geometry (standard full-depth, x=0) [CODIFIED basic rack ISO 53 / DIN 867]:
- module m = d/z ; pitch diameter d = m*z ; circular pitch p = pi*m
- addendum = 1.0*m ; dedendum = 1.25*m ; whole depth = 2.25*m ; clearance = 0.25*m
- tip dia d_a = m*(z+2) ; root dia d_f = m*(z-2.5) ; base circle d_b = d*cos(alpha)
- centre distance a = m*(z1+z2)/2 ; ratio i = z2/z1 = n1/n2
- contact ratio: keep eps_alpha >= 1.2 absolute min [RULE]; 20deg pairs reach ~1.4-1.8

Undercut / profile shift:
- min teeth without undercut z_min = 2/sin^2(alpha): ~17 at 20deg, ~32 at 14.5deg,
  ~12 at 25deg (~14 accepted at 20deg with slight undercut).
- shift to avoid undercut x_min ~= (17 - z)/17 at 20deg. Positive shift thickens the
  root but sharpens the tip -> check top land s_a >= ~0.2-0.4*m [RULE].

Helical: m_t = m_n/cos(beta); d = m_n*z/cos(beta); beta ~15-30deg [RULE];
overlap ratio eps_beta = b*sin(beta)/(pi*m_n), aim >= 1 for quiet running.

Planetary (single planets):
- ring fixed, sun in, carrier out: i = 1 + z_R/z_S (single-stage ~3:1 to 10:1)
- coaxial: z_R = z_S + 2*z_P ; assembly (equal spacing): (z_S + z_R)/N = integer
- adjacency: (z_P + 2) < (z_S + z_P)*sin(pi/N)

Strength - Lewis (quick, concept level only):
- sigma_F = F_t / (K_v * b * m * Y), Y ~0.30-0.35 for 20-30 teeth at 20deg.
- size face width: b = SF * F_t / (sigma_allow * Y * m * K_v).
Strength - ISO 6336 / DIN 3990 is the real rating [CERT]: root bending (Part 3) and
pitting (Part 2), with K_A, K_v, K_Hbeta/K_Fbeta, K_Halpha/K_Falpha factors.

## 4. Verification checks (must verify, report result)
1. z1 >= z_min (or x >= x_min); top land s_a >= ~0.25*m; eps_alpha >= 1.2 (aim 1.4+).
   Planetary: coaxial + assembly + adjacency conditions all met.
2. Root bending sigma_F <= allowable for BOTH pinion and wheel (Lewis first pass;
   ISO 6336-3 to rate) [CERT for production].
3. Pitting sigma_H <= allowable (ISO 6336-2) [CERT].
4. Peak/start-up torque vs static strength. Shaft/bearing/housing check needed too.

## 5. Vocabulary / forms
module, pressure angle (20deg default), pitch/base/tip/root circle, addendum,
dedendum, profile shift x, undercut, contact ratio (eps_alpha / eps_beta), helix
angle, lead, hand LH/RH, face width, backlash, pinion/wheel, rack, internal/ring
gear, sun/planet/carrier (epicyclic), worm/worm wheel, starts, lead angle,
self-locking, bevel cone angle, hunting tooth, K_A, K_v, Lewis form factor Y.

## 6. Standards to respect (paraphrased - do not reproduce standards text)
- ISO 53 / DIN 867 - standard basic rack (20deg, ha=m, hf=1.25m, fillet ~0.38m).
- ISO 54 / DIN 780 - preferred modules (Series I).
- ISO 21771 / DIN 3960 - cylindrical gear geometry and terminology.
- ISO 6336-1/-2/-3/-5/-6 - load capacity (Part 5 = material strength by grade ML/MQ/ME).
- DIN 3990 - German predecessor of ISO 6336 (same factor structure).
- ISO 10300 / DIN 3991 - bevel; ISO/TS 14521 / DIN 3996 - worm.
- ISO 1328 / DIN 3961-3962 - accuracy grades; AGMA 2001/2101 - US rating counterpart.
- DIN 3967 - backlash/tooth-thickness allowances; DIN 3964 - centre-distance tol.
- VDI 2736 - plastic gears (rate plastics with this, not ISO 6336).
Tell the user a certified ISO 6336 / AGMA rating is a separate step.

## 7. Manufacturing limits and design rules
- Use ISO 54 modules and 20deg to stay within standard hob/shaper/cutter tooling;
  non-standard modules need special tools [RULE].
- Hobbing cannot cut against a close shoulder - leave hob run-out, or use shaping.
- Internal gears: min tooth-count difference z_R - z_P ~>= 10-12 at 20deg [RULE].
- Rim under the root >= ~3.5*m_n or the thin-rim factor applies.
- Add tip chamfer ~0.1-0.2*m and full root fillet ~0.38*m for bending strength.
- Specify backlash by tooth-thickness allowance (span Wk / over-pins), not CAD gap.
- 3D-printed/moulded: use m >= 1, avoid z < 12, add 0.1-0.2 mm clearance [RULE].

## 8. CAD approach in FreeCAD
- Spur gears: use the `build_spur_gear` tool (exact involute, bore and keyway, no
  addon needed). Never draw the tooth curves yourself.
- Internal (ring) gears for planetary stages: use `build_ring_gear` (no addon needed).
  Give the ring the same profile shift as the planets; check the tooth counts with
  calc_gears first (ring = sun + 2 x planet, (sun + ring) / planets is a whole number).
- Helical, bevel and worm gears: the FCGear workbench (addon), driven from a
  Spreadsheet via run_freecad_code, if it is installed. Run `doctor` to check; if it is
  missing, tell the user and give the install steps, never install it yourself.
- Always recompute, confirm a valid solid, and report m, z1/z2, a, b and ratio.

## 9. Build sequence
1. Ask section-2 questions; stop only if an input you need to choose a dimension is missing.
2. Compute T and F_t; pick m from ISO 54, alpha = 20deg, z1 >= 17 (or set x).
3. Set face width b = 8-16*m [RULE]; solve z2 for the ratio; compute a, d, d_a, d_f.
4. Lewis sanity check on bending for pinion AND wheel.
5. Build geometry (`build_spur_gear`, `build_ring_gear`, or FCGear for other types), verify the solid.
6. Report all values with tags; list what needs a certified ISO 6336 rating.

## 10. Default values (state the tag when used)
- module from ISO 54 Series I: 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10... (avoid 6.5)
- pressure angle 20deg [CODIFIED]; face width b = 10*m [RULE] (range 8-16*m)
- pinion z1 >= 17 [RULE]; accuracy grade 7-8 (normal hobbed) [RULE]
- ratio per stage: spur <=5-6, helical <=8-10, bevel <=5, worm 5-75, planetary 3-10
- min safety factors (uncertain inputs): S_F >= 1.4-1.5, S_H >= 1.0-1.2 [RULE]

## 11. Always be honest about limits
- Say which numbers were assumed vs given.
- Lewis and these defaults are preliminary; call final strength a certified step.
