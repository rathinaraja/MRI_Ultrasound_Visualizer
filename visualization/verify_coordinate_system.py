r"""
verify_coordinate_system.py
-----------------------------
Standalone diagnostic — not part of the main pipeline. Settles whether
the biopsy spreadsheet's "Bx Tip/Base (MRI Coord)" values should be
used raw, or with X/Y negated (config.CONVERT_LPS_TO_RAS), by checking
them against TCIA's own known-correct ground truth: the .fcsv fiducial
overlay file shipped with the dataset under
supporting/selected_overlays/<case>/*.fcsv.

Two independent checks are run:
  1. The .fcsv file's own header line declares its coordinate system
     ("# CoordinateSystem = RAS" or "LPS") — Slicer writes this
     directly into the file, so it's not a guess.
  2. Every spreadsheet Tip/Base point is matched against the nearest
     point in the .fcsv file, once using the raw coordinates and once
     with X/Y negated. Whichever hypothesis gives near-zero distances
     is the one to use for CONVERT_LPS_TO_RAS.

Run:
    python verify_coordinate_system.py --fcsv "path\to\case.fcsv" --xlsx "path\to\TCIA-Biopsy-Data_2020-07-14.xlsx" --case-id "Prostate-MRI-US-Biopsy-0396"
"""

import argparse
import re

import numpy as np
import pandas as pd


TIP_X_CANDIDATES = ["Bx Tip X (MRI Coord)", "Bx_Tip_X_MRI_Coord", "Tip_X"]
TIP_Y_CANDIDATES = ["Bx Tip Y (MRI Coord)", "Bx_Tip_Y_MRI_Coord", "Tip_Y"]
TIP_Z_CANDIDATES = ["Bx Tip Z (MRI Coord)", "Bx_Tip_Z_MRI_Coord", "Tip_Z"]
BASE_X_CANDIDATES = ["Bx Base X (MRI Coord)", "Bx_Base_X_MRI_Coord", "Base_X"]
BASE_Y_CANDIDATES = ["Bx Base Y (MRI Coord)", "Bx_Base_Y_MRI_Coord", "Base_Y"]
BASE_Z_CANDIDATES = ["Bx Base Z (MRI Coord)", "Bx_Base_Z_MRI_Coord", "Base_Z"]
PATIENT_ID_CANDIDATES = ["Patient Number", "Patient ID", "Patient Id", "PatientID", "Subject ID"]
MISSING_COORD_MAGNITUDE = 1000  # see 02_build_biopsy_tubes.py — placeholder for missing data


