#!/usr/bin/env python3
"""
Interactive maps for Queimadas RMC using Folium.
Generates HTML map strings for embedding in FastAPI responses.
"""

import json
import math
import tempfile
import uuid
from pathlib import Path

import folium
import folium.plugins as plugins
import folium.template
import folium.utilities
import numpy as np
import pandas as pd

# Monkeypatch Folium bug: camelize crashes on non-string keys in GeoJSON kwargs
_orig_camelize = folium.utilities.camelize
def _safe_camelize(key):
    if not isinstance(key, str):
        key = str(key)
    return _orig_camelize(key)
folium.utilities.camelize = _safe_camelize
folium.template.camelize = _safe_camelize

GEOJSON_PATH = Path("RMC_Municipios_2024.geojson")
CSV_PATH = Path("resultados/todos_focos_rmc.csv")

RMC_CENTER = [-22.83, -47.15]
DEFAULT_ZOOM = 11


def load_data():
    return pd.read_csv(CSV_PATH, parse_dates=["data_pas"])


def load_geojson():
    with open(GEOJSON_PATH) as f:
        return json.load(f)


def _sanitize_geojson(gj):
    for feat in gj.get("features", []):
        for k, v in list(feat.get("properties", {}).items()):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                feat["properties"][k] = ""
            elif not isinstance(v, str):
                feat["properties"][k] = str(v)
    return gj


def _filter(df, anos=None, municipios=None):
    out = df.copy()
    if anos:
        if anos[0] is not None:
            out = out[out["ano"] >= anos[0]]
        if anos[1] is not None:
            out = out[out["ano"] <= anos[1]]
    if municipios:
        out = out[out["NM_MUN"].isin(municipios)]
    return out


def _full_map_html(m, extra_js=""):
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        m.save(f.name)
        html = Path(f.name).read_text()
    Path(f.name).unlink()
    if extra_js:
        html = html.replace("</body>", extra_js + "\n</body>")
    return html


