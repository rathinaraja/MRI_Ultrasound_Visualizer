#!/usr/bin/env python3
"""
01_download_case_0396.py

Query and download every MR and US DICOM series associated with one TCIA patient.

Run a metadata-only query first:
    python 01_download_case_0396.py --output D:/TCIA_case_0396 --query-only

Then download:
    python 01_download_case_0396.py --output D:/TCIA_case_0396
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from idc_index import IDCClient


PATIENT_ID = "Prostate-MRI-US-Biopsy-0396"


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments supplied by the user."""
    parser = argparse.ArgumentParser(
        description=f"Download all MR and US DICOM series for {PATIENT_ID}."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("TCIA_case_0396"),
        help="Root directory for the manifest and downloaded DICOM data.",
    )
    parser.add_argument(
        "--query-only",
        action="store_true",
        help="Create the series manifest without downloading image files.",
    )
    return parser.parse_args()


def query_case_series(client: IDCClient) -> pd.DataFrame:
    """Return one row for every MR or US series belonging to the patient."""
    query = f"""
    SELECT
        collection_id,
        PatientID,
        StudyInstanceUID,
        SeriesInstanceUID,
        Modality,
        SeriesDescription,
        BodyPartExamined,
        Manufacturer,
        ManufacturerModelName,
        series_size_MB
    FROM index
    WHERE PatientID = '{PATIENT_ID}'
      AND Modality IN ('MR', 'US')
    ORDER BY collection_id, StudyInstanceUID, Modality, SeriesDescription
    """

    series_table = client.sql_query(query)

    if series_table.empty:
        raise RuntimeError(
            f"No MR/US series were found for {PATIENT_ID}. "
            "Check internet access and upgrade idc-index."
        )

    return (
        series_table
        .drop_duplicates(subset=["SeriesInstanceUID"])
        .reset_index(drop=True)
    )


def save_manifest(series_table: pd.DataFrame, manifest_path: Path) -> None:
    """Save the exact series selection before downloading any pixel data."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    series_table.to_csv(manifest_path, index=False)


def validate_modalities(series_table: pd.DataFrame) -> None:
    """Stop if either MRI or ultrasound is absent."""
    modalities = set(series_table["Modality"].dropna().astype(str))

    missing = {"MR", "US"} - modalities
    if missing:
        raise RuntimeError(
            "The case is missing required modality/modalities: "
            + ", ".join(sorted(missing))
        )


def download_series(
    client: IDCClient,
    series_table: pd.DataFrame,
    dicom_directory: Path,
) -> None:
    """Download every series listed in the verified manifest."""
    dicom_directory.mkdir(parents=True, exist_ok=True)

    series_uids = (
        series_table["SeriesInstanceUID"]
        .dropna()
        .astype(str)
        .tolist()
    )

    client.download_dicom_series(
        seriesInstanceUID=series_uids,
        downloadDir=str(dicom_directory),
    )


def main() -> None:
    """Coordinate the query, validation, manifest creation, and download."""
    args = parse_arguments()
    root = args.output.resolve()
    manifest_path = root / "manifests" / "case_0396_series.csv"
    dicom_directory = root / "dicom"

    client = IDCClient.client()
    series_table = query_case_series(client)
    validate_modalities(series_table)
    save_manifest(series_table, manifest_path)

    print("\nSeries selected for download:")
    print(series_table.to_string(index=False))

    total_mb = series_table["series_size_MB"].fillna(0).sum()
    print(f"\nNumber of series: {len(series_table)}")
    print(f"Estimated size: {total_mb:.1f} MB")
    print(f"Manifest: {manifest_path}")

    if args.query_only:
        print("\nQuery-only mode: no DICOM files were downloaded.")
        return

    download_series(client, series_table, dicom_directory)
    print(f"\nDICOM download completed under: {dicom_directory}")


if __name__ == "__main__":
    main()
