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
The citations name the edition and the table or section; they have not yet been
checked against the printed books.

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

`fea_convergence` on the cantilever, key result `max_displacement_mm`; converged when the last change is under 2.0 %.

| Mesh | Nodes | Elements | Value | Change |
|---|---|---|---|---|
| 9.0 mm | 1823 | 854 | 0.954057 |  |
| 6.0 mm | 4419 | 2330 | 0.95481 | 0.079 % |
| 4.0 mm | 11233 | 6454 | 0.955234 | 0.044 % |

Converged: yes.

## Known failures

None in the last run.

## Cases, sources and tolerances

### Cantilever column, buckling (`cantilever_buckling`)

Steel bar 200 x 20 x 20 mm, end x = 0 fixed, 1000 N axial compression (-x) on the free end. Critical load = load factor x 1000 N.

- Euler buckling load, mode 1: `pi^2 E I / (4 L^2) (fixed-free column, effective length 2 L)`. Source: S. P. Timoshenko, J. M. Gere, Theory of Elastic Stability, 2nd ed., McGraw-Hill 1961, Section 2.1 (column fixed at the base, free at the top). Tolerance 5 %: Euler theory leaves out shear deformation (small at slenderness 69), and the end load is a uniform traction, not a point force at the centroid.
- Euler buckling load, mode 2 (other direction): `as mode 1 (square section)`. Source: S. P. Timoshenko, J. M. Gere, Theory of Elastic Stability, 2nd ed., McGraw-Hill 1961, Section 2.1. Tolerance 5 %: As mode 1.

### Cantilever, natural frequencies (`cantilever_modal`)

Steel bar 200 x 20 x 20 mm, end x = 0 fixed. The square section bends the same way in y and z, so the first two modes share one frequency.

- First bending frequency, mode 1: `(lambda1^2 / (2 pi)) sqrt(E I / (rho A L^4)), lambda1 = first root of cos(x) cosh(x) = -1 (1.8751)`. Source: R. D. Blevins, Formulas for Natural Frequency and Mode Shape, Van Nostrand Reinhold 1979, Table 8-1 (single-span beams, clamped-free). Tolerance 3 %: Euler-Bernoulli theory leaves out shear deformation and rotary inertia, which lower the real frequency by about 1 % at L/h = 10.
- First bending frequency, mode 2 (other direction): `as mode 1 (square section: I is the same about y and z)`. Source: R. D. Blevins, Formulas for Natural Frequency and Mode Shape, Van Nostrand Reinhold 1979, Table 8-1 (single-span beams, clamped-free). Tolerance 3 %: As mode 1.

### Cantilever, end load (`cantilever_static`)

Steel bar 200 x 20 x 20 mm, end x = 0 fixed, 1000 N down (-z) spread over the free end x = 200.

- Tip deflection (centre of the free end, -z): `F L^3 / (3 E I), I = b h^3 / 12`. Source: W. C. Young, R. G. Budynas, A. M. Sadegh, Roark's Formulas for Stress and Strain, 8th ed., McGraw-Hill 2012, Table 8.1 case 1a (cantilever, end load). Tolerance 3 %: Euler-Bernoulli theory leaves out shear deformation, which adds F L / (k G A), about 0.8 % at L/h = 10; the rest covers the discretisation error of a 4 mm mesh.
- Bending stress at mid-length, top face: `M c / I with M = F (L - x) and c = h/2, at the x of the probe's node`. Source: J. M. Gere, B. J. Goodno, Mechanics of Materials, 8th ed., Cengage 2013, Chapter 5, normal stresses in beams (flexure formula). Tolerance 3 %: Nodal stresses are extrapolated from the integration points, about 1 % off at this mesh; on the free top face the other stresses are zero, so von Mises equals the bending stress.

### Bar in tension (`tension_bar`)

Steel bar 100 x 20 x 10 mm, 20 kN along +x on the end x = 100. The faces x = 0, y = 0 and z = 0 are sliding supports (symmetry planes): they stop rigid-body motion but leave the lateral (Poisson) contraction free, so the stress is uniform right up to the support.

- Axial stress at mid-length: `F / A`. Source: J. M. Gere, B. J. Goodno, Mechanics of Materials, 8th ed., Cengage 2013, Chapter 1, normal stress and strain. Tolerance 2 %: With sliding supports the uniform stress state is exact for any mesh, so a larger error means a wrong area, load or support.
- Elongation (x movement of the loaded end): `F L / (E A)`. Source: J. M. Gere, B. J. Goodno, Mechanics of Materials, 8th ed., Cengage 2013, Section 2.2, changes in lengths of axially loaded members. Tolerance 2 %: A linear displacement field is exact for quadratic elements; the band catches setup errors.

### Bar, steady heat conduction (`thermal_bar`)

Steel bar 100 x 20 x 10 mm, end x = 0 at 100 °C, end x = 100 at 20 °C, all other faces insulated.

- Temperature near x = 25 (error relative to the 80 K span): `T(x) = T_hot - (T_hot - T_cold) x / L, at the x of the probe's node`. Source: F. P. Incropera, D. P. DeWitt, T. L. Bergman, A. S. Lavine, Fundamentals of Heat and Mass Transfer, 7th ed., Wiley 2011, Section 3.1 (the plane wall). Tolerance 1 %: A linear temperature field lies in the element space, so the FEA should match to solver precision.
- Temperature near x = 50 (error relative to the 80 K span): `T(x) = T_hot - (T_hot - T_cold) x / L, at the x of the probe's node`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer, 7th ed., Section 3.1 (the plane wall). Tolerance 1 %: As for x = 25.
- Temperature near x = 75 (error relative to the 80 K span): `T(x) = T_hot - (T_hot - T_cold) x / L, at the x of the probe's node`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer, 7th ed., Section 3.1 (the plane wall). Tolerance 1 %: As for x = 25.
- Heat flow into the hot end: `k A (T_hot - T_cold) / L`. Source: Incropera et al., Fundamentals of Heat and Mass Transfer, 7th ed., Section 3.1 (the plane wall, Fourier's law). Tolerance 1 %: The heat flow of an exact linear field; 1 % leaves room for the nodal summation only.

### Free bar, uniform heating (`thermomech_free_bar`)

Steel bar 100 x 20 x 10 mm, every face at 120 °C, stress-free at 20 °C (dT = 100 K). The faces x = 0, y = 0 and z = 0 are sliding supports: statically determinate, so the bar expands freely.

- Free thermal elongation: `alpha dT L`. Source: J. M. Gere, B. J. Goodno, Mechanics of Materials, 8th ed., Cengage 2013, Section 2.5, thermal effects. Tolerance 2 %: Free uniform expansion is a linear displacement field, exact for any mesh; the band catches a support that restrains the bar.
- Peak von Mises stress (zero in theory; error relative to E alpha dT, the stress of a fully clamped bar): `0 for a free bar`. Source: J. M. Gere, B. J. Goodno, Mechanics of Materials, 8th ed., Cengage 2013, Section 2.5, thermal effects (a statically determinate structure carries no thermal stress). Tolerance 2 %: Any stress means the supports restrain the expansion; 2 % of the clamped-bar stress (about 5 MPa) is the band.
