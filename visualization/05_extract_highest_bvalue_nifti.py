"""
05_extract_highest_bvalue_nifti.py
------------------------------------
Task 2: for one case, scan every MR series, read the diffusion b-value
tag from the DICOM headers, find the series with the HIGHEST b-value,
load that full series as a 3D volume, and export it as a .nii.gz file.

The b-value reading and series-discovery logic now lives in
dicom_utils.py, shared with the other pipeline steps. This module just
wires that up per case. Run this file directly to process every case
in one pass:
    python 05_extract_highest_bvalue_nifti.py

Produces, per case:
    <output_dir>/highest_bvalue_series.nii.gz
"""

import dicom_utils


def export_highest_bvalue_series(dicom_case_root, output_dir):
    """
    Find the highest-b-value DICOM series for one case and export it as
    a NIfTI file into that case's output folder.
    """
    best_folder, best_bvalue = dicom_utils.find_highest_bvalue_series(dicom_case_root)
    print(f"Highest b-value series: {best_folder.name} (b={best_bvalue})")

    output_path = output_dir / "highest_bvalue_series.nii.gz"
    dicom_utils.export_series_to_nifti(best_folder, output_path)
    return output_path


if __name__ == "__main__":
    import config
    import case_utils

    for case_id in case_utils.get_case_ids():
        print(f"\n=== Highest b-value NIfTI: {case_id} ===")
        paths = case_utils.resolve_case_paths(case_id)
        paths["output_dir"].mkdir(parents=True, exist_ok=True)
        export_highest_bvalue_series(
            dicom_case_root=paths["dicom_root"],
            output_dir=paths["output_dir"],
        )
