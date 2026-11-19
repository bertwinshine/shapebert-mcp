"""Calculators checked against hand calculations and textbook values."""

import math

import pytest

from cadkit.calculators import boat, fasteners, gears, shafts, sheet_metal, weldments


def approx(x, rel=1e-3):
    return pytest.approx(x, rel=rel)


def test_torque_from_power():
    assert gears.torque_from_power(1.5, 1450) == approx(9.879, 1e-3)


def test_spur_geometry_matches_iso53_formulas():
    r = gears.spur_pair(m=2, z1=20, z2=60)
    p, w = r["geometry"]["pinion"], r["geometry"]["wheel"]
    assert p["d_mm"] == 40 and p["d_tip_mm"] == 44 and p["d_root_mm"] == 35
    assert w["d_mm"] == 120
    assert r["centre_distance_mm"] == 80
    assert r["ratio"] == 3
    assert p["d_base_mm"] == approx(40 * math.cos(math.radians(20)))


def test_contact_ratio_textbook_value():
    # 20 deg, z 20/60 standard gears: eps_alpha ~1.67 (classic table value)
    assert gears.contact_ratio(2, 20, 60) == approx(1.67, 0.02)


def test_undercut_check_fails_for_10_teeth():
    r = gears.spur_pair(m=1, z1=10, z2=30)
    chk = {c["check"]: c["pass"] for c in r["checks"]}
    assert chk["pinion undercut"] is False


def test_lewis_stress_hand_calc():
    # T = 10 N.m, m=2, z1=20 -> d=40, Ft=500 N; b=20; Y(20)=0.322; no rpm -> Kv=1
    r = gears.spur_pair(m=2, z1=20, z2=60, torque_nm=10, sigma_allow_mpa=200)
    assert r["load"]["Ft_N"] == 500
    assert r["load"]["lewis_pinion"]["sigma_F_MPa"] == approx(500 / (20 * 2 * 0.322), 1e-2)


def test_planetary_conditions():
    good = gears.planetary(z_sun=24, z_planet=24, n_planets=3)  # ring 72, i = 4
    assert good["ratio_sun_to_carrier"] == 4
    assert all(c["pass"] for c in good["checks"])
    bad = gears.planetary(z_sun=20, z_planet=21, n_planets=3)  # ring 62, (20+62)/3 not int
    assert not {c["check"]: c["pass"] for c in bad["checks"]}["equal-spacing assembly (z_S+z_R)/N integer"]


def test_solve_planetary_returns_only_valid_sets():
    hits = gears.solve_planetary(5.0, n_planets=3)
    assert hits and all(abs(h["error_pct"]) <= 2 for h in hits)
    for h in hits:
        assert all(c["pass"] for c in gears.planetary(h["z_sun"], h["z_planet"], h["z_ring"], 3)["checks"])


def test_nearest_module():
    assert gears.nearest_module(2.2) == 2.5
    assert gears.nearest_module(2.2, series_ii=True) == 2.25


def test_bend_allowance_hand_calc():
    r = sheet_metal.bend(t_mm=2, r_mm=2, angle_deg=90, k=0.44)
    assert r["bend_allowance_mm"] == approx(math.pi / 2 * (2 + 0.44 * 2))
    assert r["outside_setback_mm"] == approx(4.0)
    assert r["bend_deduction_mm"] == approx(8 - math.pi / 2 * 2.88)


def test_flat_length_u_channel():
    # U channel 50/30/50 outside, t=2, R=2, K=0.44: flat = 130 - 2*BD
    bd = 8 - math.pi / 2 * 2.88
    r = sheet_metal.flat_length([50, 30, 50], 2, 2, k=0.44)
    assert r["flat_length_mm"] == approx(130 - 2 * bd)


def test_k_from_test_bend_inverts_bend():
    ba = sheet_metal.bend(3, 3, 90, k=0.4)["bend_allowance_mm"]
    assert sheet_metal.k_from_test_bend(ba, 90, 3, 3) == approx(0.4)


def test_press_brake_force():
    r = sheet_metal.press_brake(t_mm=2, length_m=1, rm_mpa=400)  # V = 16
    assert r["force_kN"] == approx(1.42 * 400 * 4 * 1 / 16, 1e-2)


def test_size_for_payload_floats_exactly():
    r = boat.size_for_payload(payload_kg=200, light_mass_kg=60, cb=0.45)
    L_, B, T = r["waterline_length_m"], r["waterline_beam_m"], r["draft_m"]
    assert approx(260, 5e-3) == L_ * B * T * 0.45 * 1000
    assert approx(2.4, 1e-2) == L_ / B and approx(4.0, 1e-2) == B / T


def test_froude_regimes():
    assert boat.froude(3, 4)["regime"] == "displacement"
    assert boat.froude(20, 4)["regime"] == "planing"


