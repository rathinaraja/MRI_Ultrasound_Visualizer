#!/usr/bin/env python3
"""
02_inventory_dicom_case_0396.py

Read downloaded DICOM headers without loading pixel data. Create:
1. One row per DICOM file.
2. One summary row per DICOM series.

Run:
    python 02_inventory_dicom_case_0396.py \
        --dicom-root D:/TCIA_case_0396/dicom \
        --output D:/TCIA_case_0396/inventory
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import pydicom
from pydicom.errors import InvalidDicomError


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a DICOM metadata inventory for case 0396."
    )
    parser.add_argument(
        "--dicom-root",
        type=Path,
        required=True,
        help="Directory containing the downloaded DICOM files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory where inventory CSV files will be written.",
    )
    return parser.parse_args()


def readable_value(value: Any) -> str | int | float | None:
    """Convert DICOM values and lists into CSV-friendly values."""
    if value is None:
        return None

    if isinstance(value, (str, int, float)):
        return value

    if isinstance(value, bytes):
        return value.decode(errors="replace")

    try:
        return "\\".join(str(item) for item in value)
    except TypeError:
        return str(value)


def read_dicom_header(file_path: Path) -> dict[str, Any] | None:
    """Read metadata only; return None when the file is not valid DICOM."""
    try:
        dataset = pydicom.dcmread(
            file_path,
            stop_before_pixels=True,
            force=False,
        )
    except (InvalidDicomError, OSError):
        return None

    return {
        "file_path": str(file_path.resolve()),
        "PatientID": readable_value(dataset.get("PatientID")),
        "StudyInstanceUID": readable_value(dataset.get("StudyInstanceUID")),
        "SeriesInstanceUID": readable_value(dataset.get("SeriesInstanceUID")),
        "SOPInstanceUID": readable_value(dataset.get("SOPInstanceUID")),
        "Modality": readable_value(dataset.get("Modality")),
        "SeriesDescription": readable_value(dataset.get("SeriesDescription")),
        "ProtocolName": readable_value(dataset.get("ProtocolName")),
        "ImageType": readable_value(dataset.get("ImageType")),
        "Rows": readable_value(dataset.get("Rows")),
        "Columns": readable_value(dataset.get("Columns")),
        "NumberOfFrames": readable_value(dataset.get("NumberOfFrames")),
        "InstanceNumber": readable_value(dataset.get("InstanceNumber")),
        "ImagePositionPatient": readable_value(
            dataset.get("ImagePositionPatient")
        ),
        "ImageOrientationPatient": readable_value(
            dataset.get("ImageOrientationPatient")
        ),
        "PixelSpacing": readable_value(dataset.get("PixelSpacing")),
        "SliceThickness": readable_value(dataset.get("SliceThickness")),
        "SpacingBetweenSlices": readable_value(
            dataset.get("SpacingBetweenSlices")
        ),
        "FrameOfReferenceUID": readable_value(
            dataset.get("FrameOfReferenceUID")
        ),
        "MagneticFieldStrength": readable_value(
            dataset.get("MagneticFieldStrength")
        ),
        "RepetitionTime": readable_value(dataset.get("RepetitionTime")),
        "EchoTime": readable_value(dataset.get("EchoTime")),
        "DiffusionBValue": readable_value(dataset.get("DiffusionBValue")),
        "Manufacturer": readable_value(dataset.get("Manufacturer")),
        "ManufacturerModelName": readable_value(
            dataset.get("ManufacturerModelName")
        ),
    }


def create_instance_inventory(dicom_root: Path) -> pd.DataFrame:
    """Recursively inspect every file below the selected directory."""
    records: list[dict[str, Any]] = []

    for file_path in sorted(path for path in dicom_root.rglob("*") if path.is_file()):
        record = read_dicom_header(file_path)
        if record is not None:
            records.append(record)

    if not records:
        raise RuntimeError(
            f"No readable DICOM files were found under {dicom_root.resolve()}."
        )

    return pd.DataFrame(records)


def first_nonmissing(series: pd.Series) -> Any:
    """Return the first non-empty value found within one series."""
    nonmissing = series.dropna()
    if nonmissing.empty:
        return None
    return nonmissing.iloc[0]


def create_series_summary(instance_table: pd.DataFrame) -> pd.DataFrame:
    """Collapse file-level metadata into one row per SeriesInstanceUID."""
    summary = (
        instance_table
        .groupby("SeriesInstanceUID", dropna=False)
        .agg(
            PatientID=("PatientID", first_nonmissing),
            StudyInstanceUID=("StudyInstanceUID", first_nonmissing),
            Modality=("Modality", first_nonmissing),
            SeriesDescription=("SeriesDescription", first_nonmissing),
            ProtocolName=("ProtocolName", first_nonmissing),
            ImageType=("ImageType", first_nonmissing),
            file_count=("file_path", "count"),
            Rows=("Rows", first_nonmissing),
            Columns=("Columns", first_nonmissing),
            NumberOfFrames=("NumberOfFrames", first_nonmissing),
            PixelSpacing=("PixelSpacing", first_nonmissing),
            SliceThickness=("SliceThickness", first_nonmissing),
            FrameOfReferenceUID=("FrameOfReferenceUID", first_nonmissing),
            DiffusionBValue=("DiffusionBValue", first_nonmissing),
            Manufacturer=("Manufacturer", first_nonmissing),
            ManufacturerModelName=("ManufacturerModelName", first_nonmissing),
        )
        .reset_index()
        .sort_values(["Modality", "SeriesDescription", "SeriesInstanceUID"])
    )
    return summary


def main() -> None:
    args = parse_arguments()
    args.output.mkdir(parents=True, exist_ok=True)

    instance_table = create_instance_inventory(args.dicom_root)
    series_summary = create_series_summary(instance_table)

    instance_path = args.output / "case_0396_dicom_instances.csv"
    summary_path = args.output / "case_0396_series_summary.csv"

    instance_table.to_csv(instance_path, index=False)
    series_summary.to_csv(summary_path, index=False)

    print("\nDICOM series summary:")
    print(series_summary.to_string(index=False))
    print(f"\nReadable DICOM files: {len(instance_table)}")
    print(f"Distinct series: {series_summary['SeriesInstanceUID'].nunique()}")
    print(f"Instance inventory: {instance_path}")
    print(f"Series summary: {summary_path}")


if __name__ == "__main__":
    main()
