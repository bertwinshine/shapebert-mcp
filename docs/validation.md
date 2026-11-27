# FEA validation

ShapeBert's FEA tools (`fea_setup`, `fea_run`, `fea_results`, `fea_convergence`)
solved against textbook answers and published benchmarks. Each case lives in
`tests/validation/<case>/`: `case.json` holds the setup, the formula or published
value, the source, the tolerance and why it is that wide; `fixture.json` holds the
accepted FEA result per environment. The analytical values are computed from the
formulas in `tests/validation/cases.py`, never typed in; only a benchmark's published
reference value (NAFEMS) is typed in, with its citation. Material: steel,
E 210000 MPa, nu 0.3, rho 7850 kg/m3, alpha 12e-6 1/K, k 50 W/(m K).

`pytest tests/validation` checks every value against its tolerance and, where a
result is frozen for the same FreeCAD, CalculiX, Gmsh and OS, that it has not moved
by more than 1e-6 relative (in the digits `fea_results` reports). Meshes differ
between platforms, so other environments only get the tolerance check. This file is
written by `python tests/validation/report.py` with a running FreeCAD listener.
Citations marked "edition/section to be checked" still need their edition or
section confirmed against the book; cases marked "description to be checked" were
modelled from an incomplete description and say what is missing. The background to
each formula, and how 3D FEA differs from it, is in `knowledge/domains/fea-mechanics.md`.

Last run: 2026-11-26, FreeCAD 1.1.3, CalculiX 2.22, Gmsh 4.15.0, Windows.

## Results

| Case | Quantity | Unit | Analytical | FEA | Error % | Tolerance % | Result | Frozen | Mesh | Element | Solver | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Cantilever column, buckling | Euler buckling load, mode 1 | N | 172718 | 172176 | 0.314 | 5 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Cantilever column, buckling | Euler buckling load, mode 2 (other direction) | N | 172718 | 172178 | 0.313 | 5 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Cantilever, natural frequencies | First bending frequency, mode 1 | Hz | 417.758 | 416.57 | 0.284 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Cantilever, natural frequencies | First bending frequency, mode 2 (other direction) | Hz | 417.758 | 416.58 | 0.282 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Cantilever, end load | Tip deflection (centre of the free end, -z) | mm | 0.952381 | 0.95248 | 0.010 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Cantilever, end load | Bending stress at mid-length, top face | MPa | 75.0607 | 75.094 | 0.044 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Bar in tension | Axial stress at mid-length | MPa | 100 | 99.999 | 0.001 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Bar in tension | Elongation (x movement of the loaded end) | mm | 0.047619 | 0.04762 | 0.002 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Bar, steady heat conduction | Temperature near x = 25 (error relative to the 80 K span) | °C | 80.2248 | 80.225 | 0.000 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Bar, steady heat conduction | Temperature near x = 50 (error relative to the 80 K span) | °C | 60.1208 | 60.12 | 0.001 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Bar, steady heat conduction | Temperature near x = 75 (error relative to the 80 K span) | °C | 40.3864 | 40.386 | 0.000 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Bar, steady heat conduction | Heat flow into the hot end | W | 8 | 8 | 0.000 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Free bar, uniform heating | Free thermal elongation | mm | 0.12 | 0.12 | 0.000 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Free bar, uniform heating | Peak von Mises stress (zero in theory; error relative to E alpha dT, the stress of a fully clamped bar) | MPa | 0 | 0 | 0.000 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |

## Published benchmarks

FEA against the published target, with `calc_hand_check` where a closed form applies. The error is against the target.

