from landmark_field_network.examples.reference_capacity import contracts, write_contracts


def test_five_reference_assets_have_admin1_keys(tmp_path):
    rows = contracts()
    assert len(rows) == 5
    by_asset = {row["asset"]: row for row in rows}
    assert by_asset["Bakken"]["admin1_key"] == "US-ND"
    assert by_asset["Permian"]["admin1_key"] == "US-TX"
    assert by_asset["Gulf of Mexico"]["admin1_key"] == "US"
    assert by_asset["Gulf of Mexico"]["state"] == ""
    paths = write_contracts(tmp_path)
    assert len(paths) == 5
    assert (tmp_path / "gulf_of_mexico_capacity.json").is_file()
