# Domain: <name>   (TEMPLATE - copy me, don't edit me)

One-line scope: what kind of parts this domain covers, and any size/type limits.
Do the calculations in section 3 and the checks in section 4 BEFORE assigning
dimensions. Ask the section-2 questions first.

---

## 1. Reality check to tell the user
- What this domain can realistically deliver vs what still needs a human / a
  specialist tool / a certified calculation. Be honest here.

## 2. Ask the user first (critical inputs - do NOT assume these)
Ask only for the inputs you need to choose a dimension. If the user already gave the
dimensions, build them and say at the end which checks were skipped.
1. <the inputs that MUST be known before any geometry - sizes, loads, material,
   intended use, standard/spec to follow>
If the user says "just pick sensible values", use the ranges below and REPORT
every value chosen.

## 3. Core calculations (run before assigning values)
- <formula 1 = ... with symbols defined and units>
- <formula 2 = ...>
Typical target ranges:
- <parameter: range, and when to use each end>

## 4. Verification checks (must verify, report result)
- <the check(s) that prove the part is valid - strength, fit, stability,
  clearance, volume vs target, etc.>

## 5. Vocabulary / forms (what to build with)
- <the standard shapes, features and terms in this field>

## 6. Standards to respect (paraphrased - never reproduce standards text)
- <standard number - what it governs>
Tell the user a formal/certified calculation is a separate step beyond the CAD.

## 7. Manufacturing limits and design rules
- <process facts: min wall, min radius, draft, tolerances, anisotropy, etc.>
- <design rules to bake into the geometry so the part is actually makeable>

## 8. CAD approach in FreeCAD
- <which operations/workbench to use; prefer a purpose-built workbench if one
  exists; always recompute, verify the solid, measure against the target>

## 9. Build sequence the assistant should follow
1. Ask section-2 questions; stop only if an input you need to choose a dimension is missing.
2. Choose targets (section 3).
3. Build geometry.
4. Verify (section 4); compare to target; iterate.
5. Apply manufacturing rules (section 7).
6. Report every value used and what still needs a human / certified check.

## 10. Always be honest about limits
- Say which numbers were assumed vs given.
- Say what is a concept vs what is verified.
