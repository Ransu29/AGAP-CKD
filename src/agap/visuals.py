"""Local explanation and simulation figures with explicit units and provenance."""
from __future__ import annotations

from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from agap.climate_demo import model_contributions


def chips_html(chips):
    """Escape both report text and category names before rendering local badges."""
    badges = "".join(f'<span class="agap-chip agap-chip-{escape(category, quote=True)}">{escape(text)}</span>'
                     for category, text in chips)
    return '<div class="agap-chips">' + badges + '</div>'


def resident_model_shift_html(person, count, decisions=None, plan_state="unplanned", active_model="climate"):
    """Compare saved-date scores and actual paired invitations, never infer a slot from rank."""
    row = None
    if decisions is not None:
        selected = decisions.loc[decisions.resident_id.eq(person.resident_id)]
        if len(selected) == 1:
            row = selected.iloc[0]
    if row is None:
        title = "Invitations not planned" if plan_state == "unplanned" else "Invitation comparison unavailable"
        detail = "Prepare a screening plan to compare invitations at the same budget." if plan_state == "unplanned" else "No paired invitation decisions are available for the current settings."
        kind = "pending"
    elif row.clinical_invited == row.climate_invited:
        title, kind = "Invitation unchanged", "unchanged"
        detail = "Invited by both models." if row.climate_invited else "Not invited by either model."
    else:
        kind = "added" if row.climate_invited else "removed"
        title = f"Invitation {kind} with climate"
        detail = "The two fitted models assign this resident a different invitation under the same plan settings."
    cards = []
    for variant, label in (("clinical", "Questionnaire only"), ("climate", "Questionnaire + climate")):
        invited = "Not planned" if row is None and plan_state == "unplanned" else "Unavailable" if row is None else "Invited" if row[f"{variant}_invited"] else "Not invited"
        active = variant == active_model
        cards.append(f'<div class="agap-model-cell{" is-active" if active else ""}" data-model="{variant}">'
            f'<div class="agap-model-label">{label}<span>{"ACTIVE PLAN" if active else "COMPARISON"}</span></div>'
            f'<div class="agap-model-value">{person[f"{variant}_score"]:.1%}<small>model score</small></div>'
            f'<div class="agap-model-position">Priority <b>#{int(person[f"{variant}_rank"]):,}</b> of {count:,}'
            f'<span>{invited}</span></div></div>')
    return ('<section class="agap-model-shift" aria-label="Resident model and invitation comparison">'
            + cards[0] + '<div class="agap-model-arrow" aria-hidden="true">→</div>' + cards[1]
            + f'<div class="agap-model-verdict agap-verdict-{kind}"><span class="agap-eyebrow">INVITATION CONSEQUENCE</span>'
            f'<strong>{escape(title)}</strong><p>{escape(detail)}</p></div></section>')


def weather_timeline_figure(window, cutoff, days=30):
    """One shared local-day axis; screening-day weather is deliberately absent.

    Validate the displayed window instead of connecting gaps or presenting
    partial observations as a complete exposure window.
    """
    cutoff = pd.Timestamp(cutoff).normalize()
    dates = pd.to_datetime(window.local_date).dt.normalize()
    expected = pd.date_range(cutoff-pd.Timedelta(days=days), periods=days)
    if len(window) != days or dates.duplicated().any() or set(dates) != set(expected):
        raise ValueError(f"The timeline requires {days} complete local days before screening.")
    values = window[["tmean_c", "tmax_c", "precip_mm"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, 2] < 0).any():
        raise ValueError("The timeline requires complete temperature and rainfall observations.")
    ordered = window.assign(local_date=dates).sort_values("local_date")
    figure = go.Figure(layout=dict(grid=dict(rows=2, columns=1, pattern="coupled", roworder="top to bottom")))
    for name, column, color, dash in (("Daily maximum", "tmax_c", "#bb721b", "solid"),
                                       ("Daily mean", "tmean_c", "#506e71", "dot")):
        figure.add_trace(go.Scatter(x=ordered.local_date, y=ordered[column], xaxis="x", yaxis="y",
            mode="lines", name=name, line=dict(color=color, width=2.6, dash=dash),
            hovertemplate="%{y:.1f} °C<extra>%{fullData.name}</extra>"))
    figure.add_trace(go.Bar(x=ordered.local_date, y=ordered.precip_mm, xaxis="x", yaxis="y2",
        name="Daily rainfall", marker_color="#3586ad", marker_line_width=0,
        hovertemplate="%{y:.1f} mm<extra>Daily rainfall</extra>"))
    # Both panels use the same x axis, so hover and zoom genuinely stay aligned.
    figure.update_layout(height=315, template="plotly_white", hovermode="x unified", hoversubplots="axis",
        margin=dict(l=48, r=24, t=32, b=48), bargap=.25,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color="#425d61", size=12),
        legend=dict(orientation="h", x=0, y=1.18, font_size=11),
        xaxis=dict(title="Local date · Asia/Manila", type="date", anchor="y2", domain=[0, 1],
            range=[expected[0]-pd.Timedelta(hours=12), cutoff+pd.Timedelta(days=1)],
            tickformat="%d %b", showgrid=False, zeroline=False,
            unifiedhovertitle=dict(text="%{x|%d %b %Y}")),
        yaxis=dict(title="Temperature (°C)", domain=[.43, 1], gridcolor="#e6eeec", zeroline=False),
        yaxis2=dict(title="Rainfall (mm)", domain=[0, .28], rangemode="tozero", gridcolor="#e6eeec", zeroline=False),
        shapes=[dict(type="line", x0=cutoff, x1=cutoff, xref="x", y0=0, y1=1, yref="paper",
            line=dict(color="#547674", width=1.4, dash="dash"))],
        annotations=[dict(x=cutoff, y=1.04, xref="x", yref="paper", text="Screening", showarrow=False,
            xanchor="right", font=dict(size=11, color="#365b59"))])
    return figure


