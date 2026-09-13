"""
case_utils.py
-------------
Multi-case helpers: which case IDs to process, where each case's DICOM
and STL files live, and how to pull just that case's rows out of the
single shared biopsy spreadsheet (the biopsy data used to be a
per-case CSV — now it's one xlsx covering all cases, so every case's
rows have to be filtered out of it by patient ID).
"""

import re

import pandas as pd
import config


# Column names the biopsy spreadsheet's patient-ID column might use.
# "Patient Number" is the real column in the shared TCIA spreadsheet;
# the others are kept as fallbacks in case a different export is used.
PATIENT_ID_CANDIDATES = ["Patient Number", "Patient ID", "Patient Id", "PatientID", "Subject ID", "TCIA Patient ID"]


def get_case_ids():
    """
    Case IDs to process, one per output folder.

    The case ID is read directly from the DICOM folder names — every
    immediate subfolder of config.DICOM_BASE (dicom/) is one case,
    named like "Prostate-MRI-US-Biopsy-0396". The dataset
    nests that same folder name a second time inside itself
    (see find_case_dicom_root below), but that inner copy only shows up
    once you go looking for it — the immediate children of DICOM_BASE
    give exactly one folder per case.
    """
    case_ids = sorted(p.name for p in config.DICOM_BASE.iterdir() if p.is_dir())
    if not case_ids:
        raise FileNotFoundError(f"No case folders found under {config.DICOM_BASE}")
    return case_ids


def find_case_dicom_root(case_id):
    """
    Locate the DICOM folder for one case.

    Per the dataset layout, the case-name folder is nested inside
    itself: dicom/prostate_mri_us_biopsy/<case>/prostate_mri_us_biopsy/
    <case>/DICOM_UID.*/MR_*|US_*/*.dcm. Rather than hardcode that
    depth, search for every folder literally named `case_id` under
    DICOM_BASE and keep the deepest match — that's the one that
    actually contains the DICOM_UID.*/MR_*/US_* subfolders, as opposed
    to the outer wrapper folder of the same name.
    """
    candidates = [p for p in config.DICOM_BASE.rglob(case_id) if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(
            f"No DICOM folder named '{case_id}' found under {config.DICOM_BASE}"
        )
    return max(candidates, key=lambda p: len(p.parts))


def resolve_case_paths(case_id):
    """All the per-case paths one case's pipeline run needs."""
    return {
        "dicom_root": find_case_dicom_root(case_id),
        "stl_dir": config.STL_BASE / case_id,
        "output_dir": config.OUTPUT_BASE / case_id,
    }


def _find_column(df, candidates):
    """Return the first candidate column name that actually exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def load_biopsy_table(xlsx_path):
    """Read the single, shared biopsy spreadsheet once for the whole run."""
    df = pd.read_excel(xlsx_path)
    print("Biopsy spreadsheet columns found:", df.columns.tolist())
    return df


def filter_case_rows(df, case_id):
    """
    Return just this case's rows from the full biopsy table.

    The sheet's patient-ID column may store the full case folder name
    ("Prostate-MRI-US-Biopsy-0396"), or just a bare number ("Patient
    Number" holds e.g. 396, with no zero-padding and no prefix) — match
    on either, comparing the number numerically so zero-padding doesn't
    cause a mismatch.
    """
    id_col = _find_column(df, PATIENT_ID_CANDIDATES)
    if id_col is None:
        raise ValueError(
            f"Could not find a patient ID column in the biopsy spreadsheet. "
            f"Actual columns are: {df.columns.tolist()}. "
            f"Add the real header name to PATIENT_ID_CANDIDATES in case_utils.py."
        )

    id_values = df[id_col].astype(str).str.strip()
    mask = id_values.str.contains(case_id, case=False, na=False)

    # Numeric fallback: pull the trailing digits off the case ID
    # ("Prostate-MRI-US-Biopsy-0771" -> 771) and compare that number
    # against the trailing digits of each spreadsheet value, so a bare
    # "771" in "Patient Number" still matches a zero-padded case ID.
    number_match = re.search(r"(\d+)$", case_id)
    if number_match:
        case_number = int(number_match.group(1))
        row_numbers = pd.to_numeric(
            id_values.str.extract(r"(\d+)$", expand=False), errors="coerce"
        )
        mask = mask | (row_numbers == case_number)

    subset = df[mask]

    if subset.empty:
        print(f"WARNING: no biopsy rows matched case '{case_id}' in column '{id_col}'")

    return subset


def save_case_biopsy_csv(case_rows, case_id, output_dir):
    """
    Write this case's filtered biopsy rows to <output_dir>/biopsy_tracks.csv.

    Not required by the pipeline — build_tubes() works directly off the
    in-memory dataframe from filter_case_rows(), the same as the pilot
    study's per-case CSV did. This is purely a per-case audit artifact,
    so a matching bug (wrong rows, or no rows) is visible by opening one
    file instead of re-deriving it or reading console warnings.
    """
    out_path = output_dir / "biopsy_tracks.csv"
    case_rows.to_csv(out_path, index=False)
    print(f"Saved {len(case_rows)} biopsy row(s) for {case_id} -> {out_path}")
    return out_path