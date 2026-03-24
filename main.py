"""
main.py - ISS yakin gecis dashboard ureticisi ve legacy orchestrator giris noktasi.

Kullanim:
  python main.py                   -> ISS dashboard HTML uret
  python main.py --no-browser      -> HTML uret ama tarayiciyi acma
  python main.py --orchestrator    -> Orijinal interaktif orchestrator modu
  python main.py "hedef"           -> Orijinal tek hedef modu
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Iterable, Iterator
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import plotly.graph_objects as go
from plotly.offline import plot
from sgp4.api import Satrec, SatrecArray, jday

EARTH_RADIUS_KM = 6371.0
ISS_NORAD_ID = 25544
DEFAULT_THRESHOLD_KM = 50.0
DEFAULT_STEP_MINUTES = 5
DEFAULT_HOURS = 24
DEFAULT_CHUNK_SIZE = 512
DEFAULT_TOP_PLOT_COUNT = 300
DEFAULT_OUTPUT_PATH = Path(__file__).with_name("iss_close_approach_dashboard.html")
LOCAL_TZ = ZoneInfo("Europe/Istanbul")
CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
CLASS_COLORS = {
    "active satellite": "#2f7bf6",
    "debris": "#f7c948",
    "rocket body": "#ff8b3d",
}
CLASS_LABELS = {
    "active satellite": "Aktif uydu",
    "debris": "Enkaz",
    "rocket body": "Roket govdesi",
}
FALLBACK_TLE_TEXT = """
ISS (ZARYA)
1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991
2 25544  51.6436 211.2001 0007417  17.6667  85.6398 15.50103472202482
VANGUARD 1
1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753
2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667
COSMOS 1024 DEB
1 26975U 78066F   06174.85818871  .00000620  00000-0  10000-3 0  6809
2 26975  68.4714 236.1303 5602877 123.7484 302.5767  2.05657553 67521
ARIANE 44L+ R/B
1 23177U 94040C   06175.45752052  .00000386  00000-0  76590-3 0    95
2 23177   7.0496 179.8238 7258491 296.0482  10.8191  2.25906668 99104
SL-6 R/B(2)
1 22674U 93035D   06176.55909107  .00002121  00000-0  29868-3 0  6569
2 22674  63.5035 354.4452 7541712 253.3264  18.7754  1.96679808 93877
""".strip()


@dataclass(slots=True)
class SpaceObject:
    name: str
    line1: str
    line2: str
    source: str
    object_class: str
    norad_id: int
    satrec: Satrec


@dataclass(slots=True)
class Encounter:
    space_object: SpaceObject
    min_distance_km: float
    min_time_utc: datetime
    object_positions: np.ndarray
    encounter_point: np.ndarray


def classify_object(name: str) -> str:
    upper_name = name.upper()
    if "DEBRIS" in upper_name or " DEB" in upper_name or upper_name.endswith("DEB"):
        return "debris"
    if "R/B" in upper_name or "ROCKET BODY" in upper_name:
        return "rocket body"
    return "active satellite"


def class_label(object_class: str) -> str:
    return CLASS_LABELS.get(object_class, object_class)


def looks_like_tle(payload: str) -> bool:
    if not payload or "<html" in payload.lower():
        return False
    line1_count = sum(1 for line in payload.splitlines() if line.lstrip().startswith("1 "))
    line2_count = sum(1 for line in payload.splitlines() if line.lstrip().startswith("2 "))
    return line1_count > 0 and line1_count == line2_count


def parse_tle_payload(payload: str, source: str) -> list[SpaceObject]:
    records: list[SpaceObject] = []
    lines = [line.rstrip() for line in payload.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        name = ""
        line1 = ""
        line2 = ""

        if line.startswith("1 ") and index + 1 < len(lines) and lines[index + 1].lstrip().startswith("2 "):
            line1 = line
            line2 = lines[index + 1].strip()
            index += 2
        elif (
            index + 2 < len(lines)
            and lines[index + 1].lstrip().startswith("1 ")
            and lines[index + 2].lstrip().startswith("2 ")
        ):
            name = line
            line1 = lines[index + 1].strip()
            line2 = lines[index + 2].strip()
            index += 3
        else:
            index += 1
            continue

        try:
            norad_id = int(line1[2:7])
            satrec = Satrec.twoline2rv(line1, line2)
        except (ValueError, IndexError):
            continue

        resolved_name = name or f"CAT-{norad_id}"
        records.append(
            SpaceObject(
                name=resolved_name,
                line1=line1,
                line2=line2,
                source=source,
                object_class=classify_object(resolved_name),
                norad_id=norad_id,
                satrec=satrec,
            )
        )

    return records


def dedupe_objects(records: Iterable[SpaceObject]) -> list[SpaceObject]:
    by_norad: dict[int, SpaceObject] = {}
    class_priority = {"rocket body": 3, "debris": 2, "active satellite": 1}

    for record in records:
        current = by_norad.get(record.norad_id)
        if current is None:
            by_norad[record.norad_id] = record
            continue
        if class_priority[record.object_class] > class_priority[current.object_class]:
            by_norad[record.norad_id] = record
            continue
        if len(record.name) > len(current.name):
            by_norad[record.norad_id] = record

    return list(by_norad.values())


def fetch_tle_payload(client: httpx.Client, params: dict[str, str]) -> str | None:
    try:
        response = client.get(CELESTRAK_GP_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    payload = response.text.strip()
    return payload if looks_like_tle(payload) else None


def load_fallback_catalog(reason: str) -> tuple[list[SpaceObject], dict[str, str]]:
    records = dedupe_objects(parse_tle_payload(FALLBACK_TLE_TEXT, "Yerel ornek TLE"))
    metadata = {
        "source_label": "Yerel ornek TLE",
        "source_note": reason,
    }
    return records, metadata


def load_catalog(sample_only: bool = False) -> tuple[list[SpaceObject], dict[str, str]]:
    if sample_only:
        return load_fallback_catalog("Canli baglanti kapatildi, gomulu ornek veri kullanildi.")

    headers = {"User-Agent": "ISS-Close-Approach-Dashboard/1.0"}
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
            active_payload = fetch_tle_payload(client, {"GROUP": "active", "FORMAT": "TLE"})
            debris_payload = fetch_tle_payload(client, {"NAME": "DEB", "FORMAT": "TLE"})
            rocket_payload = fetch_tle_payload(client, {"NAME": "R/B", "FORMAT": "TLE"})
    except httpx.HTTPError:
        active_payload = None
        debris_payload = None
        rocket_payload = None

    if not active_payload or not debris_payload:
        return load_fallback_catalog("CelesTrak erisilemedi, gomulu ornek veri kullanildi.")

    records: list[SpaceObject] = []
    records.extend(parse_tle_payload(active_payload, "CelesTrak aktif"))
    records.extend(parse_tle_payload(debris_payload, "CelesTrak debris/DEB"))
    if rocket_payload:
        records.extend(parse_tle_payload(rocket_payload, "CelesTrak rocket body/R-B"))

    records = dedupe_objects(records)
    iss_object = next((record for record in records if record.norad_id == ISS_NORAD_ID), None)
    if iss_object is None:
        return load_fallback_catalog("ISS TLE kaydi bulunamadi, gomulu ornek veri kullanildi.")

    note = "Kaynaklar: CelesTrak aktif + NAME=DEB + NAME=R/B"
    if rocket_payload is None:
        note = f"{note}; rocket body sorgusu bos dondu."

    return records, {"source_label": "CelesTrak canli TLE", "source_note": note}


def ceil_to_step(dt_utc: datetime, step_minutes: int) -> datetime:
    base = dt_utc.replace(second=0, microsecond=0)
    remainder = base.minute % step_minutes
    if remainder == 0 and dt_utc.second == 0 and dt_utc.microsecond == 0:
        return base
    delta_minutes = step_minutes - remainder if remainder else step_minutes
    return base + timedelta(minutes=delta_minutes)


def build_time_grid(hours: int, step_minutes: int) -> list[datetime]:
    start_utc = ceil_to_step(datetime.now(timezone.utc), step_minutes)
    total_steps = int((hours * 60) / step_minutes) + 1
    return [start_utc + timedelta(minutes=step_minutes * index) for index in range(total_steps)]


def to_julian_arrays(times_utc: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    jds = np.empty(len(times_utc), dtype=float)
    frs = np.empty(len(times_utc), dtype=float)

    for index, dt_utc in enumerate(times_utc):
        jd, fr = jday(
            dt_utc.year,
            dt_utc.month,
            dt_utc.day,
            dt_utc.hour,
            dt_utc.minute,
            dt_utc.second + (dt_utc.microsecond / 1_000_000.0),
        )
        jds[index] = jd
        frs[index] = fr

    return jds, frs


def chunked(sequence: list[SpaceObject], size: int) -> Iterator[list[SpaceObject]]:
    for start in range(0, len(sequence), size):
        yield sequence[start : start + size]


def first_valid_position(positions: np.ndarray, valid_mask: np.ndarray) -> np.ndarray | None:
    valid_indices = np.flatnonzero(valid_mask)
    if valid_indices.size == 0:
        return None
    return positions[valid_indices[0]]


def format_time_local(dt_utc: datetime) -> str:
    return dt_utc.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")


def format_distance(distance_km: float) -> str:
    return f"{distance_km:,.2f} km"


def build_earth_surface() -> go.Surface:
    u_values = np.linspace(0, 2 * np.pi, 64)
    v_values = np.linspace(0, np.pi, 32)
    u_grid, v_grid = np.meshgrid(u_values, v_values)
    x_grid = EARTH_RADIUS_KM * np.cos(u_grid) * np.sin(v_grid)
    y_grid = EARTH_RADIUS_KM * np.sin(u_grid) * np.sin(v_grid)
    z_grid = EARTH_RADIUS_KM * np.cos(v_grid)

    return go.Surface(
        x=x_grid,
        y=y_grid,
        z=z_grid,
        opacity=0.35,
        showscale=False,
        hoverinfo="skip",
        colorscale=[[0.0, "#123c8c"], [0.5, "#2f7bf6"], [1.0, "#8cc6ff"]],
        name="Dunya",
    )


def analyze_catalog(
    records: list[SpaceObject],
    times_utc: list[datetime],
    threshold_km: float,
    chunk_size: int,
) -> dict[str, object]:
    iss_object = next((record for record in records if record.norad_id == ISS_NORAD_ID), None)
    if iss_object is None:
        raise RuntimeError("ISS TLE kaydi bulunamadi.")

    jds, frs = to_julian_arrays(times_utc)
    iss_errors, iss_positions, _ = iss_object.satrec.sgp4_array(jds, frs)
    iss_errors = np.asarray(iss_errors)
    iss_positions = np.asarray(iss_positions, dtype=float)
    iss_valid_mask = iss_errors == 0
    if not np.any(iss_valid_mask):
        raise RuntimeError("ISS yorlugu propagasyonu basarisiz oldu.")

    candidates = [record for record in records if record.norad_id != ISS_NORAD_ID]
    all_marker_positions: dict[str, list[np.ndarray]] = {key: [] for key in CLASS_COLORS}
    summary_rows: list[dict[str, object]] = []
    critical_encounters: list[Encounter] = []

    for batch in chunked(candidates, chunk_size):
        sat_array = SatrecArray([record.satrec for record in batch])
        errors, positions, _ = sat_array.sgp4(jds, frs)
        errors = np.asarray(errors)
        positions = np.asarray(positions, dtype=float)
        valid_mask = errors == 0

        deltas = positions - iss_positions[np.newaxis, :, :]
        distances = np.linalg.norm(deltas, axis=2)
        distances[~valid_mask] = np.inf
        distances[:, ~iss_valid_mask] = np.inf

        minimum_indices = np.argmin(distances, axis=1)
        minimum_distances = distances[np.arange(len(batch)), minimum_indices]

        for index, record in enumerate(batch):
            current_position = first_valid_position(positions[index], valid_mask[index])
            if current_position is not None:
                all_marker_positions[record.object_class].append(current_position)

            if not np.isfinite(minimum_distances[index]):
                continue

            min_idx = int(minimum_indices[index])
            min_distance = float(minimum_distances[index])
            min_time_utc = times_utc[min_idx]
            summary_rows.append(
                {
                    "name": record.name,
                    "norad_id": record.norad_id,
                    "class": record.object_class,
                    "min_distance_km": min_distance,
                    "min_time_utc": min_time_utc,
                    "current_position": current_position,
                }
            )

            if min_distance < threshold_km:
                encounter_point = (positions[index, min_idx] + iss_positions[min_idx]) / 2.0
                critical_encounters.append(
                    Encounter(
                        space_object=record,
                        min_distance_km=min_distance,
                        min_time_utc=min_time_utc,
                        object_positions=positions[index],
                        encounter_point=encounter_point,
                    )
                )

    summary_rows.sort(key=lambda row: row["min_distance_km"])
    critical_encounters.sort(key=lambda encounter: encounter.min_distance_km)

    return {
        "iss_object": iss_object,
        "iss_positions": iss_positions,
        "summary_rows": summary_rows,
        "critical_encounters": critical_encounters,
        "all_marker_positions": all_marker_positions,
        "times_utc": times_utc,
    }


def build_sidebar_html(
    total_tracked: int,
    critical_count: int,
    top_risks: list[dict[str, object]],
    generated_at_utc: datetime,
    source_label: str,
    source_note: str,
    hours: int,
    step_minutes: int,
    threshold_km: float,
) -> str:
    rows = []
    for row in top_risks:
        rows.append(
            "<tr>"
            f"<td>{escape(str(row['name']))}</td>"
            f"<td>{row['min_distance_km']:.2f}</td>"
            f"<td>{escape(format_time_local(row['min_time_utc']))}</td>"
            f"<td>{escape(class_label(str(row['class'])))}</td>"
            "</tr>"
        )

    table_body = "".join(rows) if rows else "<tr><td colspan='4'>Veri yok</td></tr>"
    generated_label = generated_at_utc.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

    return f"""
    <aside class="sidebar">
      <div class="panel">
        <div class="eyebrow">ISS yakin gecis analizi</div>
        <h1>24 saatlik uzay nesnesi riski</h1>
        <p class="muted">{escape(source_label)}</p>
        <p class="note">{escape(source_note)}</p>
      </div>
      <div class="stats">
        <div class="stat-card">
          <span>Toplam takip edilen nesne</span>
          <strong>{total_tracked:,}</strong>
        </div>
        <div class="stat-card danger">
          <span>Kritik yaklasma sayisi</span>
          <strong>{critical_count:,}</strong>
          <small>{threshold_km:.0f} km alti</small>
        </div>
        <div class="stat-card">
          <span>Analiz penceresi</span>
          <strong>{hours} saat</strong>
          <small>{step_minutes} dk adim</small>
        </div>
        <div class="stat-card">
          <span>Son guncelleme</span>
          <strong>{generated_label}</strong>
        </div>
      </div>
      <div class="panel table-panel">
        <h2>En tehlikeli 10 nesne</h2>
        <table>
          <thead>
            <tr>
              <th>Nesne</th>
              <th>Mesafe</th>
              <th>Zaman</th>
              <th>Sinif</th>
            </tr>
          </thead>
          <tbody>{table_body}</tbody>
        </table>
      </div>
    </aside>
    """


def build_dashboard_html(
    records: list[SpaceObject],
    analysis: dict[str, object],
    source_label: str,
    source_note: str,
    hours: int,
    step_minutes: int,
    threshold_km: float,
    top_plot_count: int,
) -> str:
    iss_positions = analysis["iss_positions"]
    summary_rows: list[dict[str, object]] = analysis["summary_rows"]
    critical_encounters: list[Encounter] = analysis["critical_encounters"]
    all_marker_positions: dict[str, list[np.ndarray]] = analysis["all_marker_positions"]

    generated_at_utc = datetime.now(timezone.utc)
    top_risks = summary_rows[:10]
    hover_rows = summary_rows[:top_plot_count]

    figure = go.Figure()
    figure.add_trace(build_earth_surface())
    figure.add_trace(
        go.Scatter3d(
            x=iss_positions[:, 0],
            y=iss_positions[:, 1],
            z=iss_positions[:, 2],
            mode="lines",
            line={"color": "#ff3b30", "width": 8},
            name="ISS yorlugu",
            hovertemplate="ISS (ZARYA)<extra></extra>",
        )
    )

    for object_class, positions in all_marker_positions.items():
        if not positions:
            continue
        points = np.asarray(positions, dtype=float)
        figure.add_trace(
            go.Scatter3d(
                x=points[:, 0],
                y=points[:, 1],
                z=points[:, 2],
                mode="markers",
                marker={"size": 2, "opacity": 0.18, "color": CLASS_COLORS[object_class]},
                name=f"{class_label(object_class)} (tum katalog)",
                hoverinfo="skip",
            )
        )

    hover_groups: dict[str, list[dict[str, object]]] = {key: [] for key in CLASS_COLORS}
    for row in hover_rows:
        if row["current_position"] is None:
            continue
        hover_groups[str(row["class"])].append(row)

    for object_class, rows in hover_groups.items():
        if not rows:
            continue
        coords = np.asarray([row["current_position"] for row in rows], dtype=float)
        customdata = np.asarray(
            [
                [
                    row["name"],
                    str(row["norad_id"]),
                    class_label(object_class),
                    format_distance(float(row["min_distance_km"])),
                    format_time_local(row["min_time_utc"]),
                ]
                for row in rows
            ],
            dtype=object,
        )
        figure.add_trace(
            go.Scatter3d(
                x=coords[:, 0],
                y=coords[:, 1],
                z=coords[:, 2],
                mode="markers",
                marker={"size": 4, "opacity": 0.9, "color": CLASS_COLORS[object_class]},
                name=f"{class_label(object_class)} (risk katmani)",
                customdata=customdata,
                hovertemplate=(
                    "%{customdata[0]}<br>"
                    "NORAD ID: %{customdata[1]}<br>"
                    "Sinif: %{customdata[2]}<br>"
                    "Minimum mesafe: %{customdata[3]}<br>"
                    "Yaklasma zamani: %{customdata[4]}<extra></extra>"
                ),
            )
        )

    for encounter in critical_encounters:
        repeated_customdata = np.asarray(
            [
                [
                    encounter.space_object.name,
                    str(encounter.space_object.norad_id),
                    class_label(encounter.space_object.object_class),
                    format_distance(encounter.min_distance_km),
                    format_time_local(encounter.min_time_utc),
                ]
            ]
            * len(encounter.object_positions),
            dtype=object,
        )
        figure.add_trace(
            go.Scatter3d(
                x=encounter.object_positions[:, 0],
                y=encounter.object_positions[:, 1],
                z=encounter.object_positions[:, 2],
                mode="lines",
                line={"color": CLASS_COLORS[encounter.space_object.object_class], "width": 5},
                name=f"{encounter.space_object.name} yorlugu",
                customdata=repeated_customdata,
                showlegend=False,
                hovertemplate=(
                    "%{customdata[0]}<br>"
                    "NORAD ID: %{customdata[1]}<br>"
                    "Sinif: %{customdata[2]}<br>"
                    "Minimum mesafe: %{customdata[3]}<br>"
                    "Yaklasma zamani: %{customdata[4]}<extra></extra>"
                ),
            )
        )

    if critical_encounters:
        encounter_customdata = np.asarray(
            [
                [
                    encounter.space_object.name,
                    str(encounter.space_object.norad_id),
                    class_label(encounter.space_object.object_class),
                    format_distance(encounter.min_distance_km),
                    format_time_local(encounter.min_time_utc),
                ]
                for encounter in critical_encounters
            ],
            dtype=object,
        )
        figure.add_trace(
            go.Scatter3d(
                x=[encounter.encounter_point[0] for encounter in critical_encounters],
                y=[encounter.encounter_point[1] for encounter in critical_encounters],
                z=[encounter.encounter_point[2] for encounter in critical_encounters],
                mode="markers+text",
                marker={"size": 9, "color": "#ff3b30", "symbol": "diamond"},
                text=[f"UYARI {encounter.min_distance_km:.1f} km" for encounter in critical_encounters],
                textposition="top center",
                name="Kritik yakin gecisler",
                customdata=encounter_customdata,
                hovertemplate=(
                    "%{customdata[0]}<br>"
                    "NORAD ID: %{customdata[1]}<br>"
                    "Sinif: %{customdata[2]}<br>"
                    "Minimum mesafe: %{customdata[3]}<br>"
                    "Yaklasma zamani: %{customdata[4]}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title={
            "text": (
                "ISS 24 Saatlik Yakin Gecis Dashboard'u"
                f"<br><sup>{escape(source_label)} | {len(records):,} nesne tarandi</sup>"
            ),
            "x": 0.5,
        },
        paper_bgcolor="#04101d",
        plot_bgcolor="#04101d",
        font={"color": "#edf4ff"},
        margin={"l": 0, "r": 0, "t": 70, "b": 0},
        scene={
            "xaxis": {"visible": False, "showbackground": False},
            "yaxis": {"visible": False, "showbackground": False},
            "zaxis": {"visible": False, "showbackground": False},
            "aspectmode": "data",
            "bgcolor": "#04101d",
            "camera": {"eye": {"x": 1.7, "y": 1.35, "z": 0.9}},
        },
        legend={"orientation": "h", "y": 1.02, "x": 0.02, "bgcolor": "rgba(0,0,0,0)"},
        hoverlabel={"bgcolor": "#061a2f", "font": {"color": "#edf4ff"}},
    )

    plot_div = plot(
        figure,
        output_type="div",
        include_plotlyjs="inline",
        config={"responsive": True, "displaylogo": False},
    )

    sidebar_html = build_sidebar_html(
        total_tracked=len(records),
        critical_count=len(critical_encounters),
        top_risks=top_risks,
        generated_at_utc=generated_at_utc,
        source_label=source_label,
        source_note=source_note,
        hours=hours,
        step_minutes=step_minutes,
        threshold_km=threshold_km,
    )

    return f"""<!DOCTYPE html>
