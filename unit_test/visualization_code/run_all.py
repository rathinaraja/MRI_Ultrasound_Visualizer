"""
run_all.py
-----------
Convenience entry point for the single-case pilot study — runs every
step in order, so you don't have to run six scripts by hand:

    1. 03_visualize_scene.py  -> biopsy_visualization.png (+html)
                                 biopsy_visualization_mesh_only.png (+html)
    2. 04_slice_views.py      -> axial_view.png, sagittal_view.png, coronal_view.png
    3. 05_extract_highest_bvalue_nifti.py -> highest_bvalue_series.nii.gz
    4. 06_combine_views.py    -> combined_summary.png

Each step is also fully runnable on its own (every script still has its
own `if __name__ == "__main__"` block), so this is purely a shortcut —
nothing here is required.

Run:
    python run_all.py
"""

from importlib import import_module

import config

build_scene = import_module("03_visualize_scene").build_scene
build_mesh_only_scene = import_module("03_visualize_scene").build_mesh_only_scene
slice_views_main = import_module("04_slice_views").main
extract_nifti = import_module("05_extract_highest_bvalue_nifti")
build_combined_summary = import_module("06_combine_views").build_combined_summary


def main():
    print("=== Step 1/4: 3D scenes ===")
    build_scene()
    build_mesh_only_scene()

    print("\n=== Step 2/4: 2D slice views ===")
    slice_views_main()

    print("\n=== Step 3/4: highest b-value NIfTI export ===")
    best_folder, best_bvalue = extract_nifti.find_highest_bvalue_series(config.DICOM_ROOT)
    print(f"Highest b-value series: {best_folder.name} (b={best_bvalue})")
    output_path = config.OUTPUT_DIR / "highest_bvalue_series.nii.gz"
    extract_nifti.export_series_to_nifti(best_folder, output_path)

    print("\n=== Step 4/4: combined summary image ===")
    build_combined_summary(config.OUTPUT_DIR)

    print(f"\nAll done. See {config.OUTPUT_DIR} for every output file.")


if __name__ == "__main__":
    main()
