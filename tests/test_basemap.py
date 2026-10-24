"""Street context remains a display layer, with a complete local asset pack."""
import hashlib
import json

import h3
import pandas as pd
import pytest

from agap.basemap import DIRECTORY, LOCAL_STYLE, REMOTE_STYLE, basemap_source
from agap.community_map import community_hex_deck, community_street_deck, invitation_change_points, selected_hex_community


def test_incomplete_map_pack_is_not_advertised_as_offline(tmp_path):
    assert basemap_source(tmp_path) == dict(style=REMOTE_STYLE, offline=False)
    (tmp_path / "style.json").write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps(dict(assets=[dict(path="tile.pbf")])))
    assert not basemap_source(tmp_path)["offline"]
    (tmp_path / "tile.pbf").write_bytes(b"fixture")
    assert basemap_source(tmp_path) == dict(style=LOCAL_STYLE, offline=True)


def test_local_style_uses_the_browser_origin_and_hosted_prefix(tmp_path):
    style = dict(glyphs="/app/static/maps/laguna/fonts/{fontstack}/{range}.pbf",
                 sprite="/app/static/maps/laguna/sprite", sources={"streets": dict(
                     tiles=["/app/static/maps/laguna/tiles/{z}/{x}/{y}.pbf"])})
    (tmp_path / "style.json").write_text(json.dumps(style))
    (tmp_path / "tile.pbf").write_bytes(b"fixture")
    (tmp_path / "manifest.json").write_text(json.dumps(dict(assets=[dict(path="tile.pbf")])))
    source = basemap_source(tmp_path, "https://demo.example:8443/agap/?ignored=yes", "agap")
    assert source["offline"] and source["style"].startswith("https://demo.example:8443/agap/app/static/")
    rendered = json.loads(next(tmp_path.glob("style-runtime-*.json")).read_text())
    assert rendered["glyphs"] == "https://demo.example:8443/agap" + style["glyphs"]
    assert rendered["sprite"] == "https://demo.example:8443/agap" + style["sprite"]
    assert rendered["sources"]["streets"]["tiles"][0].startswith("https://demo.example:8443/agap/")
    assert json.loads((tmp_path / "style.json").read_text()) == style
    with pytest.raises(ValueError):
        basemap_source(tmp_path, "file:///tmp/anything")


@pytest.mark.skipif(not (DIRECTORY / "manifest.json").exists(), reason="Run make collect-map for the local street pack")
def test_local_pack_checksums_limits_and_asset_urls():
    manifest = json.loads((DIRECTORY / "manifest.json").read_text())
    style = json.loads((DIRECTORY / "style.json").read_text())
    assert manifest["tile_count"] <= 3000 and manifest["total_bytes"] <= 50_000_000
    assert manifest["concurrency"] <= 4 and "AGAP-CKD" in manifest["user_agent"]
    for asset in manifest["assets"]:
        data = (DIRECTORY / asset["path"]).read_bytes()
        assert len(data) == asset["bytes"]
        assert hashlib.sha256(data).hexdigest() == asset["sha256"]
    for source in style["sources"].values():
        assert not source.get("url")
        assert all(url.startswith("/app/static/maps/laguna/") for url in source["tiles"])
        assert "OpenStreetMap" in source["attribution"]
    assert style["glyphs"].startswith("/app/static/maps/laguna/")
    assert style["sprite"].startswith("/app/static/maps/laguna/")


def test_street_overlays_reconcile_to_the_current_cohort_and_keep_truth_out():
    cell = h3.latlng_to_cell(14.2, 121.2, 8)
    locations = pd.DataFrame(dict(resident_id=["A", "B"], municipality="Town", latitude=[14.2, 14.201],
                                 longitude=[121.2, 121.201], h3=cell))
    queue = locations.assign(score=[.8, .2], invitation_status=["Invited", "Not invited"], y_true=[True, False])
    facilities = locations.iloc[:1].assign(facility_id="SIM-1")
    before = queue.copy(deep=True)
    street = json.loads(community_street_deck(queue, locations, facilities, LOCAL_STYLE,
                                            planned=True, selected_resident="B").to_json())
    layers = {layer["id"]: layer for layer in street["layers"]}
    row = layers["communities"]["data"][0]
    assert row["adults"] == 2 and row["mean_score"] == .5 and row["invitation_coverage"] == .5
    assert "y_true" not in row and "positive_detected" not in row
    assert street["initialViewState"]["pitch"] == 0 and street["mapStyle"] == LOCAL_STYLE
    assert not layers["facilities"]["pickable"] and not layers["selected_resident"]["pickable"]
    assert all(layers[name]["radiusUnits"] == "pixels" for name in ("communities", "facilities", "selected_resident"))
    assert layers["selected_resident"]["data"][0]["longitude"] == 121.201
    state = {"selection": {"objects": {"communities": [row]}}}
    assert selected_hex_community(state, {"Town"}, "communities") == "Town"
    assert selected_hex_community(state, {"Town"}) is None  # layer identities remain distinct
    tilted = json.loads(community_hex_deck(queue, locations, facilities, basemap_style=LOCAL_STYLE).to_json())
    assert tilted["mapStyle"] == LOCAL_STYLE and tilted["initialViewState"]["pitch"] > 0
    assert not tilted["views"][0].get("clear")  # street tiles remain visible below the overlay
    pd.testing.assert_frame_equal(queue, before)


def test_model_change_markers_join_actual_ids_without_truth_or_unchanged_residents():
    locations = pd.DataFrame(dict(resident_id=["A", "B", "C"], municipality="Town", latitude=[14.2, 14.201, 14.202],
        longitude=[121.2, 121.201, 121.202], y_true=[True, False, True]))
    changes = pd.DataFrame(dict(resident_id=["C", "B", "A"],
        change=["Invited by both", "Removed with climate", "Added with climate"], completed=True))
    points = invitation_change_points(locations, changes).set_index("resident_id")
    assert set(points.index) == {"A", "B"}
    assert points.loc["B", "longitude"] == 121.201
    assert points.loc["A", "fill_color"][-1] > 0 and points.loc["B", "fill_color"][-1] == 0
    assert not {"y_true", "completed", "positive_detected"} & set(points.columns)
    queue = locations.assign(score=.5, invitation_status="Not invited")
    facilities = locations.iloc[:1].assign(facility_id="SIM-1")
    for builder, options in ((community_street_deck, dict(style=LOCAL_STYLE)), (community_hex_deck, dict(basemap_style=LOCAL_STYLE))):
        deck = json.loads(builder(queue, locations, facilities, model_changes=changes, **options).to_json())
        layer = next(layer for layer in deck["layers"] if layer["id"] == "invitation_changes")
        assert {row["resident_id"] for row in layer["data"]} == {"A", "B"}
        assert layer["radiusUnits"] == "pixels" and not layer["pickable"]
        assert all("y_true" not in row and "completed" not in row for row in layer["data"])
    assert invitation_change_points(locations, None).empty
