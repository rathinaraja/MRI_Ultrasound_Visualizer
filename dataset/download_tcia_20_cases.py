#!/usr/bin/env python3
"""Download the 20 selected Prostate-MRI-US-Biopsy cases.

What this script does
---------------------
1. Queries the NCI Imaging Data Commons (IDC) index for every MR and US DICOM
   series belonging to the 20 selected PatientIDs.
2. Saves a reproducible series manifest before downloading anything.
3. Downloads the DICOM series patient-by-patient so interrupted runs can be
   restarted without changing the cohort definition.
4. Downloads the TCIA biopsy and target spreadsheets.
5. Optionally calls IBM Aspera CLI (ascli) to retrieve the official STL and
   biopsy-overlay packages distributed by TCIA.
6. Extracts ZIP archives and copies only files/folders relevant to the 20 cases.

Requirements
------------
Python >= 3.10
pip install --upgrade idc-index pandas requests tqdm

Optional for STL/overlay package retrieval
------------------------------------------
Install IBM Aspera CLI (`ascli`) and its transfer runtime, then run:
    ascli config transferd install

Examples
--------
Query and download DICOM + spreadsheets:
    python download_tcia_20_cases.py --output D:/TCIA_20_cases

Only create the manifest, without downloading DICOM:
    python download_tcia_20_cases.py --output D:/TCIA_20_cases --query-only

Also attempt the official Aspera package downloads:
    python download_tcia_20_cases.py --output D:/TCIA_20_cases --with-aspera

After manually downloading the TCIA STL/overlay ZIPs into supporting/packages:
    python download_tcia_20_cases.py --output D:/TCIA_20_cases --skip-dicom --organize-support
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from idc_index import IDCClient


COLLECTION_ID = "prostate_mri_us_biopsy"

PATIENT_IDS = [
    "Prostate-MRI-US-Biopsy-0396",
    "Prostate-MRI-US-Biopsy-1141",
    "Prostate-MRI-US-Biopsy-0021",
    "Prostate-MRI-US-Biopsy-0090",
    "Prostate-MRI-US-Biopsy-1099",
    "Prostate-MRI-US-Biopsy-1072",
    "Prostate-MRI-US-Biopsy-0239",
    "Prostate-MRI-US-Biopsy-1122",
    "Prostate-MRI-US-Biopsy-0201",
    "Prostate-MRI-US-Biopsy-0338",
    "Prostate-MRI-US-Biopsy-0817",
    "Prostate-MRI-US-Biopsy-0332",
    "Prostate-MRI-US-Biopsy-0915",
    "Prostate-MRI-US-Biopsy-0434",
    "Prostate-MRI-US-Biopsy-0992",
    "Prostate-MRI-US-Biopsy-1126",
    "Prostate-MRI-US-Biopsy-0922",
    "Prostate-MRI-US-Biopsy-0771",
    "Prostate-MRI-US-Biopsy-0062",
    "Prostate-MRI-US-Biopsy-0943",
]

SUPPORTING_URLS = {
    "TCIA-Biopsy-Data_2020-07-14.xlsx": (
        "https://wiki.cancerimagingarchive.net/download/attachments/68550661/"
        "TCIA%20Biopsy%20Data_2020-07-14.xlsx?api=v2"
    ),
    "Target-Data_2019-12-05.xlsx": (
        "https://wiki.cancerimagingarchive.net/download/attachments/68550661/"
        "Target-Data_2019-12-05%20%282%29.xlsx?api=v2"
    ),
}

# Official public TCIA Faspex links. These are legacy external packages.
ASPERA_PACKAGE_LINKS = {
    "stl": (
        "https://faspex.cancerimagingarchive.net/aspera/faspex?context="
        "eyJyZXNvdXJjZSI6InBhY2thZ2VzIiwidHlwZSI6ImV4dGVybmFsX2Rvd25sb2FkX3BhY2thZ2UiLCJpZCI6IjYzNSIsInBhc3Njb2RlIjoiNzZkZDBhOWY2Y2YzZjQ1OGQ0ODZlOWE4OTRiOGExMjRjNmNkOGUwNyIsInBhY2thZ2VfaWQiOiI2MzUiLCJlbWFpbCI6ImhlbHBAY2FuY2VyaW1hZ2luZ2FyY2hpdmUubmV0In0%3D"
    ),
    "biopsy_overlays": (
        "https://faspex.cancerimagingarchive.net/aspera/faspex?context="
        "eyJyZXNvdXJjZSI6InBhY2thZ2VzIiwidHlwZSI6ImV4dGVybmFsX2Rvd25sb2FkX3BhY2thZ2UiLCJpZCI6IjYzMyIsInBhc3Njb2RlIjoiZjY3MzUxMGUyMGY5OGY3YzFhMDE4MDBmZWFjYTRiYWZiYjFjNDE4NCIsInBhY2thZ2VfaWQiOiI2MzMiLCJlbWFpbCI6ImhlbHBAY2FuY2VyaW1hZ2luZ2FyY2hpdmUubmV0In0%3D"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download 20 selected TCIA prostate MRI/US biopsy cases."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("TCIA_20_cases"),
        help="Root output directory (default: ./TCIA_20_cases).",
    )
    parser.add_argument(
        "--query-only",
        action="store_true",
        help="Create manifests but do not download DICOM files.",
    )
    parser.add_argument(
        "--skip-dicom",
        action="store_true",
        help="Skip both the IDC query and DICOM download.",
    )
    parser.add_argument(
        "--skip-spreadsheets",
        action="store_true",
        help="Do not download the TCIA biopsy and target spreadsheets.",
    )
    parser.add_argument(
        "--with-aspera",
        action="store_true",
        help="Use installed ascli to download the official STL and overlay packages.",
    )
    parser.add_argument(
        "--organize-support",
        action="store_true",
        help="Extract package ZIPs and copy only files for the selected 20 cases.",
    )
    return parser.parse_args()


def create_directories(root: Path) -> dict[str, Path]:
    paths = {
        "root": root,
        "dicom": root / "dicom",
        "manifests": root / "manifests",
        "spreadsheets": root / "supporting" / "spreadsheets",
        "packages": root / "supporting" / "packages",
        "extracted": root / "supporting" / "extracted",
        "selected_stl": root / "supporting" / "selected_stl",
        "selected_overlays": root / "supporting" / "selected_overlays",
        "logs": root / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def sql_string_list(values: Iterable[str]) -> str:
    """Return SQL-safe quoted literals for a fixed trusted list."""
    return ",\n        ".join("'" + value.replace("'", "''") + "'" for value in values)


def query_selected_series(client: IDCClient) -> pd.DataFrame:
    """Find all MR and US series for the selected patients in the IDC collection."""
    patient_literals = sql_string_list(PATIENT_IDS)
    query = f"""
    SELECT
        collection_id,
        PatientID,
        StudyInstanceUID,
        SeriesInstanceUID,
        Modality,
        SeriesDescription,
        series_size_MB
    FROM index
    WHERE collection_id = '{COLLECTION_ID}'
      AND PatientID IN (
        {patient_literals}
      )
      AND Modality IN ('MR', 'US')
    ORDER BY PatientID, Modality, SeriesDescription, SeriesInstanceUID
    """
    result = client.sql_query(query)
    if result.empty:
        raise RuntimeError(
            "IDC returned no rows. Upgrade idc-index and verify internet access."
        )
    return result.drop_duplicates(subset=["SeriesInstanceUID"]).reset_index(drop=True)


def validate_manifest(series_df: pd.DataFrame) -> pd.DataFrame:
    """Check that all requested patients and both modalities are represented."""
    found_patients = set(series_df["PatientID"].dropna().astype(str))
    missing_patients = sorted(set(PATIENT_IDS) - found_patients)
    if missing_patients:
        raise RuntimeError(
            "The following requested PatientIDs were not found in IDC:\n"
            + "\n".join(missing_patients)
        )

    summary = (
        series_df.groupby(["PatientID", "Modality"], dropna=False)
        .agg(
            series_count=("SeriesInstanceUID", "nunique"),
            total_size_MB=("series_size_MB", "sum"),
        )
        .reset_index()
    )
    pivot = summary.pivot(
        index="PatientID", columns="Modality", values="series_count"
    ).fillna(0)

    missing_mr = pivot.index[pivot.get("MR", 0) == 0].tolist()
    missing_us = pivot.index[pivot.get("US", 0) == 0].tolist()
    if missing_mr or missing_us:
        message = []
        if missing_mr:
            message.append("Missing MR: " + ", ".join(missing_mr))
        if missing_us:
            message.append("Missing US: " + ", ".join(missing_us))
        raise RuntimeError("Manifest validation failed. " + " | ".join(message))

    return summary


def save_manifests(
    series_df: pd.DataFrame, summary_df: pd.DataFrame, manifest_dir: Path
) -> None:
    (manifest_dir / "selected_patients.txt").write_text(
        "\n".join(PATIENT_IDS) + "\n", encoding="utf-8"
    )
    series_df.to_csv(manifest_dir / "selected_series.csv", index=False)
    summary_df.to_csv(manifest_dir / "patient_modality_summary.csv", index=False)

    metadata = {
        "collection_id": COLLECTION_ID,
        "number_of_requested_patients": len(PATIENT_IDS),
        "number_of_series": int(series_df["SeriesInstanceUID"].nunique()),
        "modalities": sorted(series_df["Modality"].dropna().unique().tolist()),
        "estimated_total_size_MB": float(series_df["series_size_MB"].fillna(0).sum()),
    }
    (manifest_dir / "download_summary.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def download_dicom_by_patient(
    client: IDCClient, series_df: pd.DataFrame, dicom_root: Path
) -> None:
    """Download one patient's complete MR/US series selection at a time."""
    for patient_id in PATIENT_IDS:
        patient_rows = series_df.loc[series_df["PatientID"] == patient_id]
        series_uids = patient_rows["SeriesInstanceUID"].dropna().astype(str).tolist()
        patient_dir = dicom_root / patient_id
        patient_dir.mkdir(parents=True, exist_ok=True)

        if not series_uids:
            print(f"[WARNING] No series found for {patient_id}; skipping.")
            continue

        print(
            f"\nDownloading {patient_id}: {len(series_uids)} MR/US series "
            f"into {patient_dir}"
        )
        client.download_dicom_series(
            seriesInstanceUID=series_uids,
            downloadDir=str(patient_dir),
        )


