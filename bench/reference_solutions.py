"""Known-good answers for bench/cases.json; each must score 1.0 (see test_bench_oracle.py)."""

HEAD = "import Part, math\nd = App.ActiveDocument\n"
TAIL = "\no = d.addObject('Part::Feature', 'Result'); o.Shape = s\nd.recompute()\n"

REFERENCE = {
    "L1-box": "s = Part.makeBox(80, 50, 20)",
    "L1-tube": "s = Part.makeCylinder(20, 100).cut(Part.makeCylinder(15, 100))",
    "L1-plate-4xM6": (
        "s = Part.makeBox(100, 60, 8)\n"
        "for x in (12, 88):\n"
        "    for y in (12, 48):\n"
        "        s = s.cut(Part.makeCylinder(3.3, 8, App.Vector(x, y, 0)))"
    ),
    "L2-flange-6xM8": (
        "s = Part.makeCylinder(60, 12).cut(Part.makeCylinder(20, 12))\n"
        "for i in range(6):\n"
        "    a = i * math.pi / 3\n"
        "    s = s.cut(Part.makeCylinder(4.5, 12, App.Vector(45 * math.cos(a), 45 * math.sin(a), 0)))"
    ),
    "L2-counterbored-plate": (
        "s = Part.makeBox(60, 40, 10)\n"
        "for x in (15, 45):\n"
        "    s = s.cut(Part.makeCylinder(2.75, 10, App.Vector(x, 20, 0)))\n"
        "    s = s.cut(Part.makeCylinder(5.0, 5.4, App.Vector(x, 20, 10 - 5.4)))"
    ),
    "L2-L-bracket-sheet": (
        "t, R, w = 2.0, 2.0, 30.0\n"
        "leg1 = Part.makeBox(t, w, 50 - R - t, App.Vector(0, 0, R + t))\n"
        "leg2 = Part.makeBox(40 - R - t, w, t, App.Vector(R + t, 0, 0))\n"
        "ring = Part.makeCylinder(R + t, w, App.Vector(R + t, 0, R + t), App.Vector(0, 1, 0), 360)"
        ".cut(Part.makeCylinder(R, w, App.Vector(R + t, 0, R + t), App.Vector(0, 1, 0)))\n"
        "quad = ring.common(Part.makeBox(R + t, w, R + t))\n"
        "s = leg1.fuse(leg2).fuse(quad).removeSplitter()"
    ),
    "L2-stepped-shaft": (
        "s = Part.makeCylinder(10, 40).fuse(Part.makeCylinder(12.5, 60, App.Vector(0, 0, 40)))"
        ".fuse(Part.makeCylinder(10, 30, App.Vector(0, 0, 100))).removeSplitter()"
    ),
    "L3-shs-frame": (
        "# solid 40x40 ring, then remove the tube's 34x34 inner cavity ring\n"
        "ring = Part.makeBox(1000, 600, 40).cut(Part.makeBox(920, 520, 40, App.Vector(40, 40, 0)))\n"
        "cav = Part.makeBox(994, 594, 34, App.Vector(3, 3, 3)).cut("
        "Part.makeBox(926, 526, 34, App.Vector(37, 37, 3)))\n"
        "s = ring.cut(cav)"
    ),
    "L3-punt-hull": (
        "s = Part.makeBox(2000, 1000, 400).cut(Part.makeBox(1984, 984, 400, App.Vector(8, 8, 8)))"
    ),
    "L3-printable-hook": (
        "back = Part.makeBox(60, 40, 5)\n"
        "for x in (12, 48):\n"
        "    back = back.cut(Part.makeCylinder(2.25, 5, App.Vector(x, 20, 0)))\n"
        "arm = Part.makeBox(8, 45, 5, App.Vector(26, 35, 0))\n"
        "tip = Part.makeBox(8, 5, 12, App.Vector(26, 75, 0))\n"
        "s = back.fuse(arm).fuse(tip).removeSplitter()"
    ),
    "V2-flange-DN50-PN16": (
        "s = Part.makeCylinder(82.5, 18)\n"
        "for i in range(4):\n"
        "    a = math.pi / 4 + i * math.pi / 2\n"
        "    s = s.cut(Part.makeCylinder(9, 18, App.Vector(62.5 * math.cos(a), 62.5 * math.sin(a), 0)))"
    ),
    "V2-spur-pinion": (
        "z, m, b = 17, 2.0, 20.0\n"
        "ra, rf, pitch = m * (z + 2) / 2, m * (z - 2.5) / 2, 2 * math.pi / z\n"
        "pts = []\n"
        "for i in range(z):\n"
        "    t = i * pitch\n"
        "    for r, f in ((rf, -0.3), (ra, -0.12), (ra, 0.12), (rf, 0.3)):\n"
        "        pts.append(App.Vector(r * math.cos(t + f * pitch), r * math.sin(t + f * pitch), 0))\n"
        "outline = Part.Face(Part.makePolygon(pts + [pts[0]]))\n"
        "s = outline.extrude(App.Vector(0, 0, b)).cut(Part.makeCylinder(5, b))"
    ),
    "V2-flat-blank": "s = Part.makeBox(90 - (8 - math.pi / 2 * (2 + 0.44 * 2)), 30, 2)",
    "V2-punt-payload": "s = Part.makeBox(2400, 1100, 340).cut(Part.makeBox(2384, 1084, 340, App.Vector(8, 8, 8)))",
    "V2-keyed-shaft": (
        "slot = Part.makeBox(16, 8, 32, App.Vector(11, -4, 34))\n"
        "for zc in (34, 66):\n"
        "    slot = slot.fuse(Part.makeCylinder(4, 16, App.Vector(11, 0, zc), App.Vector(1, 0, 0)))\n"
        "s = Part.makeCylinder(15, 100).cut(slot)"
    ),
}


def code_for(case_id: str) -> str:
    return HEAD + REFERENCE[case_id] + TAIL
