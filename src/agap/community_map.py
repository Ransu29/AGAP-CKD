"""Interactive street maps and a tile-free Cartesian fallback."""
from __future__ import annotations

import h3
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk

from agap.registers import display_text


def invitation_change_points(locations, changes):
    """Project only paired invitation changes and locations into display layers."""
    columns = ["resident_id", "longitude", "latitude", "change", "fill_color", "line_color"]
    if changes is None:
        return pd.DataFrame(columns=columns)
    selected = changes.loc[changes.change.isin(["Added with climate", "Removed with climate"]), ["resident_id", "change"]]
    points = selected.merge(locations[["resident_id", "longitude", "latitude"]], on="resident_id", validate="one_to_one")
    if len(points) != len(selected) or not np.isfinite(points[["longitude", "latitude"]]).all().all():
        raise ValueError("Every changed invitation requires its resident's saved location.")
    added = points.change.eq("Added with climate")
    points["fill_color"] = [[17, 126, 110, 235] if value else [175, 83, 55, 0] for value in added]
    points["line_color"] = [[255, 255, 255, 255] if value else [175, 83, 55, 255] for value in added]
    return points[columns]


def _invitation_change_layer(locations, changes, hex_rows=None):
    points = invitation_change_points(locations, changes)
    if points.empty:
        return []
    heights = {row["h3"]: row["elevation"] for row in hex_rows or []}
    points["display_elevation"] = [heights.get(h3.latlng_to_cell(lat, lon, 8), 0) + 100 if hex_rows else 0
                                    for lat, lon in zip(points.latitude, points.longitude)]
    return [pdk.Layer("ScatterplotLayer", points.to_dict("records"), id="invitation_changes",
        get_position="[longitude, latitude, display_elevation]", get_fill_color="fill_color", get_line_color="line_color",
        get_radius=4.5, radius_units=pdk.types.String("pixels"), stroked=True, line_width_min_pixels=1.6, pickable=False)]


def selected_community(points, allowed):
    for point in points:
        value = point.get("customdata")
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
        if isinstance(value, str) and value in allowed:
            return value
    return None


# Operational colourings for the community circles: (column, legend). Values lie in [0, 1].
COMMUNITY_METRICS = {
    "Without a questionnaire": ("no_questionnaire", "Share of cohort adults without a questionnaire"),
    "Invitation coverage (draft plan)": ("invitation_coverage", "Share of cohort adults invited in the draft plan"),
    "Open follow-up work (approved round)": ("open_share", "Share of the round's invitations with open tasks"),
    "Mean model score": ("mean_score", "Mean model score (synthetic outcome)"),
}


def community_points(queue, locations, cells=None, work=None):
    """One selectable community point, with counts from the current cohort.

    ``work`` optionally adds recorded round counts per municipality (invited, open_tasks,
    overdue, open_share) from :func:`agap.community_overview.round_work`.
    """
    summary = queue.groupby("municipality", sort=True).agg(adults=("resident_id", "size"), mean_score=("score", "mean"))
    summary["invitation_coverage"] = queue.assign(invited=queue.invitation_status.eq("Invited")).groupby("municipality").invited.mean()
    summary["no_questionnaire"] = ((~queue.reported.astype(bool)).groupby(queue.municipality).mean()
                                   if "reported" in queue else np.nan)
    for column in ("invited", "open_tasks", "overdue", "open_share"):
        summary[column] = work[column].reindex(summary.index).fillna(0) if work is not None and len(work) else 0
    source = cells if cells is not None else locations
    positions = []
    for name in summary.index:
        local = source.loc[source.municipality.eq(name)]
        if local.empty:
            local = locations.loc[locations.municipality.eq(name)]
        weights = local.adult_count if "adult_count" in local else None
        lon, lat = np.average(local.longitude, weights=weights), np.average(local.latitude, weights=weights)
        point = local.iloc[np.argmin((local.longitude-lon)**2 + (local.latitude-lat)**2)]
        positions.append((point.longitude, point.latitude))
    summary[["longitude", "latitude"]] = pd.DataFrame(positions, index=summary.index)
    return summary.reset_index()