def test_box_stability():
    r = boat.stability_box(beam_m=1.0, draft_m=0.2, kg_m=0.15)
    assert r["BM_m"] == approx(1 / 2.4) and r["GM_m"] == approx(0.1 + 1 / 2.4 - 0.15)


def test_fillet_weld_matches_domain_file_example():
    # weldments.md: a=5 in S355 ~= 1.2 kN/mm
    r = weldments.fillet_weld(a_mm=5, length_mm=200, grade="S355")
    assert r["capacity_per_mm_kN"] == approx(1.2, 0.01)
    assert r["f_vw_d_MPa"] == approx(241, 0.005)


def test_fillet_weld_minimum_length_check():
    r = weldments.fillet_weld(a_mm=5, length_mm=35)
    assert not {c["check"]: c["pass"] for c in r["checks"]}["l_eff >= max(30 mm, 6a)"]


def test_required_throat_is_consistent():
    req = weldments.required_throat(force_kn=100, length_mm=150)
    cap = weldments.fillet_weld(req["a_chosen_mm"], 150)["capacity_kN"]
    assert cap >= 100


def test_leg_throat():
    assert weldments.leg_to_throat(7) == approx(4.95)


def test_shs_mass():
    # SHS 40x40x3 sharp-corner area = 1600 - 34^2 = 444 mm^2 -> 3.485 kg/m
    assert weldments.tube_mass(40, 3, 1000)["mass_per_m_kg"] == approx(3.485, 1e-3)


def test_bolt_hole_matches_conventions():
    # conventions.md medium clearance values
    for size, d in {"M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0}.items():
        assert fasteners.bolt_hole(size)["clearance_hole_mm"]["chosen"] == d


def test_tapped_hole_in_aluminium():
    r = fasteners.bolt_hole("M6", tapped_material="aluminium")
    assert r["tap_drill_mm"] == 5.0 and r["thread_engagement_min_mm"] == 9.0


def test_iso286_h7_g6_25mm():
    # ISO 286-2: 25 H7 = +0/+21 um, 25 g6 = -7/-20 um
    f = fasteners.fit(25, "H7/g6")
    assert (f["hole"]["lower_dev_um"], f["hole"]["upper_dev_um"]) == (0, 21)
    assert (f["shaft"]["lower_dev_um"], f["shaft"]["upper_dev_um"]) == (-20, -7)
    assert f["type"] == "clearance"
    assert f["max_clearance_mm"] == approx(0.041) and f["min_clearance_mm"] == approx(0.007)


def test_iso286_fit_types():
    assert fasteners.fit(25, "H7/k6")["type"] == "transition"
    assert fasteners.fit(25, "H7/p6")["type"] == "interference"
    assert fasteners.fit(40, "H7/h6")["min_clearance_mm"] == 0


def test_unknown_size_raises():
    with pytest.raises(ValueError):
        fasteners.bolt_hole("M7")


def test_shaft_diameter_hand_calc():
    # T = 100 N.m, tau = 40 MPa, no keyway: d = (16*1e5/(pi*40))^(1/3) = 23.35 mm
    r = shafts.shaft_diameter(torque_nm=100, tau_allow_mpa=40, keyway=False)
    assert r["d_min_mm"] == approx(23.35, 1e-3) and r["d_chosen_mm"] == 25


def test_key_selection_din6885():
    r = shafts.key(30, torque_nm=50, hub_length_mm=40)
    assert (r["key_b_mm"], r["key_h_mm"], r["shaft_groove_t1_mm"]) == (8, 7, 4.0)
    assert r["surface_pressure_MPa"] == approx(2 * 50e3 / (30 * 3 * 32), 1e-2)


def test_bearing_life_iso281():
    r = shafts.bearing_life(c_kn=13.5, p_kn=1.5, rpm=1500, required_hours=20000)
    assert r["L10_million_rev"] == approx(729)
    assert r["L10h_hours"] == approx(729e6 / 90000, 1e-3)  # 8100 h
    assert r["checks"][0]["pass"] is False  # < 20 000 h required
    # C needed for 20 000 h: P * (20000*60*1500/1e6)^(1/3) = 1.5 * 1800^(1/3)
    assert r["C_required_kN"] == approx(1.5 * 1800 ** (1 / 3), 1e-3)


def test_dn50_pn16_matches_the_benchmark_flange():
    from cadkit.calculators import flanges

    f = flanges.en1092(dn=50, pn=16)
    assert (f["outside_diameter_mm"], f["bolt_circle_mm"], f["holes"], f["hole_diameter_mm"]) == (
        165,
        125,
        4,
        18,
    )


def test_unknown_flange_size_is_refused():
    import pytest

    from cadkit.calculators import flanges

    with pytest.raises(ValueError):
        flanges.en1092(dn=55)


def test_dn65_warns_about_the_4_hole_legacy_flanges():
    from cadkit.calculators import flanges

    f = flanges.en1092(dn=65, pn=16)
    assert f["holes"] == 8 and "4 holes" in f["warning"] and f["verified_against_standard"]