def download_file(url: str, destination: Path) -> None:
    """Stream a public supporting file to disk with basic integrity checks."""
    if destination.exists() and destination.stat().st_size > 0:
        print(f"Already present, skipping: {destination}")
        return

    print(f"Downloading supporting file: {destination.name}")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as output_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)

    if destination.stat().st_size == 0:
        raise RuntimeError(f"Downloaded file is empty: {destination}")


def download_spreadsheets(spreadsheet_dir: Path) -> None:
    for filename, url in SUPPORTING_URLS.items():
        download_file(url, spreadsheet_dir / filename)


def run_aspera_downloads(package_dir: Path) -> None:
    """Call IBM ascli for TCIA's official public Faspex packages."""
    ascli = shutil.which("ascli")
    if ascli is None:
        raise RuntimeError(
            "ascli was not found. Install IBM Aspera CLI and run "
            "'ascli config transferd install', or download the two packages "
            "manually from the TCIA collection page into supporting/packages."
        )

    for package_name, public_link in ASPERA_PACKAGE_LINKS.items():
        destination = package_dir / package_name
        destination.mkdir(parents=True, exist_ok=True)
        command = [
            ascli,
            "faspex",
            "package",
            "receive",
            f"--link={public_link}",
            f"--to-folder={destination}",
        ]
        print("\nRunning:", " ".join(command[:4]), "<public-link>", command[-1])
        subprocess.run(command, check=True)


