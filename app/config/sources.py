"""The configured sources: one entry per canton, with licence and provenance."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CANTONS = {
    "AG": "Aargau",
    "AI": "Appenzell Innerrhoden",
    "AR": "Appenzell Ausserrhoden",
    "BE": "Bern",
    "BL": "Basel-Landschaft",
    "BS": "Basel-Stadt",
    "FR": "Fribourg",
    "GE": "Genève",
    "GL": "Glarus",
    "GR": "Graubünden",
    "JU": "Jura",
    "LU": "Luzern",
    "NE": "Neuchâtel",
    "NW": "Nidwalden",
    "OW": "Obwalden",
    "SG": "St. Gallen",
    "SH": "Schaffhausen",
    "SO": "Solothurn",
    "SZ": "Schwyz",
    "TG": "Thurgau",
    "TI": "Ticino",
    "UR": "Uri",
    "VD": "Vaud",
    "VS": "Valais",
    "ZG": "Zug",
    "ZH": "Zürich",
}
SYNTHETIC = "XX"


@dataclass(frozen=True)
class Source:
    canton: str
    name: str
    url: str
    licence: str
    licence_url: str
    access: str
    dataset: str = "Amtliche Vermessung (DM.01-AV-CH)"
    native_crs: str = "EPSG:2056"
    file: str | None = None
    layer: str | None = None
    municipality_layer: str | None = None
    parcel_type: str | None = None
    attribute_layer: str | None = None
    join_left: str | None = None
    join_right: str | None = None
    dataset_date: str | None = None
    # Fribourg numbers the parts of one parcel <article>.<nn>; the parts share the parcel's EGRID
    egrid_parts: bool = False
    notes: str = ""
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        return self.canton == SYNTHETIC

    @property
    def lawful(self) -> bool:
        return self.access in ("open", "open-with-attribution") or self.synthetic


def load_sources(path: str | Path) -> dict[str, Source]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for code, entry in data.get("source", {}).items():
        code = code.upper()
        if code not in CANTONS and code != SYNTHETIC:
            raise ValueError(f"unknown canton code {code}")
        out[code] = Source(canton=code, **entry)
    return out
