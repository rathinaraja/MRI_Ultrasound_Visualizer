#!/usr/bin/env python3
"""
03_extract_biopsy_case_0396.py

Extract the 17 biopsy records for case 0396, validate MRI coordinates,
and assign the professor's requested tube classes and colors.

Run:
    python 03_extract_biopsy_case_0396.py \
        --excel "TCIA-Biopsy-Data_2020-07-14.xlsx" \
        --output D:/TCIA_case_0396/biopsy
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


PATIENT_ID = "Prostate-MRI-US-Biopsy-0396"

MRI_COORDINATE_COLUMNS = [
    "Bx Tip X (MRI Coord)",
    "Bx Tip Y (MRI Coord)",
    "Bx Tip Z (MRI Coord)",
    "Bx Base X (MRI Coord)",
    "Bx Base Y (MRI Coord)",
    "Bx Base Z (MRI Coord)",
]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Extract and validate biopsy rows for {PATIENT_ID}."
    )
    parser.add_argument(
        "--excel",
        type=Path,
        required=True,
        help="Path to the TCIA biopsy Excel workbook.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory where the cleaned case-level CSV will be saved.",
    )
    return parser.parse_args()


def classify_biopsy(primary: float, secondary: float) -> tuple[str, str]:
    """Return the tube class and display color required by the task."""
    primary_missing = pd.isna(primary)
    secondary_missing = pd.isna(secondary)

    if primary_missing and secondary_missing:
        return "benign", "blue"

    if primary_missing != secondary_missing:
        return "incomplete_gleason", "review"

    if int(primary) == 3 and int(secondary) == 3:
        return "gleason_3_plus_3", "orange"

    return "higher_grade", "red"


def validate_mri_coordinates(row: pd.Series) -> tuple[bool, str, float]:
    """Check missing values, -1000 placeholders, and zero-length tracks."""
    coordinates = pd.to_numeric(
        row[MRI_COORDINATE_COLUMNS],
        errors="coerce",
    ).to_numpy(dtype=float)

    if np.isnan(coordinates).any():
        return False, "missing_or_non_numeric_coordinate", np.nan

    if np.isclose(coordinates, -1000.0).any():
        return False, "contains_minus_1000_placeholder", np.nan

    tip = coordinates[0:3]
    base = coordinates[3:6]
    length_mm = float(np.linalg.norm(tip - base))

    if np.isclose(length_mm, 0.0):
        return False, "tip_and_base_are_identical", length_mm

    return True, "valid", length_mm


def main() -> None:
    args = parse_arguments()
    args.output.mkdir(parents=True, exist_ok=True)

    biopsy_table = pd.read_excel(args.excel)

    missing_columns = [
        column
        for column in ["Patient Number", "Primary Gleason", "Secondary Gleason"]
        + MRI_COORDINATE_COLUMNS
        if column not in biopsy_table.columns
    ]
    if missing_columns:
        raise KeyError(
            "The Excel workbook is missing required columns: "
            + ", ".join(missing_columns)
        )

    case_table = biopsy_table.loc[
        biopsy_table["Patient Number"].astype(str) == PATIENT_ID
    ].copy()

    if case_table.empty:
        raise RuntimeError(f"No biopsy rows were found for {PATIENT_ID}.")

    validations = case_table.apply(validate_mri_coordinates, axis=1)
    case_table["valid_mri_coordinates"] = [
        result[0] for result in validations
    ]
    case_table["coordinate_status"] = [
        result[1] for result in validations
    ]
    case_table["track_length_mm"] = [
        result[2] for result in validations
    ]

    classifications = case_table.apply(
        lambda row: classify_biopsy(
            row["Primary Gleason"],
            row["Secondary Gleason"],
        ),
        axis=1,
    )
    case_table["tube_class"] = [
        result[0] for result in classifications
    ]
    case_table["tube_color"] = [
        result[1] for result in classifications
    ]

    output_path = args.output / "case_0396_biopsy_tracks.csv"
    case_table.to_csv(output_path, index=False)

    print(f"\nPatient: {PATIENT_ID}")
    print(f"Biopsy rows: {len(case_table)}")
    print(
        "Valid MRI tracks: "
        f"{int(case_table['valid_mri_coordinates'].sum())}/{len(case_table)}"
    )
    print("\nTube classes:")
    print(case_table["tube_class"].value_counts(dropna=False).to_string())
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