def extract_all_zip_files(package_dir: Path, extracted_dir: Path) -> list[Path]:
    extracted_roots: list[Path] = []
    zip_files = sorted(package_dir.rglob("*.zip"))
    if not zip_files:
        print(
            "No ZIP files found under supporting/packages. "
            "Download the STL and biopsy-overlay packages first."
        )
        return extracted_roots

    for zip_path in zip_files:
        destination = extracted_dir / zip_path.stem
        marker = destination / ".extracted_complete"
        if marker.exists():
            extracted_roots.append(destination)
            continue

        destination.mkdir(parents=True, exist_ok=True)
        print(f"Extracting {zip_path.name} -> {destination}")
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(destination)
        marker.write_text("complete\n", encoding="utf-8")
        extracted_roots.append(destination)

    return extracted_roots


def copy_selected_supporting_files(
    extracted_dir: Path, selected_stl_dir: Path, selected_overlay_dir: Path
) -> None:
    """Copy selected STL and biopsy-overlay files based on PatientID text."""
    all_files = [path for path in extracted_dir.rglob("*") if path.is_file()]
    copied_stl = 0
    copied_overlay_files = 0

    for patient_id in PATIENT_IDS:
        patient_stl_dir = selected_stl_dir / patient_id
        patient_overlay_dir = selected_overlay_dir / patient_id

        for source in all_files:
            source_text = str(source)
            if patient_id not in source_text:
                continue

            suffix = source.suffix.lower()
            if suffix == ".stl":
                patient_stl_dir.mkdir(parents=True, exist_ok=True)
                destination = patient_stl_dir / source.name
                shutil.copy2(source, destination)
                copied_stl += 1
            elif suffix in {".mrml", ".fcsv", ".vtk", ".json", ".txt"}:
                patient_overlay_dir.mkdir(parents=True, exist_ok=True)
                relative_name = "__".join(source.parts[-3:])
                destination = patient_overlay_dir / relative_name
                shutil.copy2(source, destination)
                copied_overlay_files += 1

    print(f"Copied {copied_stl} STL files for the selected cases.")
    print(f"Copied {copied_overlay_files} overlay-related files.")

    missing_stl = [
        patient_id
        for patient_id in PATIENT_IDS
        if not any((selected_stl_dir / patient_id).glob("*.STL"))
        and not any((selected_stl_dir / patient_id).glob("*.stl"))
    ]
    if missing_stl:
        print(
            "[WARNING] No selected STL files were found for:\n  "
            + "\n  ".join(missing_stl)
        )