def community_street_deck(queue, locations, facilities, style, boundary=None, cells=None,
                          planned=False, selected_resident=None, model_changes=None, metric=None, work=None):
    """A north-up street map with operational community/service-point overlays."""
    points = community_points(queue, locations, cells, work)
    metric = metric or ("invitation_coverage" if planned else "mean_score")
    points["radius"] = 10 + 14*np.sqrt(points.adults / points.adults.max())
    points["fill_color"] = [[int(70-30*v), int(125+55*v), int(205-40*v), 215] for v in points[metric]]
    points["score_percent"] = points.mean_score.map(lambda value: f"{value:.1%}")
    points["coverage_percent"] = points.invitation_coverage.map(lambda value: f"{value:.1%}" if planned else "Not planned")
    points["no_questionnaire_percent"] = points.no_questionnaire.map(lambda value: f"{value:.0%}")
    points["work_text"] = [f"{int(row.open_tasks)} open tasks · {int(row.overdue)} overdue of {int(row.invited)} invited"
                           if work is not None else "No approved round" for row in points.itertuples()]
    layers = []
    if boundary:
        layers.append(pdk.Layer("GeoJsonLayer", boundary, id="boundary", filled=False,
            get_line_color=[45, 96, 155, 170], get_line_width=45, line_width_min_pixels=1, pickable=False))
    layers.append(pdk.Layer("ScatterplotLayer", facilities.to_dict("records"), id="facilities",
        get_position="[longitude, latitude]", get_fill_color=[255, 255, 255], get_line_color=[38, 66, 100],
        stroked=True, line_width_min_pixels=1.5, get_radius=4, radius_units=pdk.types.String("pixels"), pickable=False))
    layers.append(pdk.Layer("ScatterplotLayer", points.to_dict("records"), id="communities",
        get_position="[longitude, latitude]", get_fill_color="fill_color", get_radius="radius", radius_units=pdk.types.String("pixels"),
        stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2, pickable=True))
    layers.extend(_invitation_change_layer(locations, model_changes))
    selected = locations.loc[locations.resident_id.eq(selected_resident), ["longitude", "latitude"]]
    layers.append(pdk.Layer("ScatterplotLayer", selected.to_dict("records"), id="selected_resident",
        get_position="[longitude, latitude]", get_fill_color=[238, 154, 42], get_line_color=[95, 57, 5],
        stroked=True, line_width_min_pixels=2, get_radius=7, radius_units=pdk.types.String("pixels"), pickable=False))
    view = pdk.ViewState(latitude=float((locations.latitude.min()+locations.latitude.max())/2),
        longitude=float((locations.longitude.min()+locations.longitude.max())/2), zoom=9.2, pitch=0, bearing=0,
        min_zoom=7, max_zoom=17)
    return pdk.Deck(layers=layers, map_provider="maplibre", map_style=style, initial_view_state=view,
        tooltip={"text": "{municipality}\n{adults} cohort adults\nWithout a questionnaire {no_questionnaire_percent}\n"
                         "Invitation coverage {coverage_percent}\nFollow-up: {work_text}\nMean model score {score_percent}"})


