"""Turn raw AV features into staging rows, or into rejections with a reason."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger
from shapely import make_valid, set_precision
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

from app.config.sources import CANTONS, Source
from app.extractors.av_file import Extract
from app.parsers.av_fields import MUNICIPALITY, find_columns

LV95, LV03, WGS84 = 2056, 21781, 4326
EGRID = re.compile(r"^CH[0-9A-Z]{12}$")
REQUIRED = ("nbident", "parcel_number")


@dataclass
class Result:
    rows: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    warnings: Counter = field(default_factory=Counter)
    read: int = 0
    repaired: int = 0
    source_crs: str = ""
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def reasons(self) -> Counter:
        return Counter(r["reason"] for r in self.rejected)


def _clean(value):
    """A JSON-safe copy of one attribute value; datetimes become UTC ISO strings."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        return ts.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _text(value) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _number(value) -> float | None:
    value = _clean(value)
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _polygonal(geom: BaseGeometry) -> MultiPolygon | None:
    """Only the polygon parts, flattened to 2D."""
    if geom is None or geom.is_empty:
        return None
    if geom.has_z:
        geom = shp_transform(lambda x, y, z=None: (x, y), geom)
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    polys = [p for g in parts for p in (g.geoms if isinstance(g, MultiPolygon) else [g])]
    return MultiPolygon(polys) if polys else None


def _epsg(frame: gpd.GeoDataFrame, source: Source) -> tuple[int, bool]:
    """EPSG code of the data and whether it had to be taken from the config."""
    if frame.crs is not None:
        code = frame.crs.to_epsg()
        if code is None:
            raise ValueError(f"unrecognised CRS in file: {frame.crs.to_string()[:80]}")
        return code, False
    return int(source.native_crs.split(":")[1]), True


def record_hash(row: dict, wkb: bytes) -> str:
    keys = (
        "canton",
        "nbident",
        "parcel_number",
        "egrid",
        "bfs_nr",
        "parcel_type",
        "completeness",
        "area_source_m2",
        "source_dataset_date",
    )
    payload = json.dumps({k: row.get(k) for k in keys}, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload + wkb).hexdigest()


