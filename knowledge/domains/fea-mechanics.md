# Domain: FEA and mechanics hand checks

One-line scope: checking parts with ShapeBert's FEA tools (linear static, modal,
buckling, heat conduction, thermal stress) and comparing every result with a
closed-form hand estimate. Ask the section-2 questions first; run the hand check in
section 3 next to every FEA run whose part is close to one of the textbook cases.

---

## 1. Reality check to tell the user
- ShapeBert's FEA is a linear-elastic check: small deformations, ideal supports, no
  contact, no plasticity, no fatigue. It shows whether a design is in the right range
  and where it is loaded; it is not a certified analysis.
- Every FEA number depends on the mesh, the supports and the loads. A result is only
  as good as the hand check it agrees with and the convergence check it passed.
- Stress at a fixed edge, a sharp inside corner or a point load is a singularity: it
  grows without limit as the mesh is refined. Such a peak is never a result.

## 2. Ask the user first (critical inputs - do NOT assume these)
1. Material (only steel, aluminium, PETG and PLA are in ShapeBert's table; for any
   other material ask for E, nu, density, yield and the thermal values).
2. Supports: which faces are held, and how (fully fixed, or free to slide).
3. Loads: size, direction and the face they act on; for a heat problem the face
   temperatures. Ask for the real contact area of a load instead of using a point
   or a tiny face.
4. What matters: peak stress against yield, deflection limit, frequency to avoid,
   buckling margin, temperature limit.
If the user gives all of these, run the analysis and say which checks were skipped.

## 3. Core calculations (run before assigning values)
`calc_hand_check` computes topics 1, 2, 4-10 below. For each topic: formula, what
happens physically, assumptions, where it stops being valid, how 3D FEA differs, how
ShapeBert uses it, and the source.

### Topic 1. Axial bar
- Formula: s = F/A, d = F L / (E A).
- Physically: the load spreads into a uniform stress over the section after the
  Saint-Venant zone, about one width from the load and the supports.
- Assumptions: linear elastic, small strain, prismatic bar, load through the centroid.
- Validity: not near the load or support; not for tapered bars or eccentric loads.
- 3D FEA: matches within a fraction of a percent away from the ends; a support that
  stops lateral contraction raises the stress next to it.
- ShapeBert: `calc_hand_check("axial_bar")`; validation case "Bar in tension".
- Source: Gere & Timoshenko, Mechanics of Materials (SI ed.), Ch. 2 Axially Loaded
  Members, sec. 2.2 (change in length, d = F L / (E A)).

### Topic 2. Bending and the cantilever
- Formula: s = M c / I; cantilever tip d = F L^3 / (3 E I); shear adds F L / (k G A),
  k = 5/6 for a rectangle, G = E / (2 (1 + nu)).
- Physically: one side of the beam stretches, the other shortens; the stress grows
  linearly from the neutral axis.
- Assumptions: plane sections stay plane, slender (L/h above about 10), small
  deflection, linear elastic.
- Validity: short beams (L/h under about 10) need the shear term or more; large
  deflections need a non-linear analysis.
- 3D FEA: slightly softer than Euler-Bernoulli, by a few tenths of a percent at
  L/h = 10. The root stress is singular where the clamped face meets the top and
  bottom faces.
- ShapeBert: `calc_hand_check("cantilever")`; validation case "Cantilever, end load".
- Source: Gere & Timoshenko, Mechanics of Materials (SI ed.), Ch. 9 (beam deflection,
  shear deflection), section to be checked.

### Topic 3. Torsion
- Formula: t = T r / J, J = pi d^4 / 32 for a solid round shaft (circular sections only).
- Physically: a round section twists as a whole without warping; the shear stress
  grows linearly from the centre.
- Assumptions: circular (solid or tube) section, linear elastic, small twist.
- Validity: non-circular sections warp, and T r / J is wrong for them: use the
  St-Venant torsion constants from Roark.
- 3D FEA: matches for round shafts away from the ends; for other sections FEA is the
  better answer, and Roark's constants are the hand check.
