# Domain: Shafts, keys and rolling bearings

Covers transmission shafts up to ~120 mm, shaft-hub connections (parallel keys,
press fits, circlips), rolling-bearing selection by rating life, and bearing seats
and shoulders. Pairs naturally with gears-power-transmission.md (every gear needs a
shaft and bearings) and fasteners-fits.md (seat fits). Use `calc_shafts`.
Tags: [CODIFIED] = in a standard, [RULE] = industry rule of thumb,
[CERT] = needs a formal/certified calculation.

---

## 1. Reality check to tell the user
- Diameters here are a static first pass. Rotating shafts usually fail by fatigue
  at notches (keyways, shoulders, grooves): a DIN 743 / FKM check is [CERT].
- Bearing life uses catalogue C values; take them from the maker (SKF, Schaeffler,
  NSK) for the exact bearing - the assistant must not invent C.

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. Torque T [N.m] (or power + speed) and speed n [rpm] for each shaft.
2. Loads on the shaft: gear/pulley forces and their positions along the shaft
   (gives the bending moment); axial loads (helical gears, preload).
3. Required bearing life in hours (or the machine type) and reliability.
4. Material (e.g. C45, 42CrMo4) and heat treatment; space envelope.
5. How hubs are fixed: key, press fit, clamp, spline.
If the user says "just pick sensible values", use C45 normalised (f_y ~ 340 MPa),
safety 2, deep-groove ball bearings, 20 000 h, and REPORT each choice.

## 3. Core calculations (run before assigning values) -> `calc_shafts`
- Torque: T = 9550 P / n.
- Bending moment from the load positions (simple beam between the bearings):
  single load F at distance a and b from the bearings: M_max = F a b / (a + b).
- Diameter (max shear stress, combined): d = (16 sqrt(M^2 + T^2) / (pi tau_allow))^(1/3),
  tau_allow = 0.5 f_y / S; reduce ~25 % at a keyway [RULE]. -> `shaft_diameter`.
- Round up to a preferred size / bearing bore (bores step 5 mm from 20 mm).
- Parallel key DIN 6885: b x h from the shaft diameter; surface pressure
  p = 2T / (d (h - t1) l_eff) <= ~100 MPa steel hub, 50-60 MPa cast iron/Al [RULE];
  l_eff = l - b for rounded (form A) keys. -> `key`.
- Bearing life ISO 281: L10 = (C/P)^p million rev (p = 3 ball, 10/3 roller);
  L10h = L10 * 10^6 / (60 n). -> `bearing_life`; P = X Fr + Y Fa (`equivalent_load`).
- Typical life targets [RULE]: occasional use 1-5 kh; 8 h/day machinery 20-30 kh;
  gearboxes 20-50 kh; continuous 24 h duty 50-100 kh.
- Deflection [RULE]: at a gear mesh <= ~0.01 x module; slope at a ball bearing
  <= ~0.002 rad (cylindrical roller ~0.001 rad).

## 4. Verification checks (must verify, report result)
1. Shaft d >= d_min from combined stress, at every section (smallest section at
   a notch governs).
2. Key pressure within the limit; hub length >= ~1.0-1.5 d.
3. Bearing L10h >= required life; static check P0 <= C0 / s0 (s0 >= 1-2).
4. Shoulder height: big enough to locate the bearing but below the inner-ring
   shoulder diameter given in the catalogue (d_a min/max) so it can be removed.
5. Fillet radius at shoulders <= the bearing's corner chamfer r_s min, else the
   bearing does not sit flat.

## 5. Vocabulary / forms
shaft, journal, shoulder, fillet/undercut (DIN 509), keyway, parallel key, Woodruff
key, spline, circlip (DIN 471 shaft / DIN 472 bore), retaining ring groove, locknut
(KM/MB), spacer, deep-groove ball bearing (6000/6200/6300 series), angular-contact,
tapered roller, cylindrical roller, needle bearing, locating/non-locating bearing,
C (dynamic) and C0 (static) load rating, L10, preload, seal, housing bore.

## 6. Standards to respect (paraphrased - never reproduce standards text)
- DIN 743 - load capacity of shafts (fatigue with notch factors) [CERT].
- DIN 6885-1 - parallel keys and keyways; DIN 6892 - key calculation.
- ISO 281 - rolling-bearing dynamic rating life; ISO 76 - static rating.
- ISO 15 - radial bearing boundary dimensions (bore/OD/width series).
- DIN 471/472 - retaining rings; DIN 509 - undercuts (relief grooves).
- ISO 286 - fits for seats (see fasteners-fits.md).
Tell the user a DIN 743 fatigue check is a separate step.

## 7. Manufacturing limits and design rules
- Locating/non-locating arrangement: one bearing fixes the shaft axially, the
  other floats, so thermal growth does not load the bearings.
- Keep shoulders to one side where possible so all parts slide on from one end.
- Use generous fillets (r >= 0.1 d where the bearing allows) to cut notch stress.
- Keyway ends: sled-runner (milled with a side cutter) has lower stress than
  end-milled pockets.
- Grind bearing seats; mark seat fits on the drawing (k6/m6 shaft, H7 housing).

## 8. CAD approach in FreeCAD
- Model the shaft as one revolved sketch (PartDesign Revolution) of the stepped
  profile, driven by Params (diameters, lengths); add keyways as pockets.
- Bearings: model as simple rings with catalogue bore/OD/width (or import the
  supplier STEP); keep them as separate bodies.
- Check fits and shoulder diameters with `measure` against the catalogue values.

## 9. Build sequence the assistant should follow
1. Ask section-2 questions; stop if loads or speed are missing and you must size the
   shaft from them. If the diameters are given, build them.
2. Compute T, bending moments, d_min; choose diameters and bearing bores.
3. Select keys and check pressure; choose bearings and check L10h.
4. Build the stepped shaft, keyways, grooves; verify geometry.
5. Report all values, the fits to put on the drawing, and the DIN 743 step.

## 10. Always be honest about limits
- Static sizing only; fatigue governs. Catalogue C values must come from the maker.
