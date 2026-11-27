from landmark_field_network.examples.mature_water import (
    BASE_INJECT_BWPD,
    build_mature_water,
    export_capacity_contract,
)


def test_mature_capacity_contract_matches_base_arc():
    contract = export_capacity_contract()
    assert contract["asset"] == "Mature conventional"
    assert contract["admin1_key"] == "US-TX"
    assert contract["spare_water_bwpd"] == BASE_INJECT_BWPD
    assert contract["source"].startswith("landmark-field-network")


def test_mature_water_model_builds():
    model = build_mature_water(n_floods=4)
    assert len(model.projects) == 8  # 4 floods + 4 facilities
    assert any(a.id == "inject_water" for a in model.network.arcs)
