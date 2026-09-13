"""
run_pipeline.py
----------------
Single entry point for the whole pipeline. Loops over every case in the
dataset (see case_utils.get_case_ids for how cases are chosen) and, for
each one, runs:
  1. the full 3D biopsy visualization scene (mesh + tubes + MR slice planes)
  2. a mesh-and-cores-only 3D scene, no MR/US planes, matching the
     reference exemplar figure's gradient-background look
  3. the axial/sagittal/coronal 2D slice views
  4. the highest-b-value DICOM -> NIfTI export
  5. a combined summary image (mesh-only scene on top, the three 2D
     views on the bottom, color-bordered red/yellow/green)

Each case's results are written to outputs/<case_id>/ so the whole
20-case run produces one self-contained output folder per case.

Run:
    python run_pipeline.py

A failure on one case (e.g. missing STL files, unreadable DICOM) is
logged and skipped rather than stopping the whole batch — the summary
at the end lists exactly which cases succeeded and which didn't, so
partial failures are easy to spot and re-run individually.
"""

from importlib import import_module

import config
import case_utils

scene_module = import_module("03_visualize_scene")
build_scene = scene_module.build_scene
build_mesh_only_scene = scene_module.build_mesh_only_scene
build_slice_views = import_module("04_slice_views").build_slice_views
export_highest_bvalue_series = import_module("05_extract_highest_bvalue_nifti").export_highest_bvalue_series
build_combined_summary = import_module("06_combine_views").build_combined_summary


def process_one_case(case_id, biopsy_df):
    paths = case_utils.resolve_case_paths(case_id)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    case_rows = case_utils.filter_case_rows(biopsy_df, case_id)
    case_utils.save_case_biopsy_csv(case_rows, case_id, paths["output_dir"])

    build_scene(
        stl_dir=paths["stl_dir"],
        dicom_case_root=paths["dicom_root"],
        biopsy_rows=case_rows,
        output_dir=paths["output_dir"],
    )
    build_mesh_only_scene(
        stl_dir=paths["stl_dir"],
        dicom_case_root=paths["dicom_root"],
        biopsy_rows=case_rows,
        output_dir=paths["output_dir"],
    )
    build_slice_views(
        stl_dir=paths["stl_dir"],
        dicom_case_root=paths["dicom_root"],
        biopsy_rows=case_rows,
        output_dir=paths["output_dir"],
    )
    export_highest_bvalue_series(
        dicom_case_root=paths["dicom_root"],
        output_dir=paths["output_dir"],
    )
    build_combined_summary(paths["output_dir"])


def main():
    biopsy_df = case_utils.load_biopsy_table(config.BIOPSY_XLSX)
    case_ids = case_utils.get_case_ids()
    print(f"Found {len(case_ids)} case(s) to process: {case_ids}")

    failures = []
    for case_id in case_ids:
        print(f"\n{'=' * 60}\nProcessing {case_id}\n{'=' * 60}")
        try:
            process_one_case(case_id, biopsy_df)
        except Exception as exc:
            print(f"ERROR processing {case_id}: {exc}")
            failures.append((case_id, str(exc)))

    succeeded = len(case_ids) - len(failures)
    print(f"\nDone. {succeeded}/{len(case_ids)} cases succeeded.")
    if failures:
        print("Failures:")
        for case_id, msg in failures:
            print(f"  {case_id}: {msg}")


if __name__ == "__main__":
    main()
