"""CSV and PDF export of an analysis result (bonus feature).

CSV uses the stdlib only. PDF uses reportlab if available; if it's not
installed the endpoint degrades to a clear error rather than crashing the app.
"""
from __future__ import annotations

import csv
import io


def to_csv(response: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["Climate Hazard Trend Analyzer — export"])
    writer.writerow(["region", response.get("region_name") or ""])
    writer.writerow(["lat", response["lat"], "lon", response["lon"]])
    writer.writerow(["hazard", response["hazard"]])
    writer.writerow(["threshold", response["threshold"], response["threshold_unit"]])
    writer.writerow(["definition", response["hazard_definition"]])
    writer.writerow(["baseline", response["baseline"]])
    writer.writerow(["insight", response["insight"]])
    writer.writerow([])

    writer.writerow([
        "year", "events", "hazard_days",
        "mean_duration", "max_intensity", "rolling_mean", "coverage",
    ])
    for p in response["series"]:
        writer.writerow([
            p["year"], p["events"], p["hazard_days"],
            p["mean_duration"], p["max_intensity"],
            p["rolling_mean"], p["coverage"],
        ])

    writer.writerow([])
    t = response["trend"]
    writer.writerow(["trend.slope_per_year", t["slope_per_year"]])
    writer.writerow(["trend.percent_change", t["percent_change"]])
    writer.writerow(["trend.r_squared", t["r_squared"]])
    writer.writerow(["trend.p_value", t["p_value"]])
    writer.writerow(["trend.mann_kendall_trend", t["mann_kendall_trend"]])
    writer.writerow(["trend.mann_kendall_p", t["mann_kendall_p"]])
    writer.writerow(["trend.significant", t["significant"]])
    return buf.getvalue()


def to_pdf(response: dict) -> bytes:
    """Render a compact one-page PDF report. Requires reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError("PDF export requires the 'reportlab' package") from exc

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Climate Hazard Report")
    styles = getSampleStyleSheet()
    elements = []

    title = response.get("region_name") or f"{response['lat']}, {response['lon']}"
    elements.append(Paragraph(f"Climate Hazard Trend Report — {title}", styles["Title"]))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(response["insight"], styles["Normal"]))
    elements.append(Spacer(1, 0.3 * cm))
    meta = (
        f"Hazard: {response['hazard']} &nbsp;|&nbsp; "
        f"Threshold: {response['threshold']} {response['threshold_unit']} &nbsp;|&nbsp; "
        f"Baseline: {response['baseline']}"
    )
    elements.append(Paragraph(meta, styles["Normal"]))
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph(f"<i>{response['hazard_definition']}</i>", styles["Normal"]))
    elements.append(Spacer(1, 0.5 * cm))

    data = [["Year", "Events", "Days", "Mean dur.", "Max intensity", "Coverage"]]
    for p in response["series"]:
        data.append([
            p["year"], p["events"], p["hazard_days"],
            p["mean_duration"],
            "" if p["max_intensity"] is None else p["max_intensity"],
            f"{p['coverage']:.0%}",
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6f54")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef5f2")]),
    ]))
    elements.append(table)
    doc.build(elements)
    return buf.getvalue()
