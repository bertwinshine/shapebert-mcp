"""calc_hand_check: closed-form estimates against hand-worked values."""

import json
import math
import re
from pathlib import Path

import pytest

from cadkit.calculators import hand_checks as hc

STEEL = {"E_mpa": 210000}
BEAM = {"length_mm": 200, "width_mm": 20, "height_mm": 20, **STEEL}


def _passed(reply, name):
    return next(c["pass"] for c in reply["checks"] if c["check"] == name)


def test_axial_bar_stress_and_elongation():
    r = hc.axial_bar(force_n=20000, area_mm2=200, length_mm=100, **STEEL)["results"]
    assert r["stress_mpa"] == 100 and r["elongation_mm"] == pytest.approx(20000 * 100 / (210000 * 200))


def test_cantilever_adds_the_shear_deflection_and_checks_slenderness():
    reply = hc.cantilever(force_n=1000, **BEAM)
    r = reply["results"]
    inertia = 20 * 20**3 / 12
    assert r["tip_deflection_bending_mm"] == pytest.approx(1000 * 200**3 / (3 * 210000 * inertia), abs=1e-6)
    shear_modulus = 210000 / 2.6
    assert r["tip_deflection_shear_mm"] == pytest.approx(1000 * 200 / (5 / 6 * shear_modulus * 400), abs=1e-6)
    assert r["tip_deflection_mm"] == pytest.approx(
        r["tip_deflection_bending_mm"] + r["tip_deflection_shear_mm"]
    )
    assert r["root_bending_stress_mpa"] == pytest.approx(150)
    assert _passed(reply, "slender beam")
    assert not _passed(hc.cantilever(force_n=1000, **{**BEAM, "length_mm": 100}), "slender beam")
    assert "topic 2" in reply["source"] and "to be checked" in reply["source"]


def test_euler_column_uses_the_weaker_axis_and_k_factor():
    fixed_free = hc.euler_column(length_mm=200, width_mm=40, height_mm=20, **STEEL)["results"]
    inertia = 40 * 20**3 / 12
    assert fixed_free["K"] == 2 and fixed_free["critical_load_n"] == pytest.approx(
        math.pi**2 * 210000 * inertia / 400**2, abs=1e-3
    )
    assert fixed_free["critical_load_with_shear_n"] < fixed_free["critical_load_n"]
    pinned = hc.euler_column(length_mm=200, width_mm=40, height_mm=20, end_condition="pinned-pinned", **STEEL)
    assert pinned["results"]["critical_load_n"] == pytest.approx(4 * fixed_free["critical_load_n"], rel=1e-9)
    assert hc.END_CONDITIONS == {
        "fixed-free": 2.0,
        "pinned-pinned": 1.0,
        "fixed-pinned": 0.7,
        "fixed-fixed": 0.5,
    }


def test_a_stocky_column_yields_before_it_buckles():
    stocky = hc.euler_column(length_mm=200, width_mm=20, height_mm=20, yield_mpa=235, **STEEL)
    assert stocky["results"]["critical_stress_mpa"] > 235 and not _passed(stocky, "elastic (Euler) range")
    slender = hc.euler_column(length_mm=2000, width_mm=20, height_mm=20, yield_mpa=235, **STEEL)
    assert _passed(slender, "elastic (Euler) range")


def test_thin_cylinder_and_its_wall_check():
    reply = hc.thin_cylinder(pressure_mpa=2, mean_radius_mm=100, thickness_mm=5)
    assert reply["results"]["hoop_stress_mpa"] == 40 and reply["results"]["axial_stress_mpa"] == 20
    assert _passed(reply, "thin wall")
    assert not _passed(hc.thin_cylinder(pressure_mpa=2, mean_radius_mm=20, thickness_mm=5), "thin wall")


def test_thick_cylinder_lame_values_and_boundary_conditions():
    r = hc.thick_cylinder(inner_radius_mm=50, outer_radius_mm=60, inner_pressure_mpa=10)["results"]
    assert r["radial_stress_inner_mpa"] == pytest.approx(-10) and r["radial_stress_outer_mpa"] == 0
    assert r["hoop_stress_inner_mpa"] == pytest.approx(10 * (60**2 + 50**2) / (60**2 - 50**2), abs=1e-6)
    assert r["axial_stress_closed_ends_mpa"] == pytest.approx(10 * 50**2 / (60**2 - 50**2), abs=1e-6)
    thin = hc.thick_cylinder(inner_radius_mm=1000, outer_radius_mm=1001, inner_pressure_mpa=1)["results"]
    assert thin["hoop_stress_inner_mpa"] == pytest.approx(thin["thin_wall_hoop_mpa"], rel=1e-3)


def test_kirsch_hole_peak_and_net_section():
    r = hc.kirsch_hole(remote_stress_mpa=50, hole_diameter_mm=10, plate_width_mm=100)["results"]
    assert r["Kt"] == 3 and r["peak_stress_mpa"] == 150 and r["stress_at_hole_along_load_mpa"] == -50
    assert r["d_over_w"] == 0.1 and r["net_section_stress_mpa"] == pytest.approx(50 * 100 / 90, abs=1e-6)


