# FEA validation

ShapeBert's FEA tools (`fea_setup`, `fea_run`, `fea_results`, `fea_convergence`)
solved against textbook answers. Each case lives in `tests/validation/<case>/`:
`case.json` holds the setup, the formula, the source, the tolerance and why it is
that wide; `fixture.json` holds the accepted FEA result per environment. The
analytical values are computed from the formulas in `tests/validation/cases.py`,
never typed in. Material: steel, E 210000 MPa, nu 0.3, rho 7850 kg/m3,
alpha 12e-6 1/K, k 50 W/(m K).

`pytest tests/validation` checks every value against its tolerance and, where a
result is frozen for the same FreeCAD, CalculiX, Gmsh and OS, that it has not moved
by more than 1e-6 relative (in the digits `fea_results` reports). Meshes differ
between platforms, so other environments only get the tolerance check. This file is
written by `python tests/validation/report.py` with a running FreeCAD listener.
Citations marked "edition/section to be checked" still need their edition or
section confirmed against the book. The background to each formula, and how 3D FEA
differs from it, is in `knowledge/domains/fea-mechanics.md`.

Last run: 2026-11-25, FreeCAD 1.1.3, CalculiX 2.22, Gmsh 4.15.0, Windows.

## Results

| Case | Quantity | Unit | Analytical | FEA | Error % | Tolerance % | Result | Frozen | Mesh | Element | Solver | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Cantilever column, buckling | Euler buckling load, mode 1 | N | 172718 | 172176 | 0.314 | 5 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Cantilever column, buckling | Euler buckling load, mode 2 (other direction) | N | 172718 | 172178 | 0.313 | 5 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Cantilever, natural frequencies | First bending frequency, mode 1 | Hz | 417.758 | 416.57 | 0.284 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Cantilever, natural frequencies | First bending frequency, mode 2 (other direction) | Hz | 417.758 | 416.58 | 0.282 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Cantilever, end load | Tip deflection (centre of the free end, -z) | mm | 0.952381 | 0.95248 | 0.010 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Cantilever, end load | Bending stress at mid-length, top face | MPa | 75.0607 | 75.094 | 0.044 | 3 | pass | same | 4.0 mm, 11233 nodes, 6454 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Bar in tension | Axial stress at mid-length | MPa | 100 | 99.999 | 0.001 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Bar in tension | Elongation (x movement of the loaded end) | mm | 0.047619 | 0.04762 | 0.002 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Bar, steady heat conduction | Temperature near x = 25 (error relative to the 80 K span) | °C | 80.2248 | 80.225 | 0.000 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Bar, steady heat conduction | Temperature near x = 50 (error relative to the 80 K span) | °C | 60.1208 | 60.12 | 0.001 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Bar, steady heat conduction | Temperature near x = 75 (error relative to the 80 K span) | °C | 40.3864 | 40.386 | 0.000 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Bar, steady heat conduction | Heat flow into the hot end | W | 8 | 8 | 0.000 | 1 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Free bar, uniform heating | Free thermal elongation | mm | 0.12 | 0.12 | 0.000 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |
| Free bar, uniform heating | Peak von Mises stress (zero in theory; error relative to E alpha dT, the stress of a fully clamped bar) | MPa | 0 | 0 | 0.000 | 2 | pass | same | 3.0 mm, 7734 nodes, 4325 el. | C3D10 | CalculiX 2.22 | 2026-11-25 |

## Mesh convergence (cantilever)

`fea_convergence` on the cantilever follows `max_displacement_mm`, `max_von_mises_away_mpa`; the stress leaves out everything within 18.0 mm of the fixed end. A result has converged when its last change is under 2.0 %.

| Mesh | Nodes | Elements | max_displacement_mm | Change | max_von_mises_away_mpa | Change |
|---|---|---|---|---|---|---|
| 9.0 mm | 1823 | 854 | 0.954057 |  | 136.191 |  |
| 6.0 mm | 4419 | 2330 | 0.95481 | 0.079 % | 135.495 | 0.511 % |
| 4.0 mm | 11233 | 6454 | 0.955234 | 0.044 % | 136.71 | 0.896 % |

Converged: max_displacement_mm, max_von_mises_away_mpa. Not converged: none.

## Known failures

None in the last run.

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
