"""Read an AV export (GeoPackage, Shapefile, GeoJSON, also inside a zip) without changing it."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pyogrio

from app.parsers.av_fields import find_columns

POLYGONS = {
    "Polygon",
    "MultiPolygon",
    "Polygon Z",
    "MultiPolygon Z",
    "3D Polygon",
    "3D MultiPolygon",
    "CurvePolygon",
    "MultiSurface",
    "CurvePolygon Z",
    "MultiSurface Z",
}
# a layer with mixed or broken geometries is listed as Unknown, it may still hold the parcels
MAYBE_POLYGONS = POLYGONS | {"Unknown", "Geometry", "GeometryCollection"}
FK_HINTS = ("liegenschaft_von", "grundstueck", "_von", "fk")
PK_HINTS = ("t_id", "tid", "t_ili_tid", "fid", "id")


@dataclass
class Extract:
    frame: gpd.GeoDataFrame
    path: Path
    layer: str
    sha256: str
    crs: str | None
    municipalities: gpd.GeoDataFrame | None = None
    municipality_layer: str | None = None
    joined_from: str | None = None
    dataset_date: str | None = None


_HASHES: dict[tuple[str, int, int], str] = {}


def sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _HASHES:
        _HASHES[key] = _digest(path)
    return _HASHES[key]


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


DATA_SUFFIXES = (".gpkg", ".shp", ".geojson", ".json", ".fgb")


def gdal_path(path: Path) -> str:
    return str(unpack(path)) if path.suffix.lower() == ".zip" else str(path)


def unpack(path: Path) -> Path:
    """Unpack a downloaded zip once, next to it, and return the data file inside."""
    target = path.parent / f"{path.stem}_{sha256(path)[:12]}"
    if not target.exists():
        partial = target.with_name(target.name + ".part")
        shutil.rmtree(partial, ignore_errors=True)
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                dest = (partial / member).resolve()
                if not dest.is_relative_to(partial.resolve()):
                    raise ValueError(f"unsafe path in {path.name}: {member}")
            zf.extractall(partial)
        partial.rename(target)
    found = sorted(p for p in target.rglob("*") if p.suffix.lower() in DATA_SUFFIXES)
    if not found:
        raise ValueError(f"no GeoPackage, Shapefile or GeoJSON inside {path.name}")
    gpkg = [p for p in found if p.suffix.lower() == ".gpkg"]
    return (gpkg or found)[0]


def gpkg_date(path: Path, layer: str) -> str | None:
    """last_change of the layer as stated in gpkg_contents, the closest thing to a dataset date."""
    if path.suffix.lower() == ".zip":
        path = unpack(path)
    if path.suffix.lower() != ".gpkg":
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
            hit = con.execute("SELECT last_change FROM gpkg_contents WHERE table_name = ?", (layer,)).fetchone()
    except sqlite3.Error:
        return None
    return str(hit[0])[:10] if hit and hit[0] else None


def layers(path: Path) -> list[tuple[str, str]]:
    return [(str(name), str(geom)) for name, geom in pyogrio.list_layers(gdal_path(path))]


def describe(path: Path) -> list[dict]:
    """Layer names, geometry types, feature counts and columns, for choosing the right layer."""
    out = []
    for name, geom in layers(path):
        info = pyogrio.read_info(gdal_path(path), layer=name)
        out.append(
            {
                "layer": name,
                "geometry": geom,
                "features": int(info["features"]),
                "crs": info["crs"],
                "columns": list(info["fields"]),
            }
        )
    return out


def pick_parcel_layer(path: Path, wanted: str | None = None) -> str:
    """The configured layer, or the polygon layer that has parcel number columns."""
    found = layers(path)
    names = [n for n, _ in found]
    if wanted:
        if wanted not in names:
            raise ValueError(f"layer {wanted!r} not in {path.name}; layers: {', '.join(names)}")
        return wanted
    candidates = []
    for name, geom in found:
        if geom not in MAYBE_POLYGONS:
            continue
        cols = list(pyogrio.read_info(gdal_path(path), layer=name)["fields"])
        hit = find_columns(cols)
        if "parcel_number" in hit and "nbident" in hit:
            lower = name.lower()
            if "proj" in lower or lower.startswith("dprsf") or "selbstrecht" in lower:
                continue  # projected parcels and building rights are not real estate parcels
            # resf is the geodienste.ch name of the Liegenschaften layer
            candidates.append((0 if lower == "resf" or lower.endswith("liegenschaft") else 1, name))
    if not candidates:
        # geometry and numbers may sit in two layers (Liegenschaft and Grundstueck)
        geometry_only = [n for n, g in found if g in POLYGONS and n.lower().endswith("liegenschaft")]
        if geometry_only:
            return geometry_only[0]
        raise ValueError(f"no parcel layer found in {path.name}; run `python main.py inspect {path}`")
    return sorted(candidates)[0][1]


def pick_municipality_layer(path: Path, wanted: str | None = None) -> str | None:
    if wanted:
        return wanted
    for name, geom in layers(path):
        lower = name.lower()
        if geom in POLYGONS and (lower == "mbsf" or "gemeindegrenze" in lower) and "teil" not in lower:
            return name
    return None


def _pick_column(columns, hints) -> str | None:
    lower = {c.lower(): c for c in columns}
    for hint in hints:
        for low, col in lower.items():
            if low == hint or (len(hint) > 3 and hint in low):
                return col
    return None


def join_attributes(
    path: Path,
    frame: gpd.GeoDataFrame,
    attribute_layer: str | None = None,
    left: str | None = None,
    right: str | None = None,
) -> tuple[gpd.GeoDataFrame, str]:
    """DM.01 keeps the parcel number on Grundstueck and the area on Liegenschaft; join them."""
    names = [attribute_layer] if attribute_layer else [n for n, _ in layers(path)]
    for name in names:
        cols = list(pyogrio.read_info(gdal_path(path), layer=name)["fields"])
        hit = find_columns(cols)
        if not ("nbident" in hit and "parcel_number" in hit):
            continue
        attrs = pyogrio.read_dataframe(gdal_path(path), layer=name, read_geometry=False, fid_as_index=True)
        rkey = right or _pick_column(cols, PK_HINTS)
        lkey = left or _pick_column([c for c in frame.columns if c != "geometry"], FK_HINTS)
        if lkey is None:
            raise ValueError(f"cannot tell how {name} links to the geometry layer; set join_left/join_right")
        attrs = attrs.reset_index().rename(columns={"index": "fid"}) if rkey in (None, "fid") else attrs
        rkey = rkey or "fid"
        merged = frame.merge(
            attrs.drop(columns=[c for c in attrs.columns if c in frame.columns and c != rkey]),
            left_on=lkey,
            right_on=rkey,
            how="left",
            suffixes=("", "_grundstueck"),
        )
        merged.index = frame.index
        return gpd.GeoDataFrame(merged, geometry="geometry", crs=frame.crs), name
    raise ValueError(f"no layer with parcel numbers to join in {path.name}")


def read(
    path: str | Path,
    layer: str | None = None,
    municipality_layer: str | None = None,
    attribute_layer: str | None = None,
    join_left: str | None = None,
    join_right: str | None = None,
) -> Extract:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    chosen = pick_parcel_layer(path, layer)
    frame = gpd.read_file(gdal_path(path), layer=chosen, engine="pyogrio", fid_as_index=True)
    joined = None
    hit = find_columns([c for c in frame.columns if c != "geometry"])
    if attribute_layer or not ("nbident" in hit and "parcel_number" in hit):
        frame, joined = join_attributes(path, frame, attribute_layer, join_left, join_right)
    crs = frame.crs.to_string() if frame.crs else None
    out = Extract(
        frame=frame,
        path=path,
        layer=chosen,
        sha256=sha256(path),
        crs=crs,
        joined_from=joined,
        dataset_date=gpkg_date(path, chosen),
    )
    mun = pick_municipality_layer(path, municipality_layer)
    if mun:
        out.municipalities = gpd.read_file(gdal_path(path), layer=mun, engine="pyogrio")
        out.municipality_layer = mun
    return out
