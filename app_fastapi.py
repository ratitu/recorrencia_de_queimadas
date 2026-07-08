#!/usr/bin/env python3
"""
FastAPI — Mapas Interativos de Queimadas na RMC
Mapas Folium/Leaflet com filtros, heatmap, coroplético e clustering.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from interactive_maps import (
    make_fires_map, make_heatmap_only, make_year_animation, make_municipality_detail,
)

app = FastAPI(title="Queimadas RMC", version="2.0.0")

BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados"

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

# --- Load data at startup ----------------------------------------------------
CSV_PATH = RESULTADOS / "todos_focos_rmc.csv"
if CSV_PATH.exists():
    df_raw = pd.read_csv(CSV_PATH, parse_dates=["data_pas"])
    if "mes" not in df_raw.columns:
        df_raw["mes"] = df_raw["data_pas"].dt.month_name()
else:
    df_raw = pd.DataFrame()


def _clean_nans(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, dict):
        return {k: _clean_nans(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nans(v) for v in obj]
    return obj


def _parse_anos(request: Request):
    amin = request.query_params.get("ano_min")
    amax = request.query_params.get("ano_max")
    if amin is None and amax is None:
        return None
    return (int(amin) if amin else None, int(amax) if amax else None)


def _parse_municipios(request: Request) -> list[str] | None:
    m = request.query_params.get("municipios")
    if m:
        return [x.strip() for x in m.split(",") if x.strip()]
    return None


# --- Main page ----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = {}
    if not df_raw.empty:
        stats = {
            "total": f"{len(df_raw):,}",
            "anos": f"{int(df_raw['ano'].min())}\u2013{int(df_raw['ano'].max())}",
            "municipios": str(df_raw["NM_MUN"].nunique()),
            "mes_critico": str(df_raw["mes"].mode().iloc[0]) if "mes" in df_raw.columns else "\u2014",
        }

    mun_list = sorted(df_raw["NM_MUN"].unique().tolist()) if not df_raw.empty else []

    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
        "municipios": mun_list,
    })


# --- Interactive map endpoints (return HTML fragments) -----------------------

@app.get("/map/main", response_class=HTMLResponse)
async def map_main(request: Request):
    anos = _parse_anos(request)
    munis = _parse_municipios(request)
    return HTMLResponse(make_fires_map(df_raw, anos, munis))


@app.get("/map/heatmap", response_class=HTMLResponse)
async def map_heatmap(request: Request):
    anos = _parse_anos(request)
    munis = _parse_municipios(request)
    return HTMLResponse(make_heatmap_only(df_raw, anos, munis))


@app.get("/map/animation", response_class=HTMLResponse)
async def map_animation():
    return HTMLResponse(make_year_animation(df_raw))


@app.get("/map/choropleth", response_class=HTMLResponse)
async def map_choropleth(request: Request):
    anos = _parse_anos(request)
    return HTMLResponse(make_municipality_detail(df_raw, anos))


# --- JSON API endpoints -------------------------------------------------------

@app.get("/api/stats")
async def api_stats():
    if df_raw.empty:
        return JSONResponse({"error": "no data"}, status_code=404)
    return {
        "total_focos": int(len(df_raw)),
        "ano_min": int(df_raw["ano"].min()),
        "ano_max": int(df_raw["ano"].max()),
        "municipios": int(df_raw["NM_MUN"].nunique()),
        "mes_critico": str(df_raw["mes"].mode().iloc[0]) if "mes" in df_raw.columns else None,
    }


@app.get("/api/focos")
async def api_focos(ano_min: int | None = None, ano_max: int | None = None,
                    municipio: str | None = None):
    filtered = df_raw.copy()
    if ano_min is not None:
        filtered = filtered[filtered["ano"] >= ano_min]
    if ano_max is not None:
        filtered = filtered[filtered["ano"] <= ano_max]
    if municipio:
        filtered = filtered[filtered["NM_MUN"].str.upper() == municipio.upper()]
    cols = ["latitude", "longitude", "data_pas", "satelite", "municipio",
            "bioma", "frp", "ano", "NM_MUN"]
    existing = [c for c in cols if c in filtered.columns]
    result = filtered[existing].copy()
    if "data_pas" in result.columns:
        result["data_pas"] = result["data_pas"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return _clean_nans(result.to_dict(orient="records"))


@app.get("/api/freq_municipio")
async def api_freq_municipio(ano_min: int | None = None, ano_max: int | None = None):
    filtered = df_raw.copy()
    if ano_min is not None:
        filtered = filtered[filtered["ano"] >= ano_min]
    if ano_max is not None:
        filtered = filtered[filtered["ano"] <= ano_max]
    freq = (filtered.groupby("NM_MUN").size()
            .reset_index(name="total_focos")
            .sort_values("total_focos", ascending=False))
    return freq.to_dict(orient="records")


@app.get("/api/freq_ano")
async def api_freq_ano():
    freq = (df_raw.groupby("ano").size()
            .reset_index(name="total_focos")
            .sort_values("ano"))
    return freq.to_dict(orient="records")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_fastapi:app", host="0.0.0.0", port=8000, reload=True)