def make_fires_map(df, anos=None, municipios=None, tile="CartoDB dark_matter"):
    filtered = _filter(df, anos, municipios)
    m = folium.Map(location=RMC_CENTER, zoom_start=DEFAULT_ZOOM, tiles=tile, control_scale=True)

    # --- Choropleth as raw Leaflet JS (avoids Folium GeoJson NaN bug) ---
    geojson = _sanitize_geojson(load_geojson())
    freq = filtered.groupby("NM_MUN").size().reset_index(name="total_focos")
    all_muns = [f["properties"]["NM_MUN"] for f in geojson["features"]]
    freq_full = pd.DataFrame({"NM_MUN": all_muns}).merge(freq, on="NM_MUN", how="left").fillna(0)
    freq_full["total_focos"] = freq_full["total_focos"].astype(int)
    freq_dict = dict(zip(freq_full["NM_MUN"], freq_full["total_focos"]))
    max_fc = max(freq_full["total_focos"].max(), 1)

    # Write GeoJSON + freq data as JS variables, inject into map
    geojson_id = f"gj_{uuid.uuid4().hex[:8]}"
    data_json = json.dumps(geojson, default=str)
    freq_json = json.dumps(freq_dict)

    js_code = f"""
    <script>
    (function() {{
        var geojsonData = {data_json};
        var freqData = {freq_json};
        var maxFc = {max_fc};

        function getColor(count) {{
            var t = count / maxFc;
            var r = Math.round(255 * t + 255 * (1-t));
            var g = Math.round(200 * (1-t) + 100 * t);
            var b = Math.round(220 * (1-t) + 0 * t);
            return 'rgb(' + r + ',' + g + ',' + b + ')';
        }}

        var choropleth = L.geoJSON(geojsonData, {{
            style: function(feature) {{
                var name = feature.properties.NM_MUN;
                var count = freqData[name] || 0;
                return {{
                    fillColor: getColor(count),
                    weight: 1,
                    opacity: 0.7,
                    color: '#555',
                    fillOpacity: count > 0 ? 0.45 : 0.1
                }};
            }},
            onEachFeature: function(feature, layer) {{
                var name = feature.properties.NM_MUN;
                var count = freqData[name] || 0;
                layer.bindTooltip('<b>' + name + '</b><br>Focos: ' + count);
            }}
        }}).addTo(window._folium_map_{m._id});
    }})();
    </script>
    """

    # --- Heatmap layer ---
    heat_data = filtered[["latitude", "longitude"]].dropna().values.tolist()
    if heat_data:
        plugins.HeatMap(
            heat_data, name="Heatmap",
            min_opacity=0.3, max_zoom=15, radius=12, blur=10,
            gradient={0.2: "blue", 0.4: "lime", 0.6: "yellow", 0.8: "orange", 1: "red"},
        ).add_to(m)

    # --- Clustered markers ---
    cluster = plugins.MarkerCluster(name="Focos (agrupados)", show=False)
    for _, row in filtered.iterrows():
        lat, lon = row.get("latitude"), row.get("longitude")
        if pd.isna(lat) or pd.isna(lon):
            continue
        frp = row.get("frp")
        frp_str = f"{frp:.1f}" if pd.notna(frp) else "N/A"
        date_str = str(row.get("data_pas", ""))[:10]
        popup_html = f"""
        <div style="font-family:sans-serif;font-size:12px;min-width:180px">
            <b>{row.get('NM_MUN', row.get('municipio',''))}</b><br>
            <b>Data:</b> {date_str}<br>
            <b>Satelite:</b> {row.get('satelite','')}<br>
            <b>Bioma:</b> {row.get('bioma','')}<br>
            <b>FRP:</b> {frp_str}<br>
            <b>Ano:</b> {row.get('ano','')}
        </div>"""
        folium.CircleMarker(
            [lat, lon], radius=4, color="#ff4b2b", fill=True,
            fill_color="#ff4b2b", fill_opacity=0.7, weight=1,
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(cluster)
    cluster.add_to(m)

    # --- Municipality labels ---
    for feat in geojson["features"]:
        props = feat["properties"]
        name = props.get("NM_MUN", "")
        coords = feat["geometry"]["coordinates"]
        geom_type = feat["geometry"]["type"]
        ring = coords[0] if geom_type == "Polygon" else coords[0][0] if geom_type == "MultiPolygon" else None
        if ring is None:
            continue
        cx = np.mean([c[0] for c in ring])
        cy = np.mean([c[1] for c in ring])
        count = freq_dict.get(name, 0)
        label = f"{name} ({count})"
        folium.Marker(
            [cy, cx],
            icon=folium.DivIcon(html=f"""<div style="font-size:10px;font-weight:700;
                color:white;text-shadow:1px 1px 2px black;white-space:nowrap;
                transform:translate(-50%,-50%)">{label}</div>"""),
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    return _full_map_html(m, js_code)


def make_heatmap_only(df, anos=None, municipios=None):
    filtered = _filter(df, anos, municipios)
    m = folium.Map(location=RMC_CENTER, zoom_start=DEFAULT_ZOOM, tiles="CartoDB positron")

    heat_data = filtered[["latitude", "longitude"]].dropna().values.tolist()
    if heat_data:
        plugins.HeatMap(
            heat_data, name="Heatmap", min_opacity=0.2, radius=15, blur=12,
            gradient={0.1: "#3388ff", 0.3: "#66cc66", 0.5: "#ffff33",
                      0.7: "#ff9933", 1: "#ff3333"},
        ).add_to(m)

    geojson = _sanitize_geojson(load_geojson())
    geojson_id = f"gj_{uuid.uuid4().hex[:8]}"
    data_json = json.dumps(geojson, default=str)

    js_code = f"""
    <script>
    (function() {{
        var geojsonData = {data_json};
        L.geoJSON(geojsonData, {{
            style: function() {{ return {{fillColor:'transparent', color:'#888', weight:1.5}}; }},
        }}).addTo(window._folium_map_{m._id});
    }})();
    </script>
    """

    return _full_map_html(m, js_code)


def make_year_animation(df):
    m = folium.Map(location=RMC_CENTER, zoom_start=DEFAULT_ZOOM, tiles="CartoDB dark_matter")

    geojson = _sanitize_geojson(load_geojson())
    geojson_id = f"gj_{uuid.uuid4().hex[:8]}"
    data_json = json.dumps(geojson, default=str)

    js_borders = f"""
    <script>
    (function() {{
        var geojsonData = {data_json};
        L.geoJSON(geojsonData, {{
            style: function() {{ return {{fillColor:'transparent', color:'#888', weight:1.5}}; }},
        }}).addTo(window._folium_map_{m._id});
    }})();
    </script>
    """

    features = []
    for _, row in df.iterrows():
        lat, lon = row.get("latitude"), row.get("longitude")
        if pd.isna(lat) or pd.isna(lon):
            continue
        date_val = row.get("data_pas")
        if pd.isna(date_val):
            continue
        date_str = pd.Timestamp(date_val).strftime("%Y-%m-%d")
        frp = row.get("frp", 0) or 0
        popup_str = f"{row.get('NM_MUN','')} | FRP: {frp:.1f}" if pd.notna(frp) else str(row.get("NM_MUN", ""))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {
                "time": date_str,
                "popup": popup_str,
                "icon": "circle",
                "iconstyle": {"color": "#ff4b2b", "fillColor": "#ff4b2b",
                              "fillOpacity": 0.6, "radius": 4},
            },
        })

    if features:
        plugins.TimestampedGeoJson(
            {"type": "FeatureCollection", "features": features},
            period="P1Y", add_last_point=True, auto_play=False,
            loop=True, max_speed=5, loop_button=True,
            date_options="YYYY", time_slider_drag_update=True,
        ).add_to(m)

    return _full_map_html(m, js_borders)


