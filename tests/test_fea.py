import pytest

from cadkit import fea


def test_material_table_and_aliases():
    assert fea.material("Steel")["E_mpa"] == 210000
    assert fea.material("aluminum")["name"] == "aluminium"
    assert fea.material("petg")["density_kg_m3"] == 1270
    with pytest.raises(ValueError, match="choose one of"):
        fea.material("titanium")


def test_every_material_has_thermal_values_and_plastics_say_typical():
    for name, props in fea.MATERIALS.items():
        assert props["k_w_mk"] > 0 and props["cp_j_kgk"] > 0 and 0 < props["alpha_1_k"] < 1e-3
        assert (props.get("thermal_values") == "typical") == (name in {"PETG", "PLA"})
    assert fea.material("aluminium")["alpha_1_k"] == 23.6e-6


FORCE = {"type": "force", "faces": ["Face2"], "value_n": 100, "direction": [0, 0, -1]}


def test_valid_setup_passes():
    pressure = {"type": "pressure", "faces": ["Face6"], "value_mpa": -0.2}
    loads = fea.check_setup("static", 3, fixed_faces=["Face1"], loads=[FORCE, pressure])["loads"]
    assert loads[0]["direction"] == [0.0, 0.0, -1.0] and loads[1]["value_mpa"] == -0.2


@pytest.mark.parametrize(
    "fixed, loads, size, message",
    [
        ([], [FORCE], 3, "fixed_faces"),
        (["Face1; import os"], [FORCE], 3, "not face names"),
        (["Face1"], [], 3, "at least one load"),
        (["Face1"], [{**FORCE, "direction": [0, 0, 0]}], 3, "non-zero"),
        (["Face1"], [{**FORCE, "value_n": -5}], 3, "flip the direction"),
        (["Face1"], [{**FORCE, "type": "moment"}], 3, "'force' or 'pressure'"),
        (["Face1"], [FORCE], 0, "mesh_size_mm"),
        (["Face1"], [FORCE], 0.04, "0.05 mm minimum"),
    ],
)
def test_bad_setup_is_refused(fixed, loads, size, message):
    with pytest.raises(ValueError, match=message):
        fea.check_setup("static", size, fixed_faces=fixed, loads=loads)


def test_modal_setup_needs_no_loads_and_refuses_them():
    checked = fea.check_setup("modal", 3, 6, fixed_faces=["Face1"])
    assert checked["loads"] == [] and checked["fixed_faces"] == ["Face1"]
    with pytest.raises(ValueError, match=r"does not use \['loads'\]"):
        fea.check_setup("modal", 3, fixed_faces=["Face1"], loads=[FORCE])
    with pytest.raises(ValueError, match="between 1 and 50"):
        fea.check_setup("modal", 3, 0, fixed_faces=["Face1"])
    with pytest.raises(ValueError, match="analysis_type must be one of"):
        fea.check_setup("acoustic", 3, fixed_faces=["Face1"])


HOT = {"faces": ["Face1"], "temperature_c": 100}


def test_thermal_steady_needs_temperatures_and_no_mechanics():
    temps = fea.check_setup("thermal_steady", 3, temperatures=[HOT])["temperatures"]
    assert temps == [{"faces": ["Face1"], "temperature_c": 100.0}]
    with pytest.raises(ValueError, match="at least one face temperature"):
        fea.check_setup("thermal_steady", 3)
    with pytest.raises(ValueError, match=r"\['fixed_faces', 'loads'\]"):
        fea.check_setup("thermal_steady", 3, fixed_faces=["Face1"], loads=[FORCE], temperatures=[HOT])
    with pytest.raises(ValueError, match="absolute zero"):
        fea.check_setup("thermal_steady", 3, temperatures=[{**HOT, "temperature_c": -300}])
    with pytest.raises(ValueError, match=r"does not use \['temperatures'\]"):
        fea.check_setup("static", 3, fixed_faces=["Face1"], loads=[FORCE], temperatures=[HOT])


def test_thermal_transient_needs_temperatures_and_time():
    checked = fea.check_setup("thermal_transient", 3, temperatures=[HOT], time_end_s=1000, time_step_s=50)
    assert checked["time_end_s"] == 1000.0 and checked["time_step_s"] == 50.0
    with pytest.raises(ValueError, match="time_end_s and time_step_s"):
        fea.check_setup("thermal_transient", 3, temperatures=[HOT])
    with pytest.raises(ValueError, match="at most 500 time steps"):
        fea.check_setup("thermal_transient", 3, temperatures=[HOT], time_end_s=1000, time_step_s=1)
    with pytest.raises(ValueError, match="not be larger"):
        fea.check_setup("thermal_transient", 3, temperatures=[HOT], time_end_s=10, time_step_s=50)
    with pytest.raises(ValueError, match=r"does not use \['time_end_s'\]"):
        fea.check_setup("thermal_steady", 3, temperatures=[HOT], time_end_s=10)


def test_buckling_needs_supports_and_loads():
    checked = fea.check_setup("buckling", 3, 4, fixed_faces=["Face5"], loads=[FORCE])
    assert checked["loads"][0]["value_n"] == 100
    with pytest.raises(ValueError, match="at least one load"):
        fea.check_setup("buckling", 3, fixed_faces=["Face5"])
    with pytest.raises(ValueError, match="between 1 and 50"):
        fea.check_setup("buckling", 3, 99, fixed_faces=["Face5"], loads=[FORCE])
    assert set(fea.NOTES) == set(fea.ANALYSIS_TYPES)


def test_thermomechanical_needs_supports_and_temperatures_loads_optional():
    checked = fea.check_setup("thermomechanical", 3, sliding_faces=["Face1", "Face3"], temperatures=[HOT])
    assert checked["sliding_faces"] == ["Face1", "Face3"] and checked["loads"] == []
    with_load = fea.check_setup(
        "thermomechanical", 3, fixed_faces=["Face1"], loads=[FORCE], temperatures=[HOT]
    )
    assert with_load["loads"][0]["value_n"] == 100
    with pytest.raises(ValueError, match="or sliding_faces"):
        fea.check_setup("thermomechanical", 3, temperatures=[HOT])
    with pytest.raises(ValueError, match="at least one face temperature"):
        fea.check_setup("thermomechanical", 3, fixed_faces=["Face1"])


def test_analysis_names_are_plain_identifiers():
    assert fea.check_name("Bracket_FEA2") == "Bracket_FEA2"
    for bad in ("../x", "a b", "1st", "x" * 41):
        with pytest.raises(ValueError):
            fea.check_name(bad)