- ShapeBert: no `calc_hand_check` case yet; `calc_shafts` sizes round shafts.
- Source: Gere & Timoshenko, Mechanics of Materials (SI ed.), Ch. 3 (torsion), section to
  be checked; Roark's Formulas for Stress and Strain, 8th ed., Young, Budynas &
  Sadegh, McGraw-Hill 2012, Ch. 10 Torsion (non-circular sections).

### Topic 4. Thin-walled pressure vessel
- Formula: s_hoop = p r / t, s_axial = p r / (2 t).
- Physically: the wall carries the pressure as a uniform membrane stress.
- Assumptions: thin wall, closed ends, away from the end caps and nozzles.
- Validity: r/t above about 10; thicker walls need Lame (topic 5).
- 3D FEA: matches in the middle of the shell; end caps and nozzles add bending.
- ShapeBert: `calc_hand_check("thin_cylinder")`.
- Source: Roark's Formulas for Stress and Strain, 8th ed., Young, Budynas & Sadegh,
  McGraw-Hill 2012, Ch. 13 Shells of Revolution; Pressure Vessels; Pipes (thin-walled
  vessels).

### Topic 5. Lame thick cylinder
- Formula: s_theta = A + B / r^2, s_r = A - B / r^2, A = (pi a^2 - po b^2) / (b^2 - a^2),
  B = (pi - po) a^2 b^2 / (b^2 - a^2); closed-end axial stress = A.
- Physically: the hoop stress is highest at the bore and falls towards the outside.
- Assumptions: long cylinder, axisymmetric pressure, linear elastic.
- Validity: away from the ends; no yielding.
- 3D FEA: matches in the middle of a long cylinder.
- ShapeBert: `calc_hand_check("thick_cylinder")`.
- Source: Timoshenko & Goodier, Theory of Elasticity, 3rd ed., McGraw-Hill 1970,
  Section 28, section to be checked.

### Topic 6. Stress concentration at a hole
- Formula: Kt = 3 for a circular hole in an infinite plate under uniaxial tension:
  peak 3 s at the hole edge across the load, -s where the load axis meets the hole.
- Physically: the force lines crowd around the hole.
- Assumptions: infinite plate, uniaxial remote tension, linear elastic, plane stress.
- Validity: a finite width raises Kt as d/W grows; other notches have other factors.
- 3D FEA: reaches Kt near 3 only with several elements around the hole; a coarse
  mesh under-predicts the peak. This peak is real (not a singularity): it converges.
- ShapeBert: `calc_hand_check("kirsch_hole")`; take finite-width and other notch
  factors from Roark's charts.
- Source: Kirsch's 1898 solution as given in Timoshenko & Goodier, Theory of
  Elasticity, 3rd ed., McGraw-Hill 1970, Section 35, section to be checked; Roark's
  Formulas for Stress and Strain, 8th ed., Young, Budynas & Sadegh, McGraw-Hill 2012,
  Ch. 17 Stress Concentration (Kt charts).

### Topic 7. Euler buckling
- Formula: P = pi^2 E I / (K L)^2, I about the weaker axis; K = 2 (fixed-free),
  1 (pinned-pinned), 0.7 (fixed-pinned), 0.5 (fixed-fixed). Shear correction
  (Engesser): P / (1 + P / (k G A)).
- Physically: above P the straight column is no longer the stable shape.
- Assumptions: perfectly straight, load through the centroid, elastic, slender.
- Validity: short columns yield first (Johnson parabola region, below
  KL/r = sqrt(2 pi^2 E / yield)); imperfections lower real loads strongly.
- 3D FEA: a linear buckling run lands near the Engesser value, slightly below Euler
  (-0.31 % in the validation case). Neither is the column's real capacity.
- ShapeBert: `calc_hand_check("euler_column")`; validation case "Cantilever column".
- Source: Timoshenko & Gere, Theory of Elastic Stability, 2nd ed., McGraw-Hill 1961,
  Section 2.1 (Euler), Section 2.17 (Engesser shear correction); K for the other
  end conditions and the Johnson parabola: section to be checked.