<html lang="tr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ISS Yakin Gecis Dashboard'u</title>
    <style>
      :root {{
        --bg: #020916;
        --panel: #0c1b2d;
        --panel-border: rgba(149, 188, 255, 0.18);
        --text: #edf4ff;
        --muted: #9fb4d6;
        --danger: #ff6b5b;
        --accent: #64c1ff;
      }}
      * {{
        box-sizing: border-box;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top left, rgba(100, 193, 255, 0.16), transparent 28%),
          radial-gradient(circle at bottom right, rgba(255, 107, 91, 0.14), transparent 22%),
          var(--bg);
        color: var(--text);
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      }}
      .layout {{
        display: flex;
        min-height: 100vh;
      }}
      .sidebar {{
        width: 380px;
        padding: 24px;
        background: rgba(6, 17, 31, 0.94);
        border-right: 1px solid var(--panel-border);
        overflow-y: auto;
      }}
      .content {{
        flex: 1;
        min-width: 0;
        padding: 14px;
      }}
      .panel {{
        background: linear-gradient(180deg, rgba(17, 35, 58, 0.96), rgba(9, 20, 36, 0.96));
        border: 1px solid var(--panel-border);
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 18px;
        box-shadow: 0 20px 45px rgba(0, 0, 0, 0.2);
      }}
      .eyebrow {{
        display: inline-flex;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(100, 193, 255, 0.12);
        color: var(--accent);
        font-size: 12px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      h1, h2 {{
        margin: 12px 0 10px;
      }}
      h1 {{
        font-size: 28px;
        line-height: 1.1;
      }}
      h2 {{
        font-size: 18px;
      }}
      .muted, .note {{
        color: var(--muted);
        line-height: 1.5;
      }}
      .stats {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
        margin-bottom: 18px;
      }}
      .stat-card {{
        background: rgba(13, 27, 44, 0.96);
        border: 1px solid rgba(149, 188, 255, 0.14);
        border-radius: 16px;
        padding: 16px;
      }}
      .stat-card span, .stat-card small {{
        display: block;
        color: var(--muted);
      }}
      .stat-card strong {{
        display: block;
        margin-top: 6px;
        font-size: 24px;
        line-height: 1.2;
      }}
      .stat-card.danger strong {{
        color: var(--danger);
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      th, td {{
        text-align: left;
        padding: 10px 8px;
        border-bottom: 1px solid rgba(149, 188, 255, 0.12);
        font-size: 13px;
        vertical-align: top;
      }}
      th {{
        color: var(--muted);
        font-weight: 600;
      }}
      .plot-frame {{
        height: calc(100vh - 28px);
        border-radius: 24px;
        overflow: hidden;
        border: 1px solid rgba(149, 188, 255, 0.12);
        background: rgba(4, 16, 29, 0.85);
      }}
      .plot-frame > div {{
        height: 100%;
      }}
      @media (max-width: 1180px) {{
        .layout {{
          flex-direction: column;
        }}
        .sidebar {{
          width: 100%;
          border-right: 0;
          border-bottom: 1px solid var(--panel-border);
        }}
        .plot-frame {{
          height: 72vh;
        }}
      }}
      @media (max-width: 720px) {{
        .sidebar {{
          padding: 18px;
        }}
        .content {{
          padding: 10px;
        }}
        h1 {{
          font-size: 24px;
        }}
        .plot-frame {{
          height: 64vh;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="layout">
      {sidebar_html}
      <main class="content">
        <section class="plot-frame">{plot_div}</section>
      </main>
    </div>
  </body>
</html>
"""


def generate_dashboard(
    output_path: Path,
    hours: int,
    step_minutes: int,
    threshold_km: float,
    sample_only: bool,
    no_browser: bool,
    top_plot_count: int,
) -> int:
    if hours <= 0:
        raise ValueError("--hours sifirdan buyuk olmali.")
    if step_minutes <= 0:
        raise ValueError("--step-minutes sifirdan buyuk olmali.")
    if threshold_km <= 0:
        raise ValueError("--threshold-km sifirdan buyuk olmali.")

    records, metadata = load_catalog(sample_only=sample_only)
    times_utc = build_time_grid(hours=hours, step_minutes=step_minutes)
    analysis = analyze_catalog(
        records=records,
        times_utc=times_utc,
        threshold_km=threshold_km,
        chunk_size=DEFAULT_CHUNK_SIZE,
    )
    html_content = build_dashboard_html(
        records=records,
        analysis=analysis,
        source_label=metadata["source_label"],
        source_note=metadata["source_note"],
        hours=hours,
        step_minutes=step_minutes,
        threshold_km=threshold_km,
        top_plot_count=top_plot_count,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")

    critical_count = len(analysis["critical_encounters"])
    print(f"HTML dosyasi olusturuldu: {output_path.resolve()}")
    print(f"Kaynak: {metadata['source_label']}")
    print(f"Not: {metadata['source_note']}")
    print(f"Toplam nesne: {len(records):,}")
    print(f"Kritik yakin gecis (< {threshold_km:.0f} km): {critical_count:,}")

    if not no_browser:
        try:
            webbrowser.open(output_path.resolve().as_uri(), new=2)
        except Exception as exc:
            print(f"Tarayici otomatik acilamadi: {exc}")

    return 0


def prepare_legacy_environment() -> None:
    sys.path.insert(0, os.path.dirname(__file__))
    from dotenv import load_dotenv

    load_dotenv()


def check_api_key() -> bool:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        print("\nWARNING: OPENROUTER_API_KEY tanimli degil.\n")
        return False
    return True


def build_legacy_agents() -> dict[str, object]:
    from core.message_bus import bus
    from agents.planner_agent import PlannerAgent
    from agents.researcher_agent import ResearcherAgent
    from agents.coder_agent import CoderAgent
    from agents.critic_agent import CriticAgent
    from agents.executor_agent import ExecutorAgent

    return {
        "planner": PlannerAgent(bus=bus),
        "researcher": ResearcherAgent(bus=bus),
        "coder": CoderAgent(bus=bus),
        "critic": CriticAgent(bus=bus),
        "executor": ExecutorAgent(bus=bus),
    }


async def run_legacy_interactive() -> None:
    from core.orchestrator import Orchestrator
    from ui.cli import AgentCLI

    cli = AgentCLI()
    agents = build_legacy_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator
    await cli.run_interactive()


async def run_legacy_single_goal(goal: str) -> None:
    from core.orchestrator import Orchestrator
    from ui.cli import AgentCLI, print_banner

    cli = AgentCLI()
    agents = build_legacy_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator
    print_banner()
    await cli.run_goal(goal)


async def run_legacy_demo() -> None:
    from ui.cli import run_demo as legacy_run_demo

    await legacy_run_demo()


async def run_legacy_profile() -> None:
    from rich.console import Console
    from agents.profiler_agent import ProfilerAgent

    console = Console()
    console.print("[bold cyan]\nProfil Analisti baslatiliyor...\n[/bold cyan]")
    profiler = ProfilerAgent()
    path = await profiler.generate_profile()
    if path:
        console.print(f"[bold green]Profil kaydedildi:[/bold green] {path}")
    else:
        console.print("[bold red]Profil olusturulamadi.[/bold red]")


def run_legacy_mode(args: argparse.Namespace) -> int:
    prepare_legacy_environment()

    if not args.no_key_check and not args.demo:
        check_api_key()

    if args.demo:
        asyncio.run(run_legacy_demo())
    elif args.profile:
        asyncio.run(run_legacy_profile())
    elif args.goal:
        asyncio.run(run_legacy_single_goal(args.goal))
    else:
        asyncio.run(run_legacy_interactive())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ISS yakin gecis dashboard ureticisi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler:
  python main.py
  python main.py --sample-only --no-browser
  python main.py --orchestrator
  python main.py "Summarize the latest AI news"
        """,
    )
    parser.add_argument("goal", nargs="?", help="Legacy orchestrator icin opsiyonel hedef")
    parser.add_argument("--orchestrator", action="store_true", help="Eski interaktif orchestrator modunu ac")
    parser.add_argument("--demo", action="store_true", help="Legacy demo modunu calistir")
    parser.add_argument("--profile", action="store_true", help="Legacy profil modunu calistir")
    parser.add_argument("--no-key-check", action="store_true", help="Legacy API key kontrolunu atla")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Olusturulacak HTML dosyasi")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="Propagasyon suresi (saat)")
    parser.add_argument(
        "--step-minutes",
        type=int,
        default=DEFAULT_STEP_MINUTES,
        help="Propagasyon adimi (dakika)",
    )
    parser.add_argument(
        "--threshold-km",
        type=float,
        default=DEFAULT_THRESHOLD_KM,
        help="Kritik yakin gecis esigi (km)",
    )
    parser.add_argument(
        "--top-plot-count",
        type=int,
        default=DEFAULT_TOP_PLOT_COUNT,
        help="Hover ile detay gosterilecek en riskli nesne sayisi",
    )
    parser.add_argument(
        "--sample-only",
        action="store_true",
        help="CelesTrak yerine gomulu ornek TLE veri setini kullan",
    )
    parser.add_argument("--no-browser", action="store_true", help="HTML uret ama tarayiciyi acma")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    legacy_requested = args.orchestrator or args.demo or args.profile or bool(args.goal)

    if legacy_requested:
        return run_legacy_mode(args)

    output_path = Path(args.output)
    return generate_dashboard(
        output_path=output_path,
        hours=args.hours,
        step_minutes=args.step_minutes,
        threshold_km=args.threshold_km,
        sample_only=args.sample_only,
        no_browser=args.no_browser,
        top_plot_count=max(10, args.top_plot_count),
    )


if __name__ == "__main__":
    raise SystemExit(main())
