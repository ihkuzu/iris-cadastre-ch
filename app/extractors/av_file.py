"""Read an AV export (GeoPackage, Shapefile, GeoJSON, also inside a zip) without changing it."""

from __future__ import annotations

import hashlib
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


def sha256(path: Path) -> str:
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
    target = path.with_suffix("")
    if not target.exists():
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                dest = (target / member).resolve()
                if not dest.is_relative_to(target.resolve()):
                    raise ValueError(f"unsafe path in {path.name}: {member}")
            zf.extractall(target)
    found = sorted(p for p in target.rglob("*") if p.suffix.lower() in DATA_SUFFIXES)
    if not found:
        raise ValueError(f"no GeoPackage, Shapefile or GeoJSON inside {path.name}")
    gpkg = [p for p in found if p.suffix.lower() == ".gpkg"]
    return (gpkg or found)[0]


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
        if geom not in POLYGONS:
            continue
        cols = list(pyogrio.read_info(gdal_path(path), layer=name)["fields"])
        hit = find_columns(cols)
        if "parcel_number" in hit and "nbident" in hit:
            # Liegenschaft layers win over other parcel-like polygon layers
            candidates.append((0 if "liegenschaft" in name.lower() else 1, name))
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
        if geom in POLYGONS and ("gemeindegrenze" in lower or "gemeinde" in lower) and "teil" not in lower:
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
    out = Extract(frame=frame, path=path, layer=chosen, sha256=sha256(path), crs=crs, joined_from=joined)
    mun = pick_municipality_layer(path, municipality_layer)
    if mun:
        out.municipalities = gpd.read_file(gdal_path(path), layer=mun, engine="pyogrio")
        out.municipality_layer = mun
    return out