### Topic 8. Beam natural frequencies
- Formula: f_n = (beta_n L)^2 / (2 pi L^2) sqrt(E I / (rho A)); beta_1 L = 1.8751
  (clamped-free), pi (pinned-pinned), 4.7300 (clamped-clamped and free-free).
- Physically: stiffness against mass; the beam vibrates in its mode shapes.
- Assumptions: Euler-Bernoulli beam, uniform section, ideal supports, no added mass.
- Validity: slender beams and low modes; shear and rotary inertia lower the higher
  modes more.
- 3D FEA: slightly lower (-0.28 % for the first mode in the validation case). Real
  supports are softer, so real frequencies are lower still.
- ShapeBert: `calc_hand_check("beam_frequency")`; validation case "Cantilever, natural
  frequencies".
- Source: Timoshenko, Young & Weaver, Vibration Problems in Engineering, 4th ed.,
  Wiley 1974, Section 5.3 (clamped-free); other supports: section to be checked.

### Topic 9. Heat conduction
- Formula: Fourier q = -k dT/dx; plane wall q = k A (T_hot - T_cold) / L, resistance
  R = L / (k A); convection q = h A (Ts - Tinf).
- Physically: heat flows from hot to cold in proportion to the gradient.
- Assumptions: steady state, constant k, 1D (other faces insulated).
- Validity: h is an input the user has to give; ShapeBert does not compute it, and its
  FEA has no convection or radiation.
- 3D FEA: exact for a bar with insulated sides (the temperature is linear).
- ShapeBert: `calc_hand_check("plane_wall")`; validation case "Bar, steady heat
  conduction".
- Source: Incropera et al., Fundamentals of Heat and Mass Transfer, 7th ed., Wiley
  2011, Ch. 3, sec. 3.1 The Plane Wall (R = L / (k A), Eq. 3.6).

### Topic 10. Thermal strain and stress
- Formula: e = alpha dT; free elongation d = alpha dT L; fully restrained (uniaxial)
  s = -E alpha dT.
- Physically: a heated part grows; only a restraint turns that growth into stress.
- Assumptions: uniform temperature change, constant alpha, linear elastic.
- Validity: a free (statically determinate) body expands stress-free; partly
  restrained parts lie between the two limits.
- 3D FEA: a free bar gives zero stress; fully fixed faces also block the sideways
  expansion and add local peaks there.
- ShapeBert: `calc_hand_check("thermal_expansion")`; validation case "Free bar,
  uniform heating".
- Source: Gere & Timoshenko, Mechanics of Materials (SI ed.), Ch. 2, sec. 2.5 Thermal
  Effects (free thermal expansion); Roark's Formulas for Stress and Strain, 8th ed.,
  Young, Budynas & Sadegh, McGraw-Hill 2012, Ch. 16 Dynamic and Temperature Stresses.

### Topic 11. Singularities and Saint-Venant's principle
- Formula: none finite. Elastic stress under a concentrated load is singular (Kelvin
  point force in full space; Boussinesq normal and Cerutti tangential point load on a
  half-space; Flamant in 2D). At a re-entrant corner the stress is singular for vertex
  angles between 180 and 360 degrees.
- Physically: real loads spread over a contact area and real corners have a radius,
  so real stresses stay finite; the model's idealisation does not.
- Assumptions: linear elasticity with ideal point loads, sharp corners and rigid supports.
- Validity: Saint-Venant's principle says that away from the load (about one width)
  the stress depends only on the resultant, so it is safe to read there.
- 3D FEA: the peak at a singular point keeps rising as the mesh is refined;
  displacements stay finite.
- ShapeBert: `fea_results` flags a load on a vertex or an edge, a loaded face less
  than 2 x mesh size across (its largest extent), and a peak within 2 mesh sizes of such a load, a fixed face
  or a sharp inside edge, and then also reports the peak outside those zones. To get
  a real value: read stress away from the spot, model the fillet radius, or use a
  linearised or averaged stress.