def main() -> int:
    args = parse_args()
    paths = create_directories(args.output.resolve())

    print(f"Output root: {paths['root']}")
    print(f"Selected patients: {len(PATIENT_IDS)}")

    if not args.skip_dicom:
        client = IDCClient.client()
        series_df = query_selected_series(client)
        summary_df = validate_manifest(series_df)
        save_manifests(series_df, summary_df, paths["manifests"])

        print("\nSeries manifest created successfully.")
        print(summary_df.to_string(index=False))
        print(
            "Estimated selected DICOM size: "
            f"{series_df['series_size_MB'].fillna(0).sum() / 1024:.2f} GB"
        )

        if not args.query_only:
            download_dicom_by_patient(client, series_df, paths["dicom"])
    else:
        print("Skipping IDC query and DICOM download.")

    if not args.skip_spreadsheets:
        download_spreadsheets(paths["spreadsheets"])

    if args.with_aspera:
        run_aspera_downloads(paths["packages"])

    if args.organize_support:
        extract_all_zip_files(paths["packages"], paths["extracted"])
        copy_selected_supporting_files(
            paths["extracted"],
            paths["selected_stl"],
            paths["selected_overlays"],
        )

    print("\nFinished.")
    print("Next: inspect manifests/selected_series.csv before loading data in 3D Slicer.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Re-run the same command to resume.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001 - top-level user-facing error handler
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
