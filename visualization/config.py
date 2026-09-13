"""
config.py
---------
Central place for every path used by the pipeline. Edit ONLY this file
when you move the dataset (e.g. after using `subst` or copying to a
shorter path) — every other script imports from here.

This version points at the ROOT of the multi-case dataset (the folder
that directly contains dicom/, manifests/, supporting/), not a single
case folder. Per-case paths are resolved at run time by case_utils.py,
since each case's DICOM folder, STL folder, and biopsy rows all live in
different places under this root.
"""

from pathlib import Path

# ---------------------------------------------------------------------
# 1. Root of the whole dataset (edit this one line as needed)
#
#    IMPORTANT (Windows): this MUST be a short path or GDCM/SimpleITK
#    will silently fail to read DICOM series once the full nested path
#    exceeds ~260 characters. Run this once in PowerShell first:
#
#        subst Z: "C:\Users\rajaj\Downloads\Radiology\TCIA_20_cases"
#
#    then point DATASET_ROOT at the mapped drive, as below.
# ---------------------------------------------------------------------
DATASET_ROOT = Path("Z:/")   # <-- must match wherever you `subst`'d, e.g. Z:\

# ---------------------------------------------------------------------
# 2. Sub-paths derived from DATASET_ROOT (matches the folder tree spec)
# ---------------------------------------------------------------------
DICOM_BASE = DATASET_ROOT / "dataset" / "dicom"
STL_BASE   = DATASET_ROOT / "dataset" / "supporting" / "selected_stl"
OVERLAYS_BASE = DATASET_ROOT / "dataset" / "supporting" / "selected_overlays"
BIOPSY_XLSX = DATASET_ROOT / "dataset" / "supporting" / "spreadsheets" / "TCIA-Biopsy-Data_2020-07-14.xlsx"

MANIFESTS_DIR = DATASET_ROOT / "dataset" / "manifests"
SELECTED_PATIENTS_FILE = MANIFESTS_DIR / "selected_patients.txt"

OUTPUT_BASE = DATASET_ROOT / "outputs"
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# 1b. Fail loudly and immediately if DATASET_ROOT is missing or still
#     too long, instead of letting every downstream script hit a
#     cryptic "GDCM found no series" error later.
# ---------------------------------------------------------------------
if not DATASET_ROOT.exists():
    raise FileNotFoundError(
        f"DATASET_ROOT does not exist: {DATASET_ROOT}\n"
        f"If you used `subst Z: ...`, confirm it's still mapped by "
        f"running `dir Z:\\` in PowerShell — subst mappings do NOT "
        f"survive a reboot and need to be re-run each session."
    )

_example_deep_path = (
    DICOM_BASE / "1234567890123456789012345678901234567890"
    / "prostate_mri_us_biopsy" / "1234567890123456789012345678901234567890"
    / "1234567890123456789012345678901234567890"
    / "MR_1234567890123456789012345678901234567890"
)
if len(str(_example_deep_path)) > 255:
    print(
        f"WARNING: DATASET_ROOT ({DATASET_ROOT}) is still long enough that "
        f"deeply nested per-case DICOM series paths may exceed Windows' "
        f"260-char limit. Consider a shorter `subst` target or drive letter root."
    )

# ---------------------------------------------------------------------
# 3. Gleason -> color rule (as specified in the task)
#    benign      -> blue
#    3+3 (GG1)   -> orange
#    anything else (3+4, 4+3, 4+4, ...) -> red
# ---------------------------------------------------------------------
COLOR_BENIGN = "blue"
COLOR_GG1    = "orange"
COLOR_HIGHER = "red"

# ---------------------------------------------------------------------
# 4. IMPORTANT coordinate-system caveat.
#    In theory, DICOM patient coordinates are LPS (Left, Posterior,
#    Superior) while 3D Slicer works internally in RAS (Right,
#    Anterior, Superior) — X/Y flipped in sign versus LPS — which is
#    why this flag existed. In practice, for THIS dataset's STL export
#    pipeline, that assumption doesn't hold: verify_tube_mesh_alignment.py
#    tested both hypotheses directly against case 0396's real prostate
#    STL mesh, and found:
#        RAW coordinates:     91.2% of biopsy tip/base points inside
#                              the mesh, mean distance to mesh 5.2mm
#        X/Y-FLIPPED coords:   0.0% inside, mean distance 42.7mm
#    i.e. the STL mesh, biopsy Tip/Base coordinates, and the DICOM
#    series' physical origin are all already in the same frame here —
#    no flip is needed anywhere (tubes, MR slice planes, or slice-view
#    contours all read this same flag). If you re-run
#    verify_tube_mesh_alignment.py on a different case and get the
#    opposite result, flip this back to True for that case — but as of
#    this check, False is correct for this dataset.
# ---------------------------------------------------------------------
CONVERT_LPS_TO_RAS = False
