"""Offline municipal choropleth and service-point map (NFR-11, NFR-12).

Municipal polygons come from the collected geoBoundaries ADM3 file, clipped to the
pilot province with the same rule as the public geography. Rendering uses local
Cartesian traces without geo-projection assets or map tiles (AT-11). Community
metrics shown on the map are synthetic.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale


def municipal_features(root, province):
    """ADM3 FeatureCollection for the pilot province, or None when boundaries are unavailable.

    Feature properties keep their original shapeName key so the map and the
    public geography resolve municipalities identically.
    """
    directory = Path(root) / "data/raw/boundaries"
    province_file, municipal_file = directory / "PHL_ADM2_simplified.geojson", directory / "PHL_ADM3_simplified.geojson"
    if not (province_file.is_file() and municipal_file.is_file()):
        return None
    from shapely.geometry import shape

    provinces = json.loads(province_file.read_text())
    matches = [f for f in provinces["features"] if f["properties"]["shapeName"].casefold() == province.casefold()]
    if len(matches) != 1:
        return None
    polygon = shape(matches[0]["geometry"]).buffer(.002)
    features = [f for f in json.loads(municipal_file.read_text())["features"]
                if polygon.covers(shape(f["geometry"]).representative_point())]
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def municipal_map(summary, features, facilities=None, color_title="", value_format=",.0f"):
    """Choropleth of one value per municipality plus hypothetical service points.

    summary needs municipality and value columns; detail, when present, is added to
    the hover. Returns None when there are no municipal polygons or the summary
    names municipalities the polygons do not contain (for example fixture zones).
    """
    if features is None or summary.empty:
        return None
    names = {f["properties"]["shapeName"] for f in features["features"]}
    if not set(summary.municipality) <= names:
        return None
    figure = go.Figure()
    values = summary.set_index("municipality")
    low, high = float(summary.value.min()), float(summary.value.max())
    colorscale = [[0, "#edf0e7"], [1, "#285a46"]]
    latitudes = []
    for feature in features["features"]:
        name = feature["properties"]["shapeName"]
        if name not in values.index:
            continue
        row = values.loc[name]
        value = float(row.value)
        fraction = (value-low)/(high-low) if high > low else .5
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        x, y = [], []
        for polygon in polygons:
            for ring in polygon:
                x.extend([p[0] for p in ring] + [None])
                y.extend([p[1] for p in ring] + [None])
                latitudes.extend(p[1] for p in ring)
        figure.add_trace(go.Scatter(
            x=x, y=y, mode="lines", fill="toself", name=name, showlegend=False,
            fillcolor=sample_colorscale(colorscale, [fraction])[0], line=dict(color="white", width=.6),
            customdata=[[name, value, row.get("detail", "")]] * len(x),
            hovertemplate="%{customdata[0]}<br>%{customdata[1]:" + value_format + "}%{customdata[2]}<extra></extra>"))
    figure.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers", showlegend=False, hoverinfo="skip",
        marker=dict(color=[low], cmin=low, cmax=high if high > low else low+1,
                    colorscale=colorscale, showscale=True,
                    colorbar=dict(title=dict(text=color_title, side="right"), thickness=12, len=.75))))
    if facilities is not None and len(facilities):
        figure.add_trace(go.Scatter(
            x=facilities.longitude, y=facilities.latitude, mode="markers",
            marker=dict(size=8, color="#b36c30", symbol="cross-thin", line=dict(width=2)),
            customdata=pd.concat([facilities.facility_id + " · " + facilities.municipality, facilities.capacity], axis=1).to_numpy(),
            hovertemplate="Hypothetical service point %{customdata[0]}<br>capacity %{customdata[1]:.0f} panels<extra></extra>",
            showlegend=False))
    figure.update_layout(
        template="plotly_white", height=430, margin=dict(l=0, r=0, t=8, b=0),
        xaxis=dict(title="Longitude (°E)", showgrid=False, zeroline=False),
        yaxis=dict(title="Latitude (°N)", showgrid=False, zeroline=False,
                   scaleanchor="x", scaleratio=1/np.cos(np.radians(np.mean(latitudes)))))
    return figure
