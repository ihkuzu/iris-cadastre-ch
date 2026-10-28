"""Synthetic AV-like files for tests. Nothing here is real cadastre data.

Every feature uses canton code XX, EGRIDs starting with CH9999 and the note SYNTHETIC.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon, box

X0, Y0 = 2_600_000, 1_200_000  # LV95 near Bern, only so coordinates look Swiss


def square(i: int, size: float = 20.0) -> Polygon:
    x, y = X0 + (i % 10) * 30, Y0 + (i // 10) * 30
    return box(x, y, x + size, y + size)


def parcels(n: int = 12) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "NBIdent": "XX0200000001",
                "Nummer": str(100 + i),
                "EGRIS_EGRID": f"CH9999{i:08d}",
                "Flaechenmass": 400.0,
                "Vollstaendigkeit": "vollstaendig",
                "Art": "Liegenschaft",
                "Note": "SYNTHETIC test fixture",
                "geometry": square(i),
            }
        )
    return rows


def write(
    path: Path,
    rows: list[dict],
    crs: int | None = 2056,
    layer: str = "Liegenschaften_Liegenschaft",
    municipalities: bool = True,
) -> Path:
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)
    gdf.to_file(path, layer=layer, driver="GPKG", engine="pyogrio")
    if municipalities:
        mun = gpd.GeoDataFrame(
            [
                {"BFSNr": 9901, "Name": "Synthetica Nord", "geometry": box(X0 - 10, Y0 + 15, X0 + 400, Y0 + 400)},
                {"BFSNr": 9902, "Name": "Synthetica Süd", "geometry": box(X0 - 10, Y0 - 10, X0 + 400, Y0 + 15)},
            ],
            geometry="geometry",
            crs=crs,
        )
        mun.to_file(path, layer="Gemeindegrenzen_Gemeindegrenze", driver="GPKG", engine="pyogrio")
    return path


def broken() -> list[dict]:
    """One row per kind of problem the transformer has to catch."""
    good = parcels(3)
    base = {k: v for k, v in good[0].items() if k != "geometry"}
    spike = Polygon(
        [
            (X0, Y0 + 500),
            (X0 + 100, Y0 + 500),
            (X0 + 100, Y0 + 600),
            (X0, Y0 + 600),
            (X0, Y0 + 550),
            (X0 - 0.01, Y0 + 550.5),
            (X0 + 0.01, Y0 + 550.6),
            (X0, Y0 + 551),
        ]
    )
    bowtie = Polygon([(X0, Y0 + 700), (X0 + 10, Y0 + 710), (X0 + 10, Y0 + 700), (X0, Y0 + 710)])
    return good + [
        {**base, "Nummer": None, "EGRIS_EGRID": "CH999900000101", "geometry": square(20)},
        {**base, "Nummer": "201", "EGRIS_EGRID": "CH-BAD", "geometry": square(21)},
        {**base, "Nummer": "202", "EGRIS_EGRID": "CH999900000202", "geometry": Polygon()},
        {**base, "Nummer": "203", "EGRIS_EGRID": "CH999900000203", "geometry": LineString([(X0, Y0), (X0 + 5, Y0)])},
        {**base, "Nummer": "204", "EGRIS_EGRID": "CH999900000204", "Flaechenmass": 10000.0, "geometry": spike},
        {**base, "Nummer": "205", "EGRIS_EGRID": "CH999900000205", "geometry": bowtie},
        {**good[1]},
        {**good[2], "geometry": square(30)},
        {**base, "Nummer": "206", "EGRIS_EGRID": "CH999900000000", "geometry": square(40)},
    ]


def geodienste(path: Path, parts: bool = False) -> Path:
    """The flat layout of the geodienste.ch GeoPackage: resf, resfproj, dprsf and mbsf, all SYNTHETIC."""

    def layer(name, rows):
        gpd.GeoDataFrame(rows, geometry="geometry", crs=2056).to_file(path, layer=name, driver="GPKG", engine="pyogrio")

    def row(i, number, geom, **extra):
        return {
            "BFSNr": 9902,
            "NBIdent": "XX0200000001",
            "Nummer": number,
            "EGRIS_EGRID": f"CH9999{i:08d}",
            "Vollstaendigkeit": "vollstaendig",
            "Flaeche": round(geom.area),
            "Gueltigkeit": "gueltig",
            "Kanton": "XX",
            "geometry": geom,
            **extra,
        }

    resf = [row(i, str(100 + i), square(i)) for i in range(4)]
    if parts:
        # one parcel drawn as two separate polygons, the way AV stores a parcel cut by a road
        resf += [row(50, "150", square(5)), row(50, "150", square(7))]
    layer("resf", resf)
    layer("resfproj", [row(90, "900", square(8))])
    layer("dprsf", [row(91, "S1", square(9), Art="SelbstRecht.Baurecht")])
    layer(
        "mbsf",
        [{"BFSNr": 9902, "Name": "Synthetica", "Kanton": "XX", "geometry": box(X0 - 10, Y0 - 10, X0 + 400, Y0 + 30)}],
    )
    return path
