# Sources and access, as checked on 2026-10-28

## Where Swiss cadastral survey data comes from

- The official cadastral survey (Amtliche Vermessung, AV; mensuration officielle, MO) is run by
  the cantons and coordinated by swisstopo / cadastre.ch.
- geodienste.ch (operated by KGK-CGC) distributes AV for all 26 cantons and Liechtenstein in one
  national offer, version 24.0, model DM.01-AV-CH, in LV95 (EPSG:2056).
  [STAC collection](https://www.geodienste.ch/stac/collections/av),
  [service description](https://www.geodienste.ch/services/av/info)
- Formats: INTERLIS, GeoPackage, Shapefile, CSV, DXF (some cantons), WFS, WMS and OGC API.
  [Downloads](https://www.geodienste.ch/downloads/av?locale=de)
- Direct download pattern used in `config/sources.toml`:
  `https://www.geodienste.ch/downloads/geopackage/av/{KT}/deu/av_{KT}_gpkg_lv95.zip`.
- The new model DMAV is in force since 2024, but each canton switches on its own date (most by the
  end of 2027) and geodienste.ch still publishes DM.01.
  [Factsheet](https://www.cadastre-manual.admin.ch/dam/it/sd-web/zB5gUibuSmHM/Factsheet_DE-definitiv.pdf)

## Lawful access

geodienste.ch lists the conditions per canton. Cantonal terms always apply and the data stay
under cantonal copyright; geodienste.ch asks for at most one download per dataset and day.
[Terms of use](https://www.geodienste.ch/terms-of-use),
[conditions per canton](https://www.geodienste.ch/info/services.csv?base_topics=av&language=de)

| Access | Cantons |
|---|---|
| Freely available, attribution required | AG, AI, BE, BL, BS, FR, GE (plus SITG terms) |
| Freely available | AR, GL, GR, SG (sg.ch terms) |
| Approval required, fees possible | JU (above 10 ha), LU, NE, NW, OW, VD |
| Not checked row by row | SH, SO, SZ, TG, TI, UR, VS, ZG, ZH |

This submission uses AI, BS, GE and FR: all freely available with attribution, German and French,
rural, city, urban and a large bilingual canton.

## The data model (DM.01-AV-CH, topic Liegenschaften)

- `Grundstueck`: `NBIdent` (TEXT*12, canton code plus a 10-character numbering area),
  `Nummer` (TEXT*12), `EGRIS_EGRID` (optional, 14 characters), `Gueltigkeit`,
  `Vollstaendigkeit`, `Art`, `GesamteFlaechenmass`; identified by NBIdent + Nummer.
- `Liegenschaft`: `Geometrie` (AREA with straight lines and arcs), `Flaechenmass`,
  `Liegenschaft_von` -> Grundstueck.
- NBIdent + Nummer is unique in Switzerland; the EGRID is a national identifier that is never
  reused. [DM.01-AV-CH](https://www.cadastre-manual.admin.ch/dam/de/sd-web/EcX-o1dH3DHy/DM-01-AV-CH_de.pdf),
  [E-GRID guide](https://www.cadastre-manual.admin.ch/dam/it/sd-web/OUiZkmVP8ldE/Leitfaden-E-GRID-de.pdf)
- Municipality boundaries (`Gemeindegrenzen`) with the BFS number come in the same export.
