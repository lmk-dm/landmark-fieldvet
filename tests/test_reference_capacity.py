import json
import subprocess
import sys
from pathlib import Path

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


def test_publish_capacity_cli(tmp_path):
    out = tmp_path / "caps"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "landmark_field_network.cli",
            "publish-capacity",
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env={**dict(**__import__("os").environ), "PYTHONPATH": "src"},
    )
    payload = json.loads(proc.stdout)
    assert payload["count"] == 5
    assert (out / "gulf_of_mexico_capacity.json").is_file()
    assert (out / "mature_conventional_capacity.json").is_file()