def _find_column(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def parse_fcsv(fcsv_path):
    """
    Parse a Slicer Markups fiducial .fcsv file.

    Returns
    -------
    coordinate_system : str — the file's declared "# CoordinateSystem = ..." value, or "" if absent
    points : list of (x, y, z) tuples — every control point in the file
    """
    coordinate_system = ""
    points = []

    with open(fcsv_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                match = re.search(r"CoordinateSystem\s*=\s*(\w+)", line, re.IGNORECASE)
                if match:
                    coordinate_system = match.group(1).upper()
                continue
            # Data row: id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID
            fields = line.split(",")
            if len(fields) < 4:
                continue
            try:
                x, y, z = float(fields[1]), float(fields[2]), float(fields[3])
                points.append((x, y, z))
            except ValueError:
                continue

    return coordinate_system, points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fcsv", required=True, help="Path to the case's .fcsv overlay file")
    parser.add_argument("--xlsx", required=True, help="Path to TCIA-Biopsy-Data_2020-07-14.xlsx")
    parser.add_argument("--case-id", required=True, help='e.g. "Prostate-MRI-US-Biopsy-0396"')
    args = parser.parse_args()

    print(f"Reading {args.fcsv} ...")
    coordinate_system, fcsv_points = parse_fcsv(args.fcsv)
    print(f"  Declared CoordinateSystem header: {coordinate_system or '(not found in file)'}")
    print(f"  {len(fcsv_points)} point(s) found")

    print(f"  Parsed points (raw, as read from the file):")
    for i, p in enumerate(fcsv_points):
        print(f"    point {i}: {p}")

    print(f"\nReading {args.xlsx} ...")
    df = pd.read_excel(args.xlsx)

    id_col = _find_column(df, PATIENT_ID_CANDIDATES)
    if id_col is None:
        raise ValueError(f"No patient ID column found. Columns: {df.columns.tolist()}")

    case_rows = df[df[id_col].astype(str).str.strip() == args.case_id]
    print(f"  {len(case_rows)} row(s) found for {args.case_id}")

    tip_x_col = _find_column(df, TIP_X_CANDIDATES)
    tip_y_col = _find_column(df, TIP_Y_CANDIDATES)
    tip_z_col = _find_column(df, TIP_Z_CANDIDATES)
    base_x_col = _find_column(df, BASE_X_CANDIDATES)
    base_y_col = _find_column(df, BASE_Y_CANDIDATES)
    base_z_col = _find_column(df, BASE_Z_CANDIDATES)
    coord_cols = [tip_x_col, tip_y_col, tip_z_col, base_x_col, base_y_col, base_z_col]
    label_col = _find_column(df, ["Core Label"])

    has_placeholder = (case_rows[coord_cols].abs() == MISSING_COORD_MAGNITUDE).any(axis=1)
    n_dropped = int(has_placeholder.sum())
    if n_dropped:
        print(f"  Skipping {n_dropped} core(s) with missing MRI coordinates (placeholder)")
    case_rows = case_rows[~has_placeholder]

    if len(fcsv_points) != 2:
        print(f"\nWARNING: expected exactly 2 points (tip, base) for a single-core "
              f".fcsv file, found {len(fcsv_points)}. Proceeding anyway, but results "
              f"below may not be meaningful.")

    # A single-core .fcsv (like the "...__Bx-2-Benign.fcsv" naming pattern)
    # holds just this one core's tip and base — not every core in the case.
    # So rather than averaging distance across all cores (which dilutes the
    # signal with 16 unrelated cores), find the ONE row whose tip/base
    # actually corresponds to these 2 points, under every combination of:
    #   - raw vs X/Y-flipped spreadsheet coordinates
    #   - fcsv point order = (tip, base) vs (base, tip) — line control point
    #     order isn't guaranteed, so try both
    a, b = fcsv_points[0], fcsv_points[1]
    point_orderings = [("tip=point0, base=point1", a, b), ("tip=point1, base=point0", b, a)]

    best = None  # (total_distance, row_label, hypothesis, ordering_desc)
    for _, row in case_rows.iterrows():
        row_label = row[label_col] if label_col else "(no label column)"
        raw_tip = np.array([row[tip_x_col], row[tip_y_col], row[tip_z_col]])
        raw_base = np.array([row[base_x_col], row[base_y_col], row[base_z_col]])
        flipped_tip = np.array([-raw_tip[0], -raw_tip[1], raw_tip[2]])
        flipped_base = np.array([-raw_base[0], -raw_base[1], raw_base[2]])

        for hyp_name, sheet_tip, sheet_base in [("RAW", raw_tip, raw_base), ("X/Y-FLIPPED", flipped_tip, flipped_base)]:
            for order_desc, fcsv_tip, fcsv_base in point_orderings:
                total = np.linalg.norm(sheet_tip - np.array(fcsv_tip)) + np.linalg.norm(sheet_base - np.array(fcsv_base))
                if best is None or total < best[0]:
                    best = (total, row_label, hyp_name, order_desc)

    print(f"\n{'='*60}")
    print("BEST-MATCHING CORE (lowest combined tip+base distance)")
    print(f"{'='*60}")
    total, row_label, hyp_name, order_desc = best
    print(f"  Core label:        {row_label}")
    print(f"  Hypothesis:        {hyp_name}")
    print(f"  Point ordering:    {order_desc}")
    print(f"  Combined distance: {total:.3f} mm  (tip + base, lower is better; near 0 = exact match)")

    print(f"\n{'='*60}")
    if total < 2.0:
        print(f"VERDICT: {hyp_name} coordinates match this core almost exactly (<2mm).")
        if hyp_name == "RAW":
            print("  -> Set CONVERT_LPS_TO_RAS = False in config.py")
        else:
            print("  -> Keep CONVERT_LPS_TO_RAS = True in config.py")
    else:
        print(f"VERDICT: best match found ({hyp_name}, {total:.1f} mm) is still large for a "
              f"single matched core — something else may be off (wrong core matched, "
              f"a units mismatch, or this case's fcsv/spreadsheet don't correspond "
              f"1:1). Worth checking the raw fcsv points printed above by hand against "
              f"the '{row_label}' row in the spreadsheet.")
    print(f"{'='*60}")
    if coordinate_system:
        print(f"\n(For reference, the .fcsv file itself declares CoordinateSystem = {coordinate_system}.)")


if __name__ == "__main__":
    main()