def _municipalities(extract: Extract, frame: gpd.GeoDataFrame) -> pd.DataFrame | None:
    """BFS number and name for each parcel from the municipality layer, by a point inside it."""
    mun = extract.municipalities
    if mun is None or mun.empty:
        return None
    cols = find_columns(list(mun.columns), MUNICIPALITY)
    if "bfs_nr" not in cols:
        return None
    mun = mun.to_crs(frame.crs) if mun.crs and frame.crs and mun.crs != frame.crs else mun
    points = gpd.GeoDataFrame(geometry=frame.geometry.representative_point(), crs=frame.crs, index=frame.index)
    keep = [cols["bfs_nr"]] + ([cols["municipality"]] if "municipality" in cols else [])
    joined = gpd.sjoin(points, mun[keep + ["geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined.rename(columns={cols["bfs_nr"]: "bfs_nr", cols.get("municipality", "_"): "municipality"})


def transform(extract: Extract, source: Source, settings) -> Result:
    frame = extract.frame
    out = Result(read=len(frame))
    log = logger.bind(canton=source.canton, file=extract.path.name, layer=extract.layer)
    out.mapping = find_columns([c for c in frame.columns if c != "geometry"], overrides=source.fields)
    missing = [k for k in REQUIRED if k not in out.mapping]
    if missing:
        raise ValueError(f"required columns not found: {', '.join(missing)}; mapping: {out.mapping}")
    epsg, assumed = _epsg(frame, source)
    if assumed:
        out.warnings["crs_from_config"] += 1
        log.warning("file has no CRS, using {} from the config", source.native_crs)
        frame = frame.set_crs(epsg)
    if epsg not in (LV95, LV03):
        raise ValueError(f"EPSG:{epsg} is not a Swiss AV reference frame (expected 2056 or 21781)")
    out.source_crs = f"EPSG:{epsg}"
    if epsg == LV03:
        # without the CHENyx06 grid installed the LV03 -> LV95 shift is only good to about a metre
        log.warning("source is LV03, reprojecting to LV95")
        out.warnings["reprojected_from_lv03"] += len(frame)
        frame = frame.to_crs(LV95)
    mun = _municipalities(extract, frame)
    attrs = [c for c in frame.columns if c != "geometry"]
    m = out.mapping
    candidates: list[tuple[dict, MultiPolygon, dict]] = []
    for fid, feature in frame.iterrows():
        raw = {c: _clean(feature[c]) for c in attrs}
        geom = feature.geometry
        reject = {
            "canton": source.canton,
            "source_feature_id": str(fid),
            "source_attributes": raw,
            "geometry_wkt": geom.wkt[:2000] if geom is not None and not geom.is_empty else None,
        }
        nbident, number = _text(feature[m["nbident"]]), _text(feature[m["parcel_number"]])
        if not nbident or not number:
            out.rejected.append({**reject, "reason": "missing_key", "detail": f"nbident={nbident!r} number={number!r}"})
            continue
        egrid = _text(feature[m["egrid"]]) if "egrid" in m else None
        egrid = egrid.upper().replace(" ", "") if egrid else None
        if egrid and not EGRID.match(egrid):
            out.rejected.append({**reject, "reason": "malformed_egrid", "detail": egrid})
            continue
        if "canton" in m:
            stated = _text(feature[m["canton"]])
            if stated and stated.upper() != source.canton:
                out.rejected.append({**reject, "reason": "canton_mismatch", "detail": stated})
                continue
        poly = _polygonal(geom)
        if poly is None:
            reason = "empty_geometry" if geom is None or geom.is_empty else "not_polygon"
            out.rejected.append({**reject, "reason": reason, "detail": None if geom is None else geom.geom_type})
            continue
        repaired = False
        if not poly.is_valid:
            fixed = _polygonal(make_valid(poly))
            change = abs(fixed.area - poly.area) / poly.area if fixed is not None and poly.area else 1.0
            if fixed is None or not fixed.is_valid or change > settings.repair_tolerance:
                out.rejected.append({**reject, "reason": "invalid_geometry", "detail": f"area change {change:.1%}"})
                continue
            poly, repaired = fixed, True
        if not source.synthetic and not nbident.upper().startswith(source.canton):
            out.warnings["nbident_without_canton_prefix"] += 1
        area_src = _number(feature[m["area_source_m2"]]) if "area_source_m2" in m else None
        bfs = _number(feature[m["bfs_nr"]]) if "bfs_nr" in m else None
        name = _text(feature[m["municipality"]]) if "municipality" in m else None
        if mun is not None and fid in mun.index:
            bfs = bfs if bfs is not None else _number(mun.at[fid, "bfs_nr"])
            name = name or (_text(mun.at[fid, "municipality"]) if "municipality" in mun.columns else None)
        row = {
            "country": "CH",
            "canton": source.canton,
            "canton_name": CANTONS.get(source.canton, "synthetic"),
            "bfs_nr": int(bfs) if bfs is not None else None,
            "municipality": name,
            "nbident": nbident,
            "parcel_number": number,
            "egrid": egrid,
            "parcel_type": _text(feature[m["parcel_type"]]) if "parcel_type" in m else None,
            "completeness": _text(feature[m["completeness"]]) if "completeness" in m else None,
            "area_m2": round(poly.area, 2),
            "area_source_m2": round(area_src, 2) if area_src is not None else None,
            "geometry_repaired": repaired,
            "source_crs": out.source_crs,
            "source_feature_id": str(fid),
            "source_dataset_date": source.dataset_date,
            "source_attributes": raw,
        }
        if row["bfs_nr"] is None:
            out.warnings["no_municipality"] += 1
        if area_src is not None:
            diff = abs(poly.area - area_src)
            if diff > max(settings.area_tolerance_m2, settings.area_tolerance_share * area_src):
                out.warnings["area_differs_from_source"] += 1
        candidates.append((row, poly, reject))
        out.repaired += repaired
    _dedupe(candidates, out)
    log.info(
        "read {} features: {} accepted, {} rejected, {} repaired",
        out.read,
        len(out.rows),
        len(out.rejected),
        out.repaired,
    )
    return out


def _dedupe(candidates, out: Result) -> None:
    """Exact copies collapse into one row; conflicting rows with the same key are all rejected."""
    by_key: dict[tuple, list] = defaultdict(list)
    for row, poly, reject in candidates:
        poly = set_precision(poly, 0.001)
        wkb = poly.normalize().wkb
        row["record_hash"] = record_hash(row, wkb)
        by_key[(row["canton"], row["nbident"], row["parcel_number"])].append((row, poly, reject))
    kept = []
    for key in sorted(by_key):
        group = by_key[key]
        hashes = {g[0]["record_hash"] for g in group}
        if len(hashes) > 1:
            for _, _, reject in group:
                out.rejected.append({**reject, "reason": "conflicting_duplicate", "detail": "/".join(key)})
            continue
        kept.append(group[0])
        for _, _, reject in group[1:]:
            out.rejected.append({**reject, "reason": "exact_duplicate", "detail": "/".join(key)})
    seen: dict[str, tuple] = {}
    clash = set()
    for row, _, _ in kept:
        if row["egrid"]:
            if row["egrid"] in seen:
                clash.add(row["egrid"])
            seen[row["egrid"]] = row
    final = []
    for row, poly, reject in kept:
        if row["egrid"] in clash:
            out.rejected.append({**reject, "reason": "duplicate_egrid", "detail": row["egrid"]})
            continue
        row["geom"] = poly
        final.append(row)
    if final:
        wgs = gpd.GeoSeries([r["geom"] for r in final], crs=LV95).to_crs(WGS84)
        for row, geom in zip(final, wgs, strict=True):
            row["geom_wgs84"] = _polygonal(geom)
    out.rows.extend(final)


def now() -> datetime:
    return datetime.now(UTC)