def community_figure(queue, locations, facilities, boundary=None, cells=None, planned=False,
                     selected_area="All municipalities", selected_resident=None, run_id="", model_changes=None,
                     metric=None, work=None):
    figure = go.Figure()
    for feature in (boundary or {}).get("features", []):
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"] if geometry["type"] == "MultiPolygon" else []
        x, y = [], []
        for polygon in polygons:
            for ring in polygon:
                x.extend([p[0] for p in ring] + [None])
                y.extend([p[1] for p in ring] + [None])
        figure.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#9aaaa3", width=1.5), hoverinfo="skip", showlegend=False))
    if cells is not None:
        x, y = [], []
        for cell in cells.h3.unique():
            ring = list(h3.cell_to_boundary(cell))
            ring.append(ring[0])
            x.extend([p[1] for p in ring] + [None])
            y.extend([p[0] for p in ring] + [None])
        figure.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#e3e9e6", width=.5), hoverinfo="skip", showlegend=False))
    summary = community_points(queue, locations, cells, work).set_index("municipality")
    source = cells if cells is not None else locations
    centres = []
    for name in summary.index:
        local = source.loc[source.municipality.eq(name)]
        if local.empty:
            local = locations.loc[locations.municipality.eq(name)]
        weights = local.adult_count if "adult_count" in local else None
        lon, lat = np.average(local.longitude, weights=weights), np.average(local.latitude, weights=weights)
        # Keep the marker inside a represented cell, rather than in a lake between cells.
        representative = local.iloc[np.argmin((local.longitude-lon)**2 + (local.latitude-lat)**2)]
        centres.append((representative.longitude, representative.latitude))
    legends = {column: name for name, (column, _) in COMMUNITY_METRICS.items()}
    metric = metric or ("invitation_coverage" if planned else "mean_score")
    legend = legends.get(metric, metric).replace(" (draft plan)", "").replace(" (approved round)", "")
    names = list(summary.index)
    # Only community markers participate in picking; context points must not
    # intercept a nearby community click through Plotly's nearest-point hit test.
    figure.add_trace(go.Scatter(x=facilities.longitude, y=facilities.latitude, mode="markers", name="Hypothetical service points",
                               marker=dict(symbol="circle-open", size=8, color="#5d6d66"), text=facilities.facility_id,
                               hoverinfo="skip"))
    figure.add_trace(go.Scatter(
        x=[p[0] for p in centres], y=[p[1] for p in centres], mode="markers+text", name="Communities",
        customdata=names, text=[name if name == selected_area else "" for name in names], textposition="top center",
        hovertext=[f"{int(row.adults):,} cohort adults · {legend.lower()} {row[metric]:.1%}" for _, row in summary.iterrows()],
        hovertemplate="<b>%{customdata}</b><br>%{hovertext}<extra></extra>",
        marker=dict(size=12+22*np.sqrt(summary.adults/summary.adults.max()), color=summary[metric], colorscale=[[0,"#d3ddd8"],[1,"#12796d"]],
                    cmin=0, cmax=1, colorbar=dict(title=dict(text=legend, font_color="#4b5d56"), tickfont_color="#4b5d56",
                                               tickformat=".0%", thickness=12), line=dict(color="#12796d", width=1.5)),  # the one data hue outlines every community, even at low values
        selectedpoints=[names.index(selected_area)] if selected_area in names else None,
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=.65)),
    ))
    changes = invitation_change_points(locations, model_changes)
    for label, symbol, color in (("Added with climate", "circle", "#117e6e"), ("Removed with climate", "circle-open", "#d58c70")):
        points = changes.loc[changes.change.eq(label)]
        if not points.empty:
            figure.add_trace(go.Scatter(x=points.longitude, y=points.latitude, mode="markers", name=label,
                marker=dict(symbol=symbol, size=8, color=color, line=dict(width=1.5, color=color)), hoverinfo="skip"))
    person = locations.loc[locations.resident_id.eq(selected_resident)]
    if not person.empty:
        figure.add_trace(go.Scatter(x=person.longitude, y=person.latitude, mode="markers", name="Selected synthetic resident",
                                   marker=dict(symbol="star", size=17, color="#bb641e"), text=person.resident_id,
                                   hoverinfo="skip"))
    latitude = locations.latitude.mean()
    figure.update_layout(height=640, margin=dict(l=15, r=15, t=20, b=25), template="plotly_white", clickmode="event+select",
                         dragmode="pan", uirevision=run_id, selectionrevision=selected_area,
                         paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font=dict(color="#16241f"),
                         xaxis=dict(visible=False, showgrid=False, zeroline=False),
                         yaxis=dict(visible=False, showgrid=False, zeroline=False,
                                    scaleanchor="x", scaleratio=1/np.cos(np.radians(latitude))),
                         legend=dict(orientation="h", y=0, yanchor="top", x=0, font=dict(size=12, color="#4b5d56")))
    return figure


