"""Command line: inspect a file, download, ingest, report and validate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from loguru import logger
from sqlalchemy import text

from app.config.settings import Settings, get_settings
from app.config.sources import load_sources
from app.database.session import engine, prepare
from app.extractors import av_file
from app.loaders.parcels import load
from app.parsers.av_fields import find_columns
from app.reports import quality
from app.transformers.parcels import transform


def setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    fmt = "{time:HH:mm:ss} {level:<7} {extra[canton]:<2} {message}"
    logger.configure(extra={"canton": "--"})
    logger.add(sys.stderr, format=fmt, level="INFO")
    # one JSON line per event, with run id, canton and file, for auditing
    logger.add(settings.log_dir / "ingest.jsonl", serialize=True, level="DEBUG")


def cmd_inspect(args, settings) -> int:
    for layer in av_file.describe(Path(args.file)):
        mapping = find_columns(layer["columns"])
        print(f"{layer['layer']}: {layer['geometry']}, {layer['features']} features, CRS {str(layer['crs'])[:30]}")
        print(f"    columns: {', '.join(layer['columns'])}")
        if mapping:
            print(f"    recognised: {json.dumps(mapping)}")
    return 0


def cmd_download(args, settings) -> int:
    source = load_sources(settings.sources_file)[args.canton.upper()]
    if not source.lawful:
        print(f"{source.canton}: access is {source.access!r}; download it yourself after accepting the terms")
        return 2
    target = settings.data_dir / "raw" / source.canton / (source.file or Path(source.url).name)
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {source.url}\n         to {target}")
    with urllib.request.urlopen(source.url, timeout=120) as res, open(target, "wb") as fh:
        while block := res.read(1 << 20):
            fh.write(block)
    if target.read_bytes()[:2] != b"PK":
        # geodienste.ch answers some formats with an order page instead of the file
        target.unlink()
        print("the server did not return a zip; order the GeoPackage on https://www.geodienste.ch/downloads/av,")
        print(f"then save it as {target} and run ingest again")
        return 2
    print(f"sha256 {hashlib.sha256(target.read_bytes()).hexdigest()}")
    return 0


def cmd_ingest(args, settings) -> int:
    sources = load_sources(settings.sources_file)
    code = args.canton.upper()
    if code not in sources:
        print(f"no source configured for {code}; see {settings.sources_file}")
        return 2
    source = sources[code]
    path = Path(args.file) if args.file else settings.data_dir / "raw" / code / (source.file or "")
    extract = av_file.read(
        path,
        layer=args.layer or source.layer,
        municipality_layer=source.municipality_layer,
        attribute_layer=source.attribute_layer,
        join_left=source.join_left,
        join_right=source.join_right,
    )
    result = transform(extract, source, settings)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "read": result.read,
                    "accepted": len(result.rows),
                    "rejected": dict(result.reasons),
                    "warnings": dict(result.warnings),
                    "mapping": result.mapping,
                },
                indent=2,
            )
        )
        return 0
    stats = load(engine(settings.database_url), settings.db_schema, settings.table, result, extract, source)
    print(
        f"run {stats.run_id}: inserted {stats.inserted}, updated {stats.updated}, "
        f"unchanged {stats.unchanged}, rejected {stats.rejected}"
    )
    return 0


def cmd_init(args, settings) -> int:
    prepare(engine(settings.database_url), settings.db_schema, settings.table)
    print(f"schema {settings.db_schema} ready")
    return 0


def cmd_report(args, settings) -> int:
    data = quality.gather(engine(settings.database_url), settings.db_schema, settings.table)
    quality.write(data, Path(args.out), Path(args.results), Path("docs/report_notes.md"))
    print(f"wrote {args.out} and {args.results}/")
    return 0


def cmd_validate(args, settings) -> int:
    sql = Path("sql/validation.sql").read_text(encoding="utf-8").replace("iris_staging.", f"{settings.db_schema}.")
    failed = 0
    with engine(settings.database_url).connect() as conn:
        for row in conn.execute(text(sql)):
            print(f"{'ok  ' if row.passed else 'FAIL'} {row.check_name}: {row.found}")
            failed += not row.passed
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iris-cadastre-ch", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect", help="list layers and columns of an AV file")
    p.add_argument("file")
    p = sub.add_parser("download", help="download a configured open source")
    p.add_argument("canton")
    p = sub.add_parser("ingest", help="read, check and load one canton")
    p.add_argument("canton")
    p.add_argument("--file", help="a file you downloaded yourself")
    p.add_argument("--layer", help="parcel layer, found by itself if left out")
    p.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    sub.add_parser("init-db", help="create the staging schema and tables")
    p = sub.add_parser("report", help="write the quality report from the database")
    p.add_argument("--out", default="docs/quality_report.md")
    p.add_argument("--results", default="results")
    sub.add_parser("validate", help="run sql/validation.sql; exit 1 if a check fails")
    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings)
    handlers = {
        "inspect": cmd_inspect,
        "download": cmd_download,
        "ingest": cmd_ingest,
        "init-db": cmd_init,
        "report": cmd_report,
        "validate": cmd_validate,
    }
    try:
        return handlers[args.cmd](args, settings)
    except (FileNotFoundError, ValueError) as error:
        logger.error("{}", error)
        return 2
