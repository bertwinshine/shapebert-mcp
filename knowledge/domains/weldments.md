# Domain: Weldments and welded frames

Covers welded steel frames from standard profiles (RHS/SHS/CHS, IPE/HEA/HEB, UPN,
angles) with fillet and butt welds. Size welds (section 3) and run the checks
(section 4) BEFORE fixing member sizes or weld legs. Ask the section-2 questions first.
Tags: [CODIFIED] = in a standard, [RULE] = industry rule of thumb,
[CERT] = needs a formal/certified calculation.

---

## 1. Reality check to tell the user
- Weld and member sizing here is concept level. Structural joint verification, member
  buckling and fatigue are [CERT] under EN 1993 / AISC, and execution/qualification
  (EN 1090, WPS/WPQR, preheat) are separate steps. Say so.
- Fatigue usually governs cyclically loaded frames and overrides static weld sizing.

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Loads and load cases (static / dynamic-fatigue / impact) with magnitude, direction
   and point; supports; deflection limits.
2. Governing code: building structure (EN 1993 + EN 1090) vs machine frame vs US
   (AISC 360 / AWS D1.1).
3. Execution class EXC1-EXC4 (EN 1090-2) -> weld quality level (ISO 5817 D/C/B).
4. Steel grade and toughness subgrade (S235JR/J0/J2, S355J2...; hollow S355J2H) and
   available profile stock/thicknesses.
5. Welding process available (MAG/135, TIG/141, MMA/111), shop vs site, finish
   (paint / hot-dip galvanising -> needs vent holes), machining-after-welding needs.
If the user says "just pick sensible values", use section-3 defaults and REPORT each.

## 3. Core calculations (run before assigning values)
Fillet weld geometry:
- throat a = z/sqrt(2) ~= 0.707*z ; leg z = a*sqrt(2) ~= 1.41*a (e.g. z=7 <-> a=5)
- EU drawings dimension by throat "a" (ISO 2553 "a5"); AWS uses leg size.
EN 1993-1-8 fillet resistance (conceptual):
- effective length l_eff = length - end craters; ignore welds with l_eff < max(30 mm, 6a); a >= 3 mm.
- correlation factor beta_w: S235=0.80, S275=0.85, S355=0.90, S420/460=1.00; gamma_M2=1.25.
- simplified: F_w,Rd = f_vw,d * a per unit length, f_vw,d = (f_u/sqrt(3))/(beta_w*gamma_M2)
  -> S235 (f_u=360) ~= 208 MPa ; S355 (f_u=470) ~= 241 MPa.
  Example: a=5 mm in S355 ~= 1.2 kN/mm. (Conservative - treats resultant as throat shear.)
- directional method: resolve to sigma_perp, tau_perp, tau_par; check
  sqrt(sigma_perp^2 + 3*(tau_perp^2 + tau_par^2)) <= f_u/(beta_w*gamma_M2) AND
  sigma_perp <= 0.9*f_u/gamma_M2.
- full-penetration butt welds: resistance = the weaker connected part (matching
  consumables) - no separate weld calc beyond the member check.
Weld group under eccentric load (concept): treat weld as a line, A_w = sum(a*l),
polar moment J_w; tau_direct = F/A_w, tau_torsion = M*r/J_w, combine vectorially.
Weldability: carbon equivalent CEV = C + Mn/6 + (Cr+Mo+V)/5 + (Ni+Cu)/15 [%];
preheat from EN 1011-2.

## 4. Verification checks (must verify, report result)
1. Each weld: a >= 3 mm; a >= code minimum for thickness; a <= max for edge/thin part;
   l_eff >= max(30 mm, 6a); stress utilisation <= 1.0 [CERT for structures].
2. Members and joints: member capacity, local plate bending, RHS face yielding /
   punching shear (EN 1993-1-8 ch.7 hollow-section joints) [CERT].
3. Fatigue if loads cycle (FAT detail category); intermittent welds/weld-ends are poor
   fatigue details [CERT].
4. Quality level consistent with execution class: EXC1->D, EXC2->C, EXC3->B, EXC4->B+.
5. Weldability: CEV/preheat per EN 1011-2; toughness subgrade vs temperature/thickness.
6. DFM/geometry: torch access, no crossing welds without copes, galvanising vents.

## 5. Vocabulary / forms
weldment, member, profile (IPE, HEA/HEB/HEM, UPN/UPE, L-angle, flat bar, SHS/RHS/CHS),
cold-formed vs hot-finished, corner radius, cope/snipe, mitre, saddle/fish-mouth cut,
end cap, gusset, stiffener, end/base plate, cleat; joints (butt, T, corner, lap,
cruciform); weld types (fillet, square/single-V/double-V(X), bevel, U, J, plug/slot,
spot); throat a, leg z, penetration s, root, root face, root gap, bevel angle, toe,
HAZ, preheat, interpass, heat input, CEV, PWHT, distortion, tack weld, back-step,
skip weld, continuous vs intermittent, weld-all-round, execution class EXC, quality
level B/C/D, NDT (VT/MT/PT/UT/RT), WPS/WPQR.