def hex_summary(queue, locations, selected_area="All municipalities", planned=False):
    """Cell estimates from represented cohort members, not municipal proxies."""
    positions = locations[["resident_id", "latitude", "longitude"]].copy()
    positions["h3"] = locations.h3 if "h3" in locations else [
        h3.latlng_to_cell(lat, lon, 8) for lat, lon in zip(locations.latitude, locations.longitude)]
    people = queue[["resident_id", "municipality", "score", "invitation_status"]].merge(
        positions, on="resident_id", validate="one_to_one", how="left")
    if people.h3.isna().any():
        raise ValueError("Every resident requires a location for the H3 view.")
    if people.groupby("h3").municipality.nunique().gt(1).any():
        raise ValueError("H3 community selection requires a consistent municipality per cell.")
    people["invited"] = people.invitation_status.eq("Invited")
    grouped = people.groupby("h3", sort=True).agg(municipality=("municipality", "first"), adults=("resident_id", "size"),
        mean_score=("score", "mean"), invitation_coverage=("invited", "mean"))
    rows = []
    for cell, row in grouped.iterrows():
        ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(cell)]
        ring.append(ring[0])
        value = float(row.invitation_coverage if planned else row.mean_score)
        alpha = 230 if selected_area in ("All municipalities", row.municipality) else 145
        rows.append(dict(h3=cell, municipality=row.municipality, adults=int(row.adults),
            mean_score=float(row.mean_score), invitation_coverage=float(row.invitation_coverage),
            score_percent=f"{row.mean_score:.1%}", coverage_percent=f"{row.invitation_coverage:.1%}" if planned else "Not planned",
            polygon=ring, elevation=int(row.adults)*90,
            fill_color=[int(97-54*value), int(152+50*value), int(215-45*value), alpha]))
    return rows


def community_hex_deck(queue, locations, facilities, boundary=None, cells=None, planned=False,
                       selected_area="All municipalities", selected_resident=None, basemap_style=None, model_changes=None):
    rows = hex_summary(queue, locations, selected_area, planned)
    layers = [pdk.Layer("PolygonLayer", rows, id="communities_hex", get_polygon="polygon", get_elevation="elevation",
                        get_fill_color="fill_color", extruded=True, pickable=True, wireframe=False)]
    if boundary:
        layers.insert(0, pdk.Layer("GeoJsonLayer", boundary, id="boundary", filled=False, stroked=True,
                                  get_line_color=[155, 178, 198], get_line_width=70, pickable=False))
    layers.append(pdk.Layer("ScatterplotLayer", facilities.to_dict("records"), id="facilities",
        get_position="[longitude, latitude]", get_fill_color=[229, 235, 244], get_radius=180, radius_min_pixels=3, pickable=False))
    layers.extend(_invitation_change_layer(locations, model_changes, rows))
    selected = locations.loc[locations.resident_id.eq(selected_resident), ["longitude", "latitude"]]
    layers.append(pdk.Layer("ScatterplotLayer", selected.to_dict("records"), id="selected_resident",
        get_position="[longitude, latitude]", get_fill_color=[247, 189, 90], get_radius=220, radius_min_pixels=6, pickable=False))
    # Tilt foreshortens northern cells and stretches the southern foreground.
    # Aim slightly south/west so Laguna fits the tall desktop canvas at startup.
    view = pdk.ViewState(latitude=float((locations.latitude.min()+locations.latitude.max())/2)-.15,
                        longitude=float((locations.longitude.min()+locations.longitude.max())/2)-.035,
                        zoom=9.4, pitch=35, bearing=-10)
    views = [pdk.View("MapView", controller=True)] if basemap_style else [
        pdk.View("MapView", controller=True, clear=True, clear_color=[19/255, 35/255, 49/255, 1])]
    return pdk.Deck(layers=layers, map_provider="maplibre" if basemap_style else None,
        map_style=basemap_style or "__MAP_STYLE__", initial_view_state=view, views=views,
        tooltip={"text": "{municipality}\n{adults} cohort adults\nMean score {score_percent}\nInvitation coverage {coverage_percent}\nH3 {h3}"})


def selected_hex_community(selection_state, allowed, layer_id="communities_hex"):
    objects = selection_state.get("selection", {}).get("objects", {})
    if not isinstance(objects, dict):
        return None
    for item in objects.get(layer_id, []):
        value = item.get("municipality") if isinstance(item, dict) else None
        if isinstance(value, str) and value in allowed:
            return value
    return None


