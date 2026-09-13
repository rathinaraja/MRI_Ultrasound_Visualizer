"""
extract_highest_bvalue_nifti.py
------------------------------------
Task 2: scan every MR series for this case, read the diffusion b-value
tag from the DICOM headers, find the series with the HIGHEST b-value,
load that full series as a 3D volume, and export it as a .nii.gz file.

Run:
    python extract_highest_bvalue_nifti.py

Produces:
    <CASE_ROOT>/outputs/highest_bvalue_series.nii.gz
"""

import pydicom
import SimpleITK as sitk
import config


# Standard DICOM tag for diffusion b-value.
# Some scanner vendors (older Siemens/GE) don't populate this standard
# tag and instead hide the b-value in a private tag — we fall back to
# the common private tags if the standard one is missing.
STANDARD_BVALUE_TAG = (0x0018, 0x9087)       # Diffusion b-value
PRIVATE_BVALUE_TAGS = [
    (0x0019, 0x100c),   # GE
    (0x0043, 0x1039),   # GE (older)
    (0x0019, 0x100C),   # Siemens (some exports)
]


def read_bvalue(dicom_file_path):
    """
    Read the b-value from a single DICOM file's header.
    Returns a float, or None if no b-value tag is present
    (i.e. this series isn't a diffusion-weighted series at all).
    """
    ds = pydicom.dcmread(dicom_file_path, stop_before_pixels=True)

    if STANDARD_BVALUE_TAG in ds:
        try:
            return float(ds[STANDARD_BVALUE_TAG].value)
        except (TypeError, ValueError):
            pass

    for tag in PRIVATE_BVALUE_TAGS:
        if tag in ds:
            try:
                # private b-value tags sometimes store a list; take first value
                val = ds[tag].value
                if isinstance(val, (list, tuple)):
                    val = val[0]
                return float(val)
            except (TypeError, ValueError, IndexError):
                pass

    return None


def find_series_folders(dicom_root):
    """
    Walk the case's dicom folder and return every leaf folder that
    contains .dcm files, along with its series UID (taken from the
    folder name, which follows the "MR_<seriesUID>" / "US_<seriesUID>"
    convention in this dataset).
    """
    series_folders = []
    for path in dicom_root.rglob("*"):
        if path.is_dir():
            dcm_files = list(path.glob("*.dcm"))
            if dcm_files:
                series_folders.append((path, dcm_files))
    return series_folders


def find_highest_bvalue_series(dicom_root):
    """
    For every series folder under dicom_root, check the b-value of the
    first file. Return the (folder_path, max_bvalue) with the highest
    b-value found. Series with no b-value tag (e.g. the US series, or
    a plain T2 series) are skipped.
    """
    series_folders = find_series_folders(dicom_root)
    if not series_folders:
        raise FileNotFoundError(f"No DICOM series found under {dicom_root}")

    best_folder = None
    best_bvalue = -1

    for folder, dcm_files in series_folders:
        bvalue = read_bvalue(dcm_files[0])
        print(f"{folder.name}: b-value = {bvalue}")
        if bvalue is not None and bvalue > best_bvalue:
            best_bvalue = bvalue
            best_folder = folder

    if best_folder is None:
        raise ValueError(
            "No series with a readable b-value tag was found. "
            "This can happen if none of the series are diffusion-weighted, "
            "or if the b-value is stored in a private tag not listed in "
            "PRIVATE_BVALUE_TAGS above — check a sample file manually with "
            "pydicom.dcmread() and inspect ds to find the right tag."
        )

    return best_folder, best_bvalue


def export_series_to_nifti(series_folder, output_path):
    """
    Load a full DICOM series (all slices) with SimpleITK and write it
    out as a compressed NIfTI (.nii.gz) file.
    """
    reader = sitk.ImageSeriesReader()
    dicom_names = reader.GetGDCMSeriesFileNames(str(series_folder))
    reader.SetFileNames(dicom_names)
    image = reader.Execute()

    sitk.WriteImage(image, str(output_path))
    print(f"Exported {series_folder.name} -> {output_path}")


if __name__ == "__main__":
    best_folder, best_bvalue = find_highest_bvalue_series(config.DICOM_ROOT)
    print(f"\nHighest b-value series: {best_folder.name} (b={best_bvalue})")

    output_path = config.OUTPUT_DIR / "highest_bvalue_series.nii.gz"
    export_series_to_nifti(best_folder, output_path)
