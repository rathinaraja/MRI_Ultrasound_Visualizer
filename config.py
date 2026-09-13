"""
config.py
---------
Central place for every path used by the pipeline. Edit ONLY this file
when you move the case data (e.g. after using `subst` or copying to a
shorter path) — every other script imports from here, so you never have
to hunt through multiple files to update a path.
"""

from pathlib import Path

# ---------------------------------------------------------------------
# 1. Root folder of the single pilot case (edit this one line as needed)
#
#    IMPORTANT (Windows): this MUST be a short path or GDCM/SimpleITK
#    will silently fail to read DICOM series once the full nested path
#    exceeds ~260 characters. Run this once in PowerShell first:
#
#        subst Z: "C:\Users\rajaj\Downloads\Radiology\TCIA_sample_cases\2.Dataset_TCIA_case_0396"
#
#    then point CASE_ROOT at the mapped drive, as below.
# ---------------------------------------------------------------------
CASE_ROOT = Path("Z:/")   # <-- must match wherever you `subst`'d, e.g. Z:\

# ---------------------------------------------------------------------
# 2. Sub-paths derived from CASE_ROOT (matches the folder tree you have)
# ---------------------------------------------------------------------
DICOM_ROOT = CASE_ROOT / "dicom" / "prostate_mri_us_biopsy" / "Prostate-MRI-US-Biopsy-0396"
STL_DIR    = CASE_ROOT / "supporting" / "selected_stl" / "Prostate-MRI-US-Biopsy-0396"
BIOPSY_CSV = CASE_ROOT / "biopsy" / "case_0396_biopsy_tracks.csv"
OUTPUT_DIR = CASE_ROOT / "outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# 1b. Fail loudly and immediately if CASE_ROOT is missing or still too
#     long, instead of letting every downstream script hit a cryptic
#     "GDCM found no series" error later.
# ---------------------------------------------------------------------
if not CASE_ROOT.exists():
    raise FileNotFoundError(
        f"CASE_ROOT does not exist: {CASE_ROOT}\n"
        f"If you used `subst Z: ...`, confirm it's still mapped by "
        f"running `dir Z:\\` in PowerShell — subst mappings do NOT "
        f"survive a reboot and need to be re-run each session."
    )

_example_deep_path = DICOM_ROOT / "1234567890123456789012345678901234567890" / "MR_1234567890123456789012345678901234567890"
if len(str(_example_deep_path)) > 255:
    print(
        f"WARNING: CASE_ROOT ({CASE_ROOT}) is still long enough that deeply "
        f"nested DICOM series paths may exceed Windows' 260-char limit. "
        f"Consider a shorter `subst` target or drive letter root."
    )

# ---------------------------------------------------------------------
# 3. Known series UIDs for this case (from the TCIA biopsy spreadsheet).
#    The "main" MRI series is the one the Bx Tip/Base coordinates were
#    recorded against (the T2-weighted anatomical series). The STL
#    folder for this case also contains a SECOND, US-derived copy of
#    the same prostate/target surfaces (see 01_load_meshes.py) — this
#    UID is what tells that script which copy to actually use.
# ---------------------------------------------------------------------
MAIN_MRI_SERIES_UID = "1.3.6.1.4.1.14519.5.2.1.118432358883624532096253314924516639723"
US_SERIES_UID       = "1.3.6.1.4.1.14519.5.2.1.130614821430940002608488302197529593031"

# ---------------------------------------------------------------------
# 4. Gleason -> color rule (as specified in the task)
#    benign      -> blue
#    3+3 (GG1)   -> orange
#    anything else (3+4, 4+3, 4+4, ...) -> red
# ---------------------------------------------------------------------
COLOR_BENIGN = "blue"
COLOR_GG1    = "orange"
COLOR_HIGHER = "red"

# ---------------------------------------------------------------------
# 5. IMPORTANT coordinate-system setting.
#
#    In theory, DICOM patient coordinates are LPS (Left, Posterior,
#    Superior) while 3D Slicer works internally in RAS (Right,
#    Anterior, Superior) — X/Y flipped in sign versus LPS — which is
#    why this flag exists at all.
#
#    In practice, for THIS case's STL export pipeline, that assumption
#    does NOT hold: verify_tube_mesh_alignment.py tested both
#    hypotheses directly against the real prostate STL mesh and found:
#        RAW coordinates:     91.2% of biopsy tip/base points land
#                              inside the mesh, mean distance 5.2mm
#        X/Y-FLIPPED coords:   0.0% inside, mean distance 42.7mm
#    i.e. the STL mesh, the Bx Tip/Base coordinates, and the DICOM
#    series' physical origin are all already in the same frame here —
#    no flip is needed. This one flag controls the flip everywhere it
#    matters (tubes, MR slice planes, 2D slice-view contours), so
#    changing it here is sufficient.
#
#    If you ever see tubes floating outside the mesh again on a
#    different case, re-run verify_tube_mesh_alignment.py against that
#    case's own STL before assuming this same value still holds.
# ---------------------------------------------------------------------
CONVERT_LPS_TO_RAS = False