PRECISION_STYLE = {  # dialysis clinic markers: exact positions solid, approximate ones lighter/hollow
    "osm": dict(fill=[176, 58, 46, 235], radius=7),
    "barangay": dict(fill=[214, 120, 92, 170], radius=7),
    "municipality": dict(fill=[255, 255, 255, 60], radius=8),
}


def clinic_points(clinics):
    """Dialysis clinic markers with their stated location precision; no position is presented as exact unless mapped."""
    if clinics is None or clinics.empty:
        return []
    rows = []
    for row in clinics.itertuples():
        style = PRECISION_STYLE[row.location_precision]
        telephone = row.telephone if isinstance(row.telephone, str) and row.telephone.strip() else "not listed"
        rows.append(dict(title=f"{display_text(row.name)} · PhilHealth-accredited dialysis clinic",
                         line1=f"{display_text(row.street)}, {row.municipality_name}", line2=f"Location: {row.location_label}",
                         line3=f"Tel. {telephone} · call to confirm schedule and slots", municipality=row.municipality_name,
                         latitude=row.latitude, longitude=row.longitude, fill_color=style["fill"], radius=style["radius"]))
    return rows


def _clinic_layer(clinics):
    rows = clinic_points(clinics)
    if not rows:
        return []
    return [pdk.Layer("ScatterplotLayer", rows, id="dialysis_clinics", get_position="[longitude, latitude]",
                      get_fill_color="fill_color", get_line_color=[120, 30, 20, 255], stroked=True, line_width_min_pixels=1.5,
                      get_radius="radius", radius_units=pdk.types.String("pixels"), pickable=True)]


def aggregate_deck(points, style, boundary=None, clinics=None, view=None):
    """LGU / analyst map: one circle per municipality with precomputed, already-suppressed labels.

    ``points`` needs municipality, latitude, longitude, value (0-1 or NaN when suppressed), adults_label and value_label.
    """
    points = points.copy()
    points["title"], points["line1"], points["line2"], points["line3"] = (
        points.municipality, points.adults_label, points.value_label, "Synthetic cohort · aggregate only")
    points["fill_color"] = [[150, 150, 150, 140] if pd.isna(v) else [int(70-30*v), int(125+55*v), int(205-40*v), 215]
                            for v in points.value]
    points["radius"] = 16
    layers = []
    if boundary:
        layers.append(pdk.Layer("GeoJsonLayer", boundary, id="boundary", filled=False,
            get_line_color=[45, 96, 155, 170], get_line_width=45, line_width_min_pixels=1, pickable=False))
    layers.append(pdk.Layer("ScatterplotLayer", points.to_dict("records"), id="municipal_summary",
        get_position="[longitude, latitude]", get_fill_color="fill_color", get_radius="radius", radius_units=pdk.types.String("pixels"),
        stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2, pickable=True))
    layers.extend(_clinic_layer(clinics))
    view = view or pdk.ViewState(latitude=float(points.latitude.mean()), longitude=float(points.longitude.mean()), zoom=9.2)
    return pdk.Deck(layers=layers, map_provider="maplibre" if style else None, map_style=style or "__MAP_STYLE__",
        initial_view_state=view,
        tooltip={"html": "<b>{title}</b><br/>{line1}<br/>{line2}<br/>{line3}"})


def municipal_positions(names, locations, cells=None):
    """A represented location near each municipality's population-weighted centre (never in a lake between cells)."""
    source = cells if cells is not None else locations
    rows = []
    for name in names:
        local = source.loc[source.municipality.eq(name)]
        if local.empty:
            local = locations.loc[locations.municipality.eq(name)]
        weights = local.adult_count if "adult_count" in local else None
        lon, lat = np.average(local.longitude, weights=weights), np.average(local.latitude, weights=weights)
        point = local.iloc[np.argmin((local.longitude-lon)**2 + (local.latitude-lat)**2)]
        rows.append(dict(municipality=name, longitude=float(point.longitude), latitude=float(point.latitude)))
    return pd.DataFrame(rows)