def make_municipality_detail(df, anos=None):
    filtered = _filter(df, anos, None)
    geojson = _sanitize_geojson(load_geojson())
    freq = filtered.groupby("NM_MUN").size().reset_index(name="total_focos")
    frp_avg = filtered.groupby("NM_MUN")["frp"].mean().reset_index(name="frp_medio")
    stats = freq.merge(frp_avg, on="NM_MUN", how="left").fillna(0)

    m = folium.Map(location=RMC_CENTER, zoom_start=DEFAULT_ZOOM, tiles="OpenStreetMap")

    max_focos = max(stats["total_focos"].max(), 1) if len(stats) > 0 else 1
    freq_dict = dict(zip(stats["NM_MUN"], stats["total_focos"].astype(int)))
    frp_dict = dict(zip(stats["NM_MUN"], stats["frp_medio"].round(1).astype(str)))
    area_dict = {f["properties"]["NM_MUN"]: f["properties"].get("AREA_KM2", "N/A")
                 for f in geojson["features"]}

    data_json = json.dumps(geojson, default=str)
    freq_json = json.dumps(freq_dict)
    frp_json = json.dumps(frp_dict)
    area_json = json.dumps(area_dict)
    max_fc = max_focos

    js_code = f"""
    <script>
    (function() {{
        var geojsonData = {data_json};
        var freqData = {freq_json};
        var frpData = {frp_json};
        var areaData = {area_json};
        var maxFc = {max_fc};

        function getColor(count) {{
            var t = count / maxFc;
            var r = Math.round(255 * t + 50 * (1-t));
            var g = Math.round(200 * (1-t) + 50 * t);
            var b = Math.round(50 * (1-t));
            return 'rgb(' + r + ',' + g + ',' + b + ')';
        }}

        L.geoJSON(geojsonData, {{
            style: function(feature) {{
                var name = feature.properties.NM_MUN;
                var count = freqData[name] || 0;
                return {{
                    fillColor: getColor(count),
                    weight: 1, opacity: 0.7, color: '#555',
                    fillOpacity: 0.55
                }};
            }},
            onEachFeature: function(feature, layer) {{
                var name = feature.properties.NM_MUN;
                var count = freqData[name] || 0;
                var frp = frpData[name] || '0';
                var area = areaData[name] || 'N/A';
                layer.bindPopup(
                    '<div style="font-family:sans-serif;font-size:13px;min-width:200px">' +
                    '<h4 style="margin:0 0 8px;color:#333">' + name + '</h4>' +
                    '<b>Total de focos:</b> ' + count + '<br>' +
                    '<b>FRP medio:</b> ' + frp + '<br>' +
                    '<b>Area:</b> ' + area + ' km2</div>'
                );
                layer.bindTooltip('<b>' + name + '</b><br>Focos: ' + count);
            }}
        }}).addTo(window._folium_map_{m._id});
    }})();
    </script>
    """

    return _full_map_html(m, js_code)
