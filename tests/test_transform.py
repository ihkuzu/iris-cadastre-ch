import dataclasses
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest

from app.extractors import av_file
from app.parsers.av_fields import find_columns
from app.transformers.parcels import transform
from tests import fixtures


def run(path, settings, source, layer="Liegenschaften_Liegenschaft"):
    return transform(av_file.read(path, layer=layer), source, settings)


def test_column_names_are_matched_in_any_spelling():
    m = find_columns(["EGRIS_EGRID", "NBIdent", "Nummer", "FLAECHENMASS", "geometry"])
    assert m == {
        "egrid": "EGRIS_EGRID",
        "nbident": "NBIdent",
        "parcel_number": "Nummer",
        "area_source_m2": "FLAECHENMASS",
    }
    assert find_columns(["egrid", "nb_ident", "numero"])["parcel_number"] == "numero"
    with pytest.raises(ValueError, match="not in the file"):
        find_columns(["a"], overrides={"egrid": "missing"})


def test_layer_is_found_and_good_parcels_pass(tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(12))
    extract = av_file.read(tmp_gpkg)
    assert extract.layer == "Liegenschaften_Liegenschaft" and extract.municipality_layer
    assert len(extract.sha256) == 64
    out = transform(extract, source, settings)
    assert len(out.rows) == 12 and not out.rejected
    row = out.rows[0]
    assert row["country"] == "CH" and row["canton"] == "XX" and row["egrid"] == "CH999900000000"
    assert row["area_m2"] == 400.0 and row["source_crs"] == "EPSG:2056"
    assert row["source_attributes"]["Note"] == "SYNTHETIC test fixture"
    assert 7.0 < row["geom_wgs84"].centroid.x < 7.6 and 46.8 < row["geom_wgs84"].centroid.y < 47.1


def test_municipality_comes_from_the_boundary_layer(tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(12))
    rows = run(tmp_gpkg, settings, source).rows
    assert {(r["bfs_nr"], r["municipality"]) for r in rows} == {(9901, "Synthetica Nord"), (9902, "Synthetica Süd")}


def test_every_kind_of_bad_record_is_rejected_with_a_reason(tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.broken())
    out = run(tmp_gpkg, settings, source)
    assert dict(out.reasons) == {
        "missing_key": 1,
        "malformed_egrid": 1,
        "empty_geometry": 1,
        "not_polygon": 1,
        "invalid_geometry": 1,
        "exact_duplicate": 1,
        "conflicting_duplicate": 2,
        "duplicate_egrid": 2,
    }
    accepted = {r["parcel_number"]: r for r in out.rows}
    assert set(accepted) == {"101", "204"}
    assert accepted["204"]["geometry_repaired"] and out.repaired == 1
    assert out.warnings["area_differs_from_source"] == 0
    assert all(r["source_attributes"] is not None for r in out.rejected)


def test_area_that_does_not_match_the_source_is_flagged(tmp_gpkg, settings, source):
    rows = fixtures.parcels(2)
    rows[0]["Flaechenmass"] = 450.0
    fixtures.write(tmp_gpkg, rows)
    assert run(tmp_gpkg, settings, source).warnings["area_differs_from_source"] == 1


def test_lv03_is_reprojected_and_other_crs_refused(tmp_gpkg, tmp_path, settings, source):
    lv95 = gpd.GeoDataFrame(fixtures.parcels(2), geometry="geometry", crs=2056)
    lv03 = lv95.to_crs(21781)
    fixtures.write(tmp_gpkg, lv03.to_dict("records"), crs=21781, municipalities=False)
    out = run(tmp_gpkg, settings, source)
    assert out.source_crs == "EPSG:21781" and out.warnings["reprojected_from_lv03"] == 2
    assert 2_599_000 < out.rows[0]["geom"].bounds[0] < 2_601_000
    wgs = tmp_path / "wgs.gpkg"
    fixtures.write(wgs, lv95.to_crs(4326).to_dict("records"), crs=4326, municipalities=False)
    with pytest.raises(ValueError, match="not a Swiss AV reference frame"):
        run(wgs, settings, source)


def test_missing_crs_falls_back_to_the_config(tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(2), crs=None, municipalities=False)
    out = run(tmp_gpkg, settings, source)
    assert out.warnings["crs_from_config"] == 1 and len(out.rows) == 2


def test_canton_column_must_match_the_source(tmp_gpkg, settings, source):
    rows = fixtures.parcels(2)
    rows[0]["Kanton"], rows[1]["Kanton"] = "XX", "ZH"
    fixtures.write(tmp_gpkg, rows, municipalities=False)
    assert dict(run(tmp_gpkg, settings, source).reasons) == {"canton_mismatch": 1}