## 6. Standards to respect (paraphrased - do not reproduce standards text)
- ISO 2553 - weld symbols. System A (EU, dual reference line) vs System B (~AWS);
  never mix. Size prefixes: a = throat, z = leg, s = penetration.
- ISO 5817 - quality levels B (stringent) / C / D (moderate) for arc-welded joints.
- EN 1993-1-8 - design of joints (fillet/butt resistance, min throat, effective length).
- EN 1993-1-1 / -1-9 / -1-10 - members, fatigue, toughness selection.
- EN 1090-1/-2 - execution of steel structures and CE conformity (execution classes).
- ISO 3834 (quality system), EN ISO 9606-1 / ISO 15614-1 (welder/procedure qualification).
- EN 10210/10219 - hot-finished / cold-formed hollow sections; EN 10365 (I/H/U dims);
  EN 10056 (angles); EN 10025-2 (S235-S355 grades incl. CEV limits).
- ISO 9692-1 - joint preparations; EN 1011-2 - preheat; EN ISO 13920 - weldment
  tolerances; EN ISO 14713-2 - design for galvanising; ISO 4063 - process numbers.
- AWS D1.1 / AISC 360 / AWS A2.4 - US structural welding, design, symbols.
Tell the user EN 1993/AISC joint + member + fatigue verification is a certified step.

## 7. Manufacturing limits and design rules
- Fillet sizing: specify the MINIMUM size that meets strength + the code minimum.
  Over-welding adds no design strength (strength is on the throat) but adds shrinkage,
  distortion, heat and cost. Weld volume rises with a^2 (a=7 uses ~2x the metal of a=5).
  Prefer double-sided smaller fillets over one large single-sided fillet.
- AWS D1.1 min fillet leg (heat-input floor): t<=6 -> 3 mm; 6-13 -> 5; 13-19 -> 6;
  19-38 -> 8; >38 -> 10 mm. Max fillet along a plate edge: leg = t (t<6), t-1.6 (t>=6).
- Joint prep (ISO 9692-1): square butt t<=4; single-V 3<t<=10 (40-60deg, gap<=4,
  root face<=2); broad-root-face V 5<=t<=40; U/steep for t>12-16. Thick plate: prefer
  double-sided (X) prep to halve weld volume and balance distortion [RULE].
- Intermittent welds: only lightly loaded stiffeners / distortion control; avoid in
  corrosive/outdoor or fatigue. Callout a5 n x l (e).
- Distortion control (TWI): minimise weld metal; balance welds about the neutral axis;
  good fit-up; preset for angular pull; back-step/skip sequences; weld parts back-to-back.
- Access: ~45deg approach and ~20-30 mm nozzle clearance; avoid welds in closed narrow
  channels [RULE].
- Gussets/stiffeners: snipe/cope inside corners (~15-25 mm or >=2x weld leg) so welds
  don't cross and clear the profile root radius; wrap ends where practical.
- Tube frames: SHS/RHS mitre (45deg) is clean but needs accurate cutting; butt/notched
  is cheaper; CHS-CHS needs saddle (fish-mouth) cuts; weld on flats (flat width = b - 2*r_o);
  cap/seal tubes and add galvanising vent/drain holes (EN ISO 14713-2).
- Machining after welding: add ~2-5 mm stock on machined faces; specify stress relief
  for tight tolerances; use EN ISO 13920 general tolerances.

## 8. CAD approach in FreeCAD
- Build members from standard profile sketches swept along frame edges (a wireframe
  skeleton drives member placement). The Arch/BIM workbench carries structural profile
  libraries; or sketch the profile and sweep. Drive profile sizes from a Spreadsheet.
- Add copes/snipes at intersections; model fillet welds only where useful (welds are
  usually a drawing callout, not solid geometry) - record throat a in feature notes.
- Recompute, verify solids, and report profiles, weld throats, and quality level.

## 9. Build sequence
1. Ask section-2 questions; stop only if an input you need to choose a dimension is missing.
2. Pick steel grade and execution class -> target quality level.
3. Choose profiles from stock; build the frame skeleton and sweep members.
4. Size fillets on the throat (a = 0.707*z, a >= 3 mm, >= code min for thickness);
   check utilisation with the simplified method.
5. Add copes/snipes; set weld callouts (ISO 2553); plan weld sequence for distortion.
6. Report profiles, weld sizes, CEV/preheat note, and list the [CERT] verifications.

## 10. Default values (state the tag when used)
- min fillet throat a = 3 mm [CODIFIED EN 1993-1-8]; machine-frame default
  a ~= 0.5-0.7*t_min continuous double-sided [RULE] - calculate for loaded joints.
- grade S235 or S355; quality level C (EXC2) as a general default [RULE].
- f_vw,d: S235 ~= 208 MPa, S355 ~= 241 MPa (simplified method).
- CEV bands: <0.35 excellent (no preheat), 0.35-0.45 good, 0.45-0.60 preheat ~50-150C.
- RHS/SHS corner radius for modelling: EN 10219 outer r_o = 2.0*t (t<=6), 2.5*t
  (6-10), 3.0*t (>10); EN 10210 r_o = 1.5*t.

## 11. Always be honest about limits
- Say which numbers were assumed vs given.
- Call the weld/member/fatigue verification and EN 1090 execution certified steps.