@pytest.mark.parametrize(
    "supports, mode, beta_l",
    [
        ("clamped-free", 1, 1.875104),
        ("clamped-free", 2, 4.694091),
        ("pinned-pinned", 2, 2 * math.pi),
        ("clamped-clamped", 1, 4.730041),
        ("free-free", 1, 4.730041),
    ],
)
def test_beam_frequency_roots(supports, mode, beta_l):
    r = hc.beam_frequency(density_kg_m3=7850, supports=supports, mode=mode, **BEAM)["results"]
    assert r["beta_L"] == pytest.approx(beta_l, abs=1e-6)


def test_beam_frequency_matches_the_validation_cantilever():
    r = hc.beam_frequency(density_kg_m3=7850, **BEAM)["results"]
    assert r["frequency_hz"] == pytest.approx(417.758, abs=1e-3)


def test_plane_wall_and_thermal_expansion():
    wall = hc.plane_wall(k_w_mk=50, area_mm2=200, thickness_mm=100, t_hot_c=100, t_cold_c=20)["results"]
    assert wall["heat_flow_w"] == pytest.approx(8) and wall["thermal_resistance_k_w"] == pytest.approx(10)
    heat = hc.thermal_expansion(alpha_1_k=12e-6, delta_t_k=100, length_mm=100, E_mpa=210000)["results"]
    assert heat["free_elongation_mm"] == pytest.approx(0.12) and heat["fully_restrained_stress_mpa"] == -252
    assert "fully_restrained_stress_mpa" not in hc.thermal_expansion(1e-5, -20, 50)["results"]


@pytest.mark.parametrize(
    "case, kwargs, message",
    [
        (hc.axial_bar, {"force_n": -1, "area_mm2": 1, "length_mm": 1, "E_mpa": 1}, "force_n"),
        (hc.axial_bar, {"force_n": True, "area_mm2": 1, "length_mm": 1, "E_mpa": 1}, "force_n"),
        (hc.cantilever, {"force_n": 1, **BEAM, "nu": 0.5}, "nu"),
        (
            hc.euler_column,
            {"length_mm": 1, "E_mpa": 1, "width_mm": 1, "height_mm": 1, "end_condition": "x"},
            "end_condition",
        ),
        (hc.thick_cylinder, {"inner_radius_mm": 5, "outer_radius_mm": 5, "inner_pressure_mpa": 1}, "larger"),
        (hc.kirsch_hole, {"remote_stress_mpa": 1, "hole_diameter_mm": 10, "plate_width_mm": 10}, "smaller"),
        (hc.beam_frequency, {**BEAM, "density_kg_m3": 1, "mode": 11}, "mode"),
        (
            hc.plane_wall,
            {"k_w_mk": 1, "area_mm2": 1, "thickness_mm": 1, "t_hot_c": 20, "t_cold_c": 20},
            "above",
        ),
        (hc.thermal_expansion, {"alpha_1_k": 1e-5, "delta_t_k": float("nan"), "length_mm": 1}, "delta_t_k"),
    ],
)
def test_bad_inputs_are_refused(case, kwargs, message):
    with pytest.raises(ValueError, match=message):
        case(**kwargs)


def _every_case() -> list[dict]:
    return [
        hc.axial_bar(1, 1, 1, 1),
        hc.cantilever(1, 200, 20, 20, 1),
        hc.euler_column(100, 1, 5, 5),
        hc.thin_cylinder(1, 100, 1),
        hc.thick_cylinder(10, 20, 1),
        hc.kirsch_hole(1),
        hc.beam_frequency(200, 20, 20, 1, 1),
        hc.plane_wall(1, 1, 1, 2, 1),
        hc.thermal_expansion(1e-5, 1, 1),
    ]


def _knowledge_sources() -> dict[str, str]:
    """{topic number: its "- Source:" text, lines joined} from the knowledge file."""
    text = (Path(hc.__file__).parents[2] / hc.KNOWLEDGE).read_text(encoding="utf-8")
    found = re.findall(r"^### Topic (\d+)\..*?^- Source: (.*?)\.\n(?=- |\n|###)", text, re.M | re.S)
    return {topic: " ".join(source.split()) for topic, source in found}


def test_every_source_is_the_knowledge_file_source_word_for_word():
    sources = _knowledge_sources()
    for reply in _every_case():
        topic, source = re.fullmatch(r".*?, topic (\d+); (.*)", reply["source"]).groups()
        assert source == sources[topic], reply["case"]


def test_every_case_names_its_formula_assumptions_and_source():
    for reply in _every_case():
        assert reply["formula"] and reply["assumptions"] and reply["fea_differs"]
        assert reply["source"].startswith("knowledge/domains/fea-mechanics.md, topic ")


def test_the_tool_lists_the_cases_and_refuses_unknown_ones():
    server = pytest.importorskip("server")
    reply = json.loads(server.calc_hand_check("torsion_tube", {}))
    assert reply["ok"] is False and "cantilever" in reply["available"] and "kirsch_hole" in reply["available"]
    ok = json.loads(
        server.calc_hand_check(
            "plane_wall", {"k_w_mk": 50, "area_mm2": 200, "thickness_mm": 100, "t_hot_c": 100, "t_cold_c": 20}
        )
    )
    assert ok["results"]["heat_flow_w"] == 8