def test_required_columns_and_hash_stability(tmp_gpkg, settings, source):
    rows = [{k: v for k, v in r.items() if k != "NBIdent"} for r in fixtures.parcels(2)]
    fixtures.write(tmp_gpkg, rows, municipalities=False)
    with pytest.raises(ValueError, match="no layer with parcel numbers"):
        run(tmp_gpkg, settings, source)
    again = tmp_gpkg.with_name("again.gpkg")
    fixtures.write(again, fixtures.parcels(3), municipalities=False)
    first = [r["record_hash"] for r in run(again, settings, source).rows]
    assert first == [r["record_hash"] for r in run(again, settings, source).rows]


def test_arcs_are_stroked_into_polygons(settings, source):
    out = run(Path(__file__).parent / "data" / "synthetic_arc.gpkg", settings, source)
    assert len(out.rows) == 1 and 150 < out.rows[0]["area_m2"] < 158  # half disc of radius 10


def test_numbers_are_joined_from_the_grundstueck_layer(tmp_gpkg, settings, source):
    rows = fixtures.parcels(4)
    geoms = gpd.GeoDataFrame(
        [{"Liegenschaft_von": i + 1, "Flaechenmass": 400.0, "geometry": r["geometry"]} for i, r in enumerate(rows)],
        geometry="geometry",
        crs=2056,
    )
    geoms.to_file(tmp_gpkg, layer="Liegenschaften_Liegenschaft", driver="GPKG", engine="pyogrio")
    attrs = pd.DataFrame(
        [
            {"T_Id": i + 1, "NBIdent": r["NBIdent"], "Nummer": r["Nummer"], "EGRIS_EGRID": r["EGRIS_EGRID"]}
            for i, r in enumerate(rows)
        ]
    )
    pyogrio.write_dataframe(attrs, tmp_gpkg, layer="Liegenschaften_Grundstueck", driver="GPKG")
    extract = av_file.read(tmp_gpkg)
    assert extract.joined_from == "Liegenschaften_Grundstueck"
    out = transform(extract, source, settings)
    assert [r["parcel_number"] for r in out.rows] == ["100", "101", "102", "103"]
    assert out.rows[2]["egrid"] == "CH999900000002"


def test_downloaded_zip_is_unpacked_once_and_hashed_as_downloaded(tmp_path, settings, source):
    import zipfile

    gpkg = fixtures.write(tmp_path / "av_XX_gpkg_lv95.gpkg", fixtures.parcels(3))
    archive = tmp_path / "av_XX_gpkg_lv95.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(gpkg, "av_XX/av_XX.gpkg")
    extract = av_file.read(archive)
    assert extract.sha256 == av_file.sha256(archive) and len(extract.frame) == 3
    folder = tmp_path / f"av_XX_gpkg_lv95_{extract.sha256[:12]}"
    assert (folder / "av_XX" / "av_XX.gpkg").exists()
    assert len(transform(extract, source, settings).rows) == 3


def test_geodienste_layout_picks_resf_and_keeps_validity(tmp_gpkg, settings, source):
    fixtures.geodienste(tmp_gpkg)
    extract = av_file.read(tmp_gpkg)
    assert extract.layer == "resf" and extract.municipality_layer == "mbsf"
    assert extract.dataset_date and len(extract.dataset_date) == 10
    out = transform(extract, dataclasses.replace(source, parcel_type="Liegenschaft"), settings)
    assert len(out.rows) == 4 and not out.rejected
    row = out.rows[0]
    assert row["validity"] == "gueltig" and row["parcel_type"] == "Liegenschaft"
    assert row["bfs_nr"] == 9902 and row["source_dataset_date"] == extract.dataset_date


def test_parts_of_one_parcel_become_one_multipolygon(tmp_gpkg, settings, source):
    fixtures.geodienste(tmp_gpkg, parts=True)
    out = transform(av_file.read(tmp_gpkg), source, settings)
    merged = [r for r in out.rows if r["parcel_number"] == "150"]
    assert len(merged) == 1 and not out.rejected
    assert len(merged[0]["geom"].geoms) == 2 and merged[0]["area_m2"] == 800
    assert merged[0]["area_source_m2"] == 800 and out.warnings["multipart_parcel"] == 1


def test_numpy_and_missing_values_are_stored_as_plain_json():
    import numpy as np

    from app.transformers.parcels import _clean

    assert _clean(np.bool_(True)) is True
    assert _clean(pd.NaT) is None
    assert _clean(np.int64(3)) == 3