- Source: Timoshenko & Goodier, Theory of Elasticity, 3rd ed., McGraw-Hill 1970,
  sections to be checked;
  Sinclair, "Stress singularities in classical elasticity I", Appl. Mech. Rev. 57(4)
  2004; Williams, "Stress singularities resulting from various boundary conditions in
  angular corners of plates in extension", J. Appl. Mech. 19 (1952) 526-528.

### Topic 12. Mesh convergence
- Formula: Richardson extrapolation estimates the converged value from results on
  successively finer meshes.
- Physically: a finer mesh represents the true field better, so the results change
  less with each refinement.
- Assumptions: the exact solution is smooth where the result is read.
- Validity: stress converges more slowly than displacement; singular points never
  converge.
- 3D FEA: second-order tetrahedra converge much faster than first-order ones, which
  are too stiff in bending.
- ShapeBert: `fea_convergence` solves at 2.25, 1.5 and 1 times the mesh size and
  follows max displacement and the peak stress outside the flagged zones (or the
  frequency, load factor or heat flow); under 2 % change counts as converged.
- Source: Bathe, Finite Element Procedures, 2nd ed., 2014 (and his MIT OCW RES.2-002
  lectures), sections to be checked; "The Standard NAFEMS Benchmarks", TNSB Rev. 3,
  NAFEMS, October 1990.

## 4. Verification checks (must verify, report result)
- `equilibrium_ok` is true: the reactions balance the loads.
- Hand check: run `calc_hand_check` for the closest case and compare. Explain the
  difference with the topic above (sign and typical size). A difference over about
  20 % means: check the loads, the supports and the units before reporting anything.
- `fea_convergence`: every followed result converged.
- No stress is reported from a flagged zone (see topic 11).
- The safety factor against yield is reported with the note that this is a
  simplified linear check.

## 5. Vocabulary / forms (what to build with)
- Supports: fixed faces (held completely), sliding faces (symmetry planes, free in
  their own plane).
- Loads: force spread over a face, pressure; temperatures fixed on faces.
- Results: von Mises stress, displacement, reaction force, natural frequency, load
  factor, heat flow.
- Mesh: element size, second-order (10-node) tetrahedra, convergence, singularity.

## 6. Standards to respect (paraphrased - never reproduce standards text)
- "The Standard NAFEMS Benchmarks", TNSB Rev. 3, NAFEMS, October 1990: published
  reference problems for checking FE results.
- Design codes (pressure vessels, steel structures, machine parts) set the
  allowable stresses and safety factors; ShapeBert does not apply them.
Tell the user a formal/certified calculation is a separate step beyond the CAD.

## 7. Manufacturing limits and design rules
- Model the real fillet radius at an inside corner when its stress matters; a sharp
  corner gives a singular peak.
- Apply loads over the real contact area, not on a point, an edge or a tiny face.
- Machined and printed parts have edge radii and surface finish that the ideal
  model does not; printed parts are weaker across the layers.

## 8. CAD approach in FreeCAD
- Build the part with the Build tools, then `fea_setup` with face selectors,
  `fea_run`, `fea_results`, `fea_convergence`, and `calc_hand_check` next to it.
- Check the faces each selector found (centre, normal) before solving.

## 9. Build sequence the assistant should follow
1. Ask section-2 questions; stop only if an input you need is missing.
2. Run `calc_hand_check` for the closest textbook case.
3. Set up and solve the FEA; read `fea_results` with its assumptions block.
4. Run `fea_convergence`; refine until every followed result has converged.
5. Compare with the hand check and explain the difference (section 4).
6. Report every value used, the assumptions block, and what still needs a human or
   certified check.

## 10. Always be honest about limits
- Say which numbers were assumed (material table values, defaults) and which given.
- Say when a result is preliminary (not converged, no hand check, flagged zone).
- A linear buckling load is the ideal elastic limit, not the part's capacity.
