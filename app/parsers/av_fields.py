"""Map the column names of AV exports to one set of names.

Exports from geodienste.ch, cantonal shops and WFS spell the same attribute differently
(EGRIS_EGRID, egris_egrid, EGRID ...), so each canonical field lists the names it accepts.
"""

from __future__ import annotations

CANDIDATES: dict[str, tuple[str, ...]] = {
    "egrid": ("egris_egrid", "egrid", "e_grid"),
    "nbident": ("nbident", "nb_ident", "numerierungsbereich", "nbi"),
    "parcel_number": ("nummer", "number", "numero", "parzellennummer", "grundstuecknummer"),
    "area_source_m2": ("flaechenmass", "flaeche", "gesamteflaechenmass", "area", "surface"),
    "completeness": ("vollstaendigkeit", "completeness"),
    "parcel_type": ("art", "grundstueckart", "type"),
    "bfs_nr": ("bfsnr", "bfs_nr", "bfs_nummer", "gemeinde_bfs", "bfs"),
    "municipality": ("gemeindename", "gemeinde_name", "name_gemeinde"),
    "canton": ("kanton", "canton", "kt"),
}
MUNICIPALITY = {"bfs_nr": ("bfsnr", "bfs_nr", "bfs_nummer", "bfs"), "municipality": ("name", "gemeindename")}


def _norm(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def find_columns(columns, candidates=CANDIDATES, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """canonical name -> source column; explicit overrides from the config win."""
    by_norm = {_norm(c): c for c in columns}
    out = {}
    for canonical, names in candidates.items():
        for name in names:
            if name in by_norm:
                out[canonical] = by_norm[name]
                break
    for canonical, source in (overrides or {}).items():
        if source not in columns:
            raise ValueError(f"configured column {source!r} for {canonical} is not in the file")
        out[canonical] = source
    return out