| Case | Quantity | Unit | Published | Target | Hand check | FEA | Error % | Tolerance % | Result | Frozen | Mesh | Element | Solver | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Plate with a hole in tension (Kirsch) | x stress at the hole edge across the load, (0, 5, 0) | MPa | Kt = 3 | 300 | 300 (`kirsch_hole`) | 302.051 | 0.684 | 2 | pass | same | 1.0 mm, 166393 nodes, 83952 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Plate with a hole in tension (Kirsch) | Peak von Mises stress away from singularities (the hole edge is not one) | MPa | Kt = 3 | 300 | 300 (`kirsch_hole`) | 303.81 | 1.270 | 2 | pass | same | 1.0 mm, 166393 nodes, 83952 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Thick cylinder under internal pressure (Lame) | Radial displacement at the bore | mm | Lame solution | 0.0468254 | none applies | 0.04682 | 0.012 | 1 | pass | same | 5.0 mm, 8427 nodes, 4872 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Thick cylinder under internal pressure (Lame) | Radial displacement at the outside | mm | Lame solution | 0.031746 | none applies | 0.03175 | 0.013 | 1 | pass | same | 5.0 mm, 8427 nodes, 4872 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| Thick cylinder under internal pressure (Lame) | Hoop stress at the bore | MPa | Lame solution | 166.667 | 166.667 (`thick_cylinder`) | 166.597 | 0.042 | 2 | pass | same | 5.0 mm, 8427 nodes, 4872 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| NAFEMS LE1, elliptic membrane | Tangential stress sigma_yy at D, coarse mesh | MPa | 92.7 MPa | 92.7 | none applies | 89.713 | 3.222 | 5 | pass | same | 500.0 mm, 859 nodes, 386 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| NAFEMS LE1, elliptic membrane | Tangential stress sigma_yy at D, fine mesh | MPa | 92.7 MPa | 92.7 | none applies | 92.589 | 0.120 | 2 | pass | same | 100.0 mm, 9854 nodes, 4811 el. | C3D10 | CalculiX 2.22 | 2026-11-26 |
| NAFEMS LE10, thick plate under pressure | sigma_yy at D (2, 0, 0.3), top face | MPa | -5.38 MPa | -5.38 | none applies | not modelled |  | 2 | **not run** |  |  |  |  | 2026-11-26 |

## Mesh convergence

### Cantilever, end load

`fea_convergence` follows `max_displacement_mm`, `max_von_mises_away_mpa`; the stress leaves out everything within 18.0 mm of a fixed face, sharp inside edge or concentrated load. A result has converged when its last change is under 2.0 %.

| Mesh | Nodes | Elements | max_displacement_mm | Change | max_von_mises_away_mpa | Change |
|---|---|---|---|---|---|---|
| 9.0 mm | 1823 | 854 | 0.954057 |  | 136.191 |  |
| 6.0 mm | 4419 | 2330 | 0.95481 | 0.079 % | 135.495 | 0.511 % |
| 4.0 mm | 11233 | 6454 | 0.955234 | 0.044 % | 136.71 | 0.896 % |

Converged: max_displacement_mm, max_von_mises_away_mpa. Not converged: none.

### Plate with a hole in tension (Kirsch)

`fea_convergence` follows `max_displacement_mm`, `max_von_mises_away_mpa`; the stress leaves out everything within 4.5 mm of a fixed face, sharp inside edge or concentrated load. A result has converged when its last change is under 2.0 %.

| Mesh | Nodes | Elements | max_displacement_mm | Change | max_von_mises_away_mpa | Change |
|---|---|---|---|---|---|---|
| 2.25 mm | 34618 | 17153 | 0.0495194 |  | 296.679 |  |
| 1.5 mm | 75253 | 37462 | 0.0495192 | 0.001 % | 301.343 | 1.572 % |
| 1.0 mm | 166393 | 83952 | 0.0495191 | 0.000 % | 303.814 | 0.820 % |

Converged: max_displacement_mm, max_von_mises_away_mpa. Not converged: none.

## Known failures

None in the last run.

Not run, because the tools cannot set them up yet:

- NAFEMS LE10, thick plate under pressure: fea_setup cannot express these supports: fixed_faces hold a face in x, y and z, and sliding_faces take only flat faces facing along an axis. LE10 needs the curved outer face held in x and y only, and an edge held in z (the outer face's mid-plane line, which exists only if that face is split at z = 0).

## Cases, sources and tolerances

### Cantilever column, buckling (`cantilever_buckling`)

Steel bar 200 x 20 x 20 mm, end x = 0 fixed, 1000 N axial compression (-x) on the free end. Critical load = load factor x 1000 N.

- Euler buckling load, mode 1: `pi^2 E I / (4 L^2) (fixed-free column, effective length 2 L)`. Source: Timoshenko & Gere, Theory of Elastic Stability, 2nd ed., McGraw-Hill 1961, Section 2.1 (Euler), Section 2.17 (Engesser shear correction P = Pe / (1 + Pe/(kGA))). Tolerance 5 %: The shear correction lowers P slightly (seen: -0.31 %); 5 % covers it and the mesh.
- Euler buckling load, mode 2 (other direction): `as mode 1 (square section)`. Source: Timoshenko & Gere, Theory of Elastic Stability, 2nd ed., McGraw-Hill 1961, Section 2.1 (Euler), Section 2.17 (Engesser shear correction P = Pe / (1 + Pe/(kGA))). Tolerance 5 %: The shear correction lowers P slightly (seen: -0.31 %); 5 % covers it and the mesh.

### Cantilever, natural frequencies (`cantilever_modal`)

Steel bar 200 x 20 x 20 mm, end x = 0 fixed. The square section bends the same way in y and z, so the first two modes share one frequency.

- First bending frequency, mode 1: `(lambda1^2 / (2 pi)) sqrt(E I / (rho A L^4)), lambda1 = first root of cos(x) cosh(x) = -1 (1.8751)`. Source: Timoshenko, Young & Weaver, Vibration Problems in Engineering, 4th ed., Wiley 1974, Section 5.3 (beta1 L = 1.8751). Tolerance 3 %: Euler-Bernoulli theory ignores shear and rotary inertia, so 3D FEA comes out slightly lower (seen: -0.28 %).
- First bending frequency, mode 2 (other direction): `as mode 1 (square section: I is the same about y and z)`. Source: Timoshenko, Young & Weaver, Vibration Problems in Engineering, 4th ed., Wiley 1974, Section 5.3 (beta1 L = 1.8751). Tolerance 3 %: Euler-Bernoulli theory ignores shear and rotary inertia, so 3D FEA comes out slightly lower (seen: -0.28 %).

### Cantilever, end load (`cantilever_static`)

Steel bar 200 x 20 x 20 mm, end x = 0 fixed, 1000 N down (-z) spread over the free end x = 200.

- Tip deflection (centre of the free end, -z): `F L^3 / (3 E I), I = b h^3 / 12`. Source: Timoshenko & Gere, Mechanics of Materials (beam deflection; with shear: d = PL^3/3EI + PL/(kGA), k = 5/6 for a rectangle), edition/section to be checked; Cowper, J. Appl. Mech. 33 (1966) 335-340 (shear coefficient). Tolerance 3 %: Beam theory and 3D elasticity differ by a few tenths of a percent at L/h = 10; the rest of the band covers the mesh error.
- Bending stress at mid-length, top face: `M c / I with M = F (L - x) and c = h/2, at the x of the probe's node`. Source: Timoshenko & Gere, Mechanics of Materials (beam deflection; with shear: d = PL^3/3EI + PL/(kGA), k = 5/6 for a rectangle), edition/section to be checked; Cowper, J. Appl. Mech. 33 (1966) 335-340 (shear coefficient). Tolerance 3 %: Beam theory and 3D elasticity differ by a few tenths of a percent at L/h = 10; the rest of the band covers the mesh error.

### Plate with a hole in tension (Kirsch) (`kirsch_plate`)

Steel plate 200 x 200 x 2 mm with a 10 mm hole in the middle (width 20 x the hole diameter), pulled with 100 MPa on the gross section. Quarter model 100 x 100 x 1 mm minus the hole: x = 0 and y = 0 are symmetry planes and z = 0 is the mid-plane, all three sliding supports. The pull (-100 MPa pressure) is on the end x = 100. Plate length, thickness and load are not part of Kirsch's solution: Kt does not depend on them in a thin plate, so they were chosen here.

- x stress at the hole edge across the load, (0, 5, 0): `s (1 - 2 cos 2 theta) at theta = 90 deg, s = remote stress`. Published: Kt = 3. Source: Kirsch 1898; Timoshenko & Goodier, Theory of Elasticity, Section 35, edition to be checked. Hand check: `calc_hand_check` `kirsch_hole`. Tolerance 2 %: The finite width (d/W = 1/20) raises Kt by a few tenths of a percent, and CalculiX extrapolates the stress from the integration points to the hole surface (up to about 1 %); the band covers both plus the mesh.
- Peak von Mises stress away from singularities (the hole edge is not one): `s (1 - 2 cos 2 theta) at theta = 90 deg; the stress there is uniaxial, so von Mises = s_theta`. Published: Kt = 3. Source: Kirsch 1898; Timoshenko & Goodier, Theory of Elasticity, Section 35, edition to be checked. Hand check: `calc_hand_check` `kirsch_hole`. Tolerance 2 %: The finite width (d/W = 1/20) raises Kt by a few tenths of a percent, and CalculiX extrapolates the stress from the integration points to the hole surface (up to about 1 %); the band covers both plus the mesh.

### Thick cylinder under internal pressure (Lame) (`lame_cylinder`)

Steel tube, inner radius a = 50 mm, outer radius b = 2a = 100 mm, 20 mm long, 100 MPa inside. Quarter model: x = 0 and y = 0 are symmetry planes and the end z = 0 slides; the other end is free (open ends, no axial stress). Probes on the y = 0 plane, where the x displacement is the radial one and the y stress is the hoop stress.

Description to be checked: The description gives b = 2a but not a, the pressure or the end condition. a and the pressure only scale the answers. The end condition changes the radial displacement (open ends, plane strain or closed ends) but not the hoop stress; open ends were modelled because the Lame solution is then exact in 3D.

- Radial displacement at the bore: `u(a) = ((1 - nu) A a + (1 + nu) B / a) / E, A = p a^2 / (b^2 - a^2), B = p a^2 b^2 / (b^2 - a^2)`. Published: Lame solution. Source: Timoshenko & Goodier, Theory of Elasticity, Section 28, edition to be checked. Tolerance 1 %: With open ends the Lame solution is exact in 3D (axial stress zero, axial strain uniform), and displacements converge fastest, so only the mesh error remains.
- Radial displacement at the outside: `u(b) = ((1 - nu) A b + (1 + nu) B / b) / E`. Published: Lame solution. Source: Timoshenko & Goodier, Theory of Elasticity, Section 28, edition to be checked. Tolerance 1 %: With open ends the Lame solution is exact in 3D (axial stress zero, axial strain uniform), and displacements converge fastest, so only the mesh error remains.
- Hoop stress at the bore: `A + B / a^2`. Published: Lame solution. Source: Timoshenko & Goodier, Theory of Elasticity, Section 28, edition to be checked. Hand check: `calc_hand_check` `thick_cylinder`. Tolerance 2 %: Exact solution in 3D; the band covers the mesh and CalculiX's extrapolation of stress from the integration points to the bore, where the stress gradient is steepest.

### NAFEMS LE1, elliptic membrane (`nafems_le1`)

Quarter of an elliptic membrane: inner ellipse (x/2)^2 + (y/1)^2 = 1, outer ellipse (x/3.25)^2 + (y/2.75)^2 = 1 (metres, modelled in mm), 0.1 m thick, steel (E 210 GPa, nu 0.3), 10 MPa outward pressure (a pull) on the outer edge, symmetry on the x and y axes. Plane stress, modelled as a thin 3D plate free in z: the plate is symmetric about its mid-plane, so the half 50 mm thick is modelled and slides on z = 0, which holds it in z and nothing else. No selector picks the elliptic outer face, so the harness takes the largest curved face from list_faces. D = (2, 0) is on the inner edge, where the tangential stress is sigma_yy. NAFEMS's coarse and fine meshes are quadrilaterals; these are Gmsh tetrahedra of 500 and 100 mm. The outer face is 50 mm thick but metres long, so fea_results does not flag its load as concentrated, even on the 500 mm mesh.

- Tangential stress sigma_yy at D, coarse mesh: `published reference value`. Published: 92.7 MPa. Source: NAFEMS, The Standard NAFEMS Benchmarks, TNSB Rev. 3, 1990, test LE1. Mesh 500 mm. Tolerance 5 %: NAFEMS gives 92.7 MPa to three figures. D is where the inner edge curves most (radius 0.5 m), so a coarse mesh misses part of the peak.
- Tangential stress sigma_yy at D, fine mesh: `published reference value`. Published: 92.7 MPa. Source: NAFEMS, The Standard NAFEMS Benchmarks, TNSB Rev. 3, 1990, test LE1. Tolerance 2 %: NAFEMS gives 92.7 MPa to three figures. The fine mesh follows the curvature at D; what is left is the extrapolation of stress to the free edge.

### NAFEMS LE10, thick plate under pressure (`nafems_le10`)

Quarter of a thick elliptic plate: inner ellipse (x/2)^2 + (y/1)^2 = 1, outer ellipse (x/3.25)^2 + (y/2.75)^2 = 1 (metres), 0.6 m thick (z from -0.3 to 0.3), steel (E 210 GPa, nu 0.3), 1 MPa pressure on the top face. Outer curved face held in x and y; the mid-plane edge on the outer face held in z; symmetry on the x and y planes. Target: sigma_yy at D (2, 0, 0.3).

Description to be checked: Boundary conditions to be checked against TNSB Rev. 3.

Not modelled: fea_setup cannot express these supports: fixed_faces hold a face in x, y and z, and sliding_faces take only flat faces facing along an axis. LE10 needs the curved outer face held in x and y only, and an edge held in z (the outer face's mid-plane line, which exists only if that face is split at z = 0).

- sigma_yy at D (2, 0, 0.3), top face: `published reference value`. Published: -5.38 MPa. Source: NAFEMS, The Standard NAFEMS Benchmarks, TNSB Rev. 3, 1990, test LE10. Tolerance 2 %: Not run; set as for the LE1 fine mesh.

### Bar in tension (`tension_bar`)

Steel bar 100 x 20 x 10 mm, 20 kN along +x on the end x = 100. The faces x = 0, y = 0 and z = 0 are sliding supports (symmetry planes): they stop rigid-body motion but leave the lateral (Poisson) contraction free, so the stress is uniform right up to the support.

- Axial stress at mid-length: `F / A`. Source: Timoshenko & Gere, Mechanics of Materials (axially loaded members, d = FL/EA), edition/section to be checked. Tolerance 2 %: Uniform stress state, near-exact for any mesh; the band only catches setup errors.
- Elongation (x movement of the loaded end): `F L / (E A)`. Source: Timoshenko & Gere, Mechanics of Materials (axially loaded members, d = FL/EA), edition/section to be checked. Tolerance 2 %: Uniform stress state, near-exact for any mesh; the band only catches setup errors.

### Bar, steady heat conduction (`thermal_bar`)

Steel bar 100 x 20 x 10 mm, end x = 0 at 100 °C, end x = 100 at 20 °C, all other faces insulated.

- Temperature near x = 25 (error relative to the 80 K span): `T(x) = T_hot - (T_hot - T_cold) x / L, at the x of the probe's node`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer (1D plane wall, Fourier's law), edition/section to be checked. Tolerance 1 %: A linear temperature field is exact for tetrahedra; the band covers solver precision.
- Temperature near x = 50 (error relative to the 80 K span): `T(x) = T_hot - (T_hot - T_cold) x / L, at the x of the probe's node`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer (1D plane wall, Fourier's law), edition/section to be checked. Tolerance 1 %: A linear temperature field is exact for tetrahedra; the band covers solver precision.
- Temperature near x = 75 (error relative to the 80 K span): `T(x) = T_hot - (T_hot - T_cold) x / L, at the x of the probe's node`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer (1D plane wall, Fourier's law), edition/section to be checked. Tolerance 1 %: A linear temperature field is exact for tetrahedra; the band covers solver precision.
- Heat flow into the hot end: `k A (T_hot - T_cold) / L`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer (1D plane wall, Fourier's law), edition/section to be checked. Tolerance 1 %: A linear temperature field is exact for tetrahedra; the band covers solver precision.

### Free bar, uniform heating (`thermomech_free_bar`)

Steel bar 100 x 20 x 10 mm, every face at 120 °C, stress-free at 20 °C (dT = 100 K). The faces x = 0, y = 0 and z = 0 are sliding supports: statically determinate, so the bar expands freely.

- Free thermal elongation: `alpha dT L`. Source: Timoshenko & Goodier, Theory of Elasticity (thermal stress chapter), or Gere & Goodno, Mechanics of Materials (thermal effects), edition/section to be checked. Tolerance 2 %: Statically determinate supports leave the expansion free: exact elongation, zero stress.
- Peak von Mises stress (zero in theory; error relative to E alpha dT, the stress of a fully clamped bar): `0 for a free bar`. Source: Timoshenko & Goodier, Theory of Elasticity (thermal stress chapter), or Gere & Goodno, Mechanics of Materials (thermal effects), edition/section to be checked. Tolerance 2 %: Statically determinate supports leave the expansion free: exact elongation, zero stress.
