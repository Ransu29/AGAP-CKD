"""NFR-11/12: the offline municipal map builds from collected boundaries only."""
import json

import pandas as pd
import pytest

from agap.mapping import municipal_features, municipal_map


def square(name, lon, lat, half=.05):
    """A tiny square polygon feature around (lon, lat)."""
    ring = [[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
            [lon - half, lat + half], [lon - half, lat - half]]
    return {"type": "Feature", "properties": {"shapeName": name},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


@pytest.fixture
def boundaries(tmp_path):
    directory = tmp_path / "data/raw/boundaries"
    directory.mkdir(parents=True)
    province = square("Laguna", 121.3, 14.2, half=.5)
    municipalities = [square("Biñan", 121.2, 14.2), square("Santa Rosa", 121.4, 14.2), square("Cavite", 121.95, 14.2)]
    (directory / "PHL_ADM2_simplified.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [province]}))
    (directory / "PHL_ADM3_simplified.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": municipalities}))
    return tmp_path


def test_features_clip_to_the_pilot_province(boundaries):
    features = municipal_features(boundaries, "Laguna")
    assert {f["properties"]["shapeName"] for f in features["features"]} == {"Biñan", "Santa Rosa"}
    assert {f["properties"]["shapeName"] for f in municipal_features(boundaries, "LAGUNA")["features"]} == {"Biñan", "Santa Rosa"}


def test_missing_or_misnamed_boundaries_return_none(boundaries):
    assert municipal_features(boundaries / "missing", "Laguna") is None  # no collected boundaries
    assert municipal_features(boundaries, "Rizal") is None  # no such province


def test_map_renders_offline_choropleth_and_service_points(boundaries):
    features = municipal_features(boundaries, "Laguna")
    summary = pd.DataFrame(dict(municipality=["Biñan", "Santa Rosa"], value=[12, 40]))
    facilities = pd.DataFrame(dict(facility_id=["SIM-001"], municipality=["Biñan"],
                                   latitude=[14.2], longitude=[121.2], capacity=[100]))
    figure = municipal_map(summary, features, facilities, color_title="Invited")
    first, second, colorbar, markers = figure.data
    assert first.name == "Biñan" and second.name == "Santa Rosa"
    assert first.customdata[0][1] == 12.0 and second.customdata[0][1] == 40.0
    assert first.fill == second.fill == "toself"
    assert colorbar.marker.showscale and colorbar.marker.colorbar.title.text == "Invited"
    assert list(markers.x) == [121.2] and list(markers.y) == [14.2]
    assert figure.layout.yaxis.scaleanchor == "x"
    assert all(trace.type == "scatter" for trace in figure.data)


def test_map_refuses_unmatched_municipalities_and_empty_input(boundaries):
    features = municipal_features(boundaries, "Laguna")
    fixture_zones = pd.DataFrame(dict(municipality=["Fixture zone 1", "Fixture zone 2"], value=[1, 2]))
    assert municipal_map(fixture_zones, features) is None
    assert municipal_map(pd.DataFrame(columns=["municipality", "value"]), features) is None
    assert municipal_map(fixture_zones, None) is None