def contributions_figure(model, person):
    terms = model_contributions(model, person).sort_values("contribution")
    intercept = terms.attrs["intercept"]
    total = float(intercept + terms.contribution.sum())
    labels = ["Intercept (reference)", *terms.input, "Total log-odds"]
    detail = ["Fitted model intercept", *["Includes missing-answer term" if value else "Reported/known input term"
                                          for value in terms.missing], "Intercept + all input terms"]
    figure = go.Figure(go.Waterfall(
        orientation="h", y=labels, x=[intercept, *terms.contribution, total],
        measure=["absolute", *["relative"] * len(terms), "total"], customdata=detail,
        increasing=dict(marker_color="#b86b46"), decreasing=dict(marker_color="#37816c"),
        totals=dict(marker_color="#3168c6"), connector=dict(line=dict(color="#c5ced9", width=1)),
        hovertemplate="%{y}<br>%{x:+.3f} log-odds<br>%{customdata}<extra></extra>"))
    figure.update_layout(height=285, margin=dict(l=0, r=8, t=12, b=30), template="plotly_white",
                         xaxis_title="Fitted model log-odds", yaxis=dict(autorange="reversed"),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    return figure


def visibility_gap_figure(monthly, area, month):
    """Two parts of the same hidden-positive count, never external validation."""
    row = monthly.loc[monthly.municipality.eq(area) & pd.to_datetime(monthly.month).eq(pd.Timestamp(month))]
    if row.empty:
        return None
    if len(row) != 1:
        raise ValueError("A visibility-gap view requires one row per area/month.")
    observed, undetected, total = (float(row.iloc[0][name]) for name in
                                  ("observed_abnormal", "hidden_undetected_abnormal", "hidden_abnormal"))
    if not np.isfinite([observed, undetected, total]).all() or min(observed, undetected, total) < 0:
        raise ValueError("Visibility-gap counts must be finite and nonnegative.")
    if observed + undetected != total:
        raise ValueError("Observed and undetected flags must partition hidden abnormal flags.")
    figure = go.Figure()
    for label, value, color in (("Observed abnormal flags", observed, "#3168c6"),
                                ("Undetected abnormal flags (simulator truth)", undetected, "#bd8046")):
        figure.add_bar(x=[value], y=[area], orientation="h", name=label, marker_color=color,
                      text=[f"{int(value):,}"], textposition="inside",
                      customdata=[[int(row.iloc[0].sampled_adults), int(row.iloc[0].tested)]],
                      hovertemplate=label + ": %{x:.0f}<br>%{customdata[0]} sampled · %{customdata[1]} tested<extra></extra>")
    if total == 0:
        figure.add_annotation(text="No abnormal flags in this sampled group/month", x=.5, y=.5,
                              xref="paper", yref="paper", showarrow=False)
    figure.update_layout(barmode="stack", height=240, template="plotly_white", margin=dict(l=0, r=10, t=12, b=50),
                         xaxis=dict(title="Abnormal flags in sampled synthetic adults (count)", rangemode="tozero", dtick=1 if total < 10 else None),
                         yaxis_title="Area", legend=dict(orientation="h", y=-.65, traceorder="normal"),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return figure
