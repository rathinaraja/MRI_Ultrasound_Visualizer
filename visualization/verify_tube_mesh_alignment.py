r"""
verify_tube_mesh_alignment.py
--------------------------------
Standalone diagnostic — not part of the main pipeline.

verify_coordinate_system.py checked the spreadsheet's raw MRI
coordinates against the same case's .fcsv overlay file, and found them
identical. That only proves both files encode the same underlying
LPS-labeled numbers — it says nothing about whether those numbers need
converting to line up with the STL mesh, since it never touched the
STL mesh at all. This script does the real test: build biopsy tip/base
points under both the RAW and X/Y-FLIPPED hypotheses, and check which
one actually falls inside or near the case's prostate STL mesh.

Needle biopsy cores sample the gland, so under the correct coordinate
convention, most tip/base points should be inside the prostate mesh or
within a few mm of its surface. Under the wrong convention (mirrored
across the mid-sagittal plane, or offset), points will mostly land far
from the mesh instead.

Run:
    python verify_tube_mesh_alignment.py --stl-dir "path\to\selected_stl\Prostate-MRI-US-Biopsy-0396" --xlsx "path\to\TCIA-Biopsy-Data_2020-07-14.xlsx" --case-id "Prostate-MRI-US-Biopsy-0396"
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyvista as pv
from scipy.spatial import cKDTree


TIP_X_CANDIDATES = ["Bx Tip X (MRI Coord)", "Bx_Tip_X_MRI_Coord", "Tip_X"]
TIP_Y_CANDIDATES = ["Bx Tip Y (MRI Coord)", "Bx_Tip_Y_MRI_Coord", "Tip_Y"]
TIP_Z_CANDIDATES = ["Bx Tip Z (MRI Coord)", "Bx_Tip_Z_MRI_Coord", "Tip_Z"]
BASE_X_CANDIDATES = ["Bx Base X (MRI Coord)", "Bx_Base_X_MRI_Coord", "Base_X"]
BASE_Y_CANDIDATES = ["Bx Base Y (MRI Coord)", "Bx_Base_Y_MRI_Coord", "Base_Y"]
BASE_Z_CANDIDATES = ["Bx Base Z (MRI Coord)", "Bx_Base_Z_MRI_Coord", "Base_Z"]
PATIENT_ID_CANDIDATES = ["Patient Number", "Patient ID", "Patient Id", "PatientID", "Subject ID"]
MISSING_COORD_MAGNITUDE = 1000


def _find_column(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def load_prostate_mesh(stl_dir):
    """
    Same classification rule as 01_load_meshes.py: anything with
    "target" in the filename is a lesion, everything else is treated
    as the prostate capsule. Multiple prostate STL parts are merged
    into one mesh for this test.
    """
    stl_dir = Path(stl_dir)
    stl_files = sorted(stl_dir.glob("*.STL")) + sorted(stl_dir.glob("*.stl"))
    if not stl_files:
        raise FileNotFoundError(f"No .STL files found in {stl_dir}")

    prostate_meshes = [pv.read(str(p)) for p in stl_files if "target" not in p.name.lower()]
    if not prostate_meshes:
        raise ValueError(f"No non-target (prostate) STL files found in {stl_dir}")

    mesh = prostate_meshes[0]
    for extra in prostate_meshes[1:]:
        mesh = mesh.merge(extra)
    return mesh


def evaluate_hypothesis(mesh, points, label):
    """
    For a set of (x, y, z) points, report:
      - fraction inside the mesh (via pyvista's enclosed-point test)
      - mean/max distance to the nearest mesh vertex (a fast
        approximation of distance-to-surface — not exact geometric
        distance to the surface, but good enough to distinguish
        "near the gland" from "far away")
    """
    points = np.asarray(points, dtype=float)
    point_cloud = pv.PolyData(points)

    try:
        if hasattr(point_cloud, "select_interior_points"):
            enclosed = point_cloud.select_interior_points(mesh, check_surface=False)
            inside_mask = np.asarray(enclosed["selected_points"], dtype=bool)
        else:
            enclosed = point_cloud.select_enclosed_points(mesh, tolerance=0.0, check_surface=False)
            inside_mask = np.asarray(enclosed["SelectedPoints"], dtype=bool)
        frac_inside = inside_mask.mean()
    except Exception as exc:
        print(f"  (inside/outside test failed: {exc} — mesh may not be watertight; "
              f"falling back to distance-only comparison)")
        frac_inside = float("nan")

    tree = cKDTree(mesh.points)
    distances, _ = tree.query(points)

    print(f"  {label}:")
    print(f"    fraction of points inside mesh: {frac_inside:.1%}" if frac_inside == frac_inside else "    fraction inside mesh: n/a")
    print(f"    distance to nearest mesh vertex — mean: {distances.mean():7.2f} mm   max: {distances.max():7.2f} mm")

    return frac_inside, distances.mean()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stl-dir", required=True, help="Path to the case's STL folder")
    parser.add_argument("--xlsx", required=True, help="Path to TCIA-Biopsy-Data_2020-07-14.xlsx")
    parser.add_argument("--case-id", required=True, help='e.g. "Prostate-MRI-US-Biopsy-0396"')
    args = parser.parse_args()

    print(f"Loading prostate mesh from {args.stl_dir} ...")
    mesh = load_prostate_mesh(args.stl_dir)
    print(f"  {mesh.n_points} vertices, bounds: {mesh.bounds}")

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

    has_placeholder = (case_rows[coord_cols].abs() == MISSING_COORD_MAGNITUDE).any(axis=1)
    n_dropped = int(has_placeholder.sum())
    if n_dropped:
        print(f"  Skipping {n_dropped} core(s) with missing MRI coordinates (placeholder)")
    case_rows = case_rows[~has_placeholder]

    if case_rows.empty:
        print("\nNo usable coordinate rows for this case — nothing to compare.")
        return

    raw_points = []
    flipped_points = []
    for _, row in case_rows.iterrows():
        tip = (row[tip_x_col], row[tip_y_col], row[tip_z_col])
        base = (row[base_x_col], row[base_y_col], row[base_z_col])
        raw_points.append(tip)
        raw_points.append(base)
        flipped_points.append((-tip[0], -tip[1], tip[2]))
        flipped_points.append((-base[0], -base[1], base[2]))

    print(f"\n{'='*60}")
    print(f"MESH BOUNDS vs POINT LOCATIONS  ({len(raw_points)} tip+base points)")
    print(f"{'='*60}")
    frac_inside_raw, mean_dist_raw = evaluate_hypothesis(mesh, raw_points, "RAW coordinates")
    frac_inside_flip, mean_dist_flip = evaluate_hypothesis(mesh, flipped_points, "X/Y-FLIPPED coordinates")

    print(f"\n{'='*60}")
    print("VERDICT")
    print(f"{'='*60}")
    raw_score = (frac_inside_raw if frac_inside_raw == frac_inside_raw else 0) - mean_dist_raw / 1000
    flip_score = (frac_inside_flip if frac_inside_flip == frac_inside_flip else 0) - mean_dist_flip / 1000
    if raw_score > flip_score:
        print("RAW coordinates land inside/near the prostate mesh much better than flipped.")
        print("-> Set CONVERT_LPS_TO_RAS = False in config.py")
    else:
        print("X/Y-FLIPPED coordinates land inside/near the prostate mesh much better than raw.")
        print("-> Keep CONVERT_LPS_TO_RAS = True in config.py")
    print("(If BOTH hypotheses show a small fraction inside and a large mean distance,")
    print(" the problem isn't the sign convention — see the note below.)")


if __name__ == "__main__":
    main()
