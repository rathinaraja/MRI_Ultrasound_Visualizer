"""
dicom_utils.py
--------------
Shared DICOM series-discovery helpers, used by every pipeline step so
each script finds a case's series folders the same way.

Two things changed going from one case to N cases:

1. Series-folder discovery has to work regardless of how deep a given
   case's DICOM_UID.*/MR_*/US_* subfolders are nested (the dataset
   nests the case-name folder inside itself — see case_utils.py). We
   handle this with a simple recursive walk for any folder containing
   .dcm files, rather than assuming a fixed depth.

2. The "main" T2 anatomical series (the one Bx Tip/Base coordinates
   were recorded against) used to be a single hardcoded series UID.
   That only worked for one case — every case has a different UID, so
   this module picks the main series automatically per case, using the
   DICOM SeriesDescription tag and (as a tie-breaker/fallback) whether
   the series carries a diffusion b-value at all.
"""

import pydicom
import SimpleITK as sitk


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

# Keywords used to spot the primary T2-weighted anatomical series from
# its DICOM SeriesDescription. Add to this list if your dataset's scanner
# uses a different naming convention.
T2_DESCRIPTION_KEYWORDS = ["t2", "tse", "t2w"]


def find_series_folders(dicom_case_root):
    """
    Every leaf folder under dicom_case_root that contains .dcm files,
    regardless of nesting depth (DICOM_UID.*/MR_*/US_* etc.).
    """
    return [p for p in dicom_case_root.rglob("*") if p.is_dir() and list(p.glob("*.dcm"))]


def read_series_description(folder):
    """Lowercased DICOM SeriesDescription for one series folder, or '' if unreadable."""
    dcm_files = list(folder.glob("*.dcm"))
    if not dcm_files:
        return ""
    ds = pydicom.dcmread(dcm_files[0], stop_before_pixels=True)
    return str(getattr(ds, "SeriesDescription", "")).lower()


def read_series_instance_uid(folder):
    """
    The real SeriesInstanceUID (DICOM tag 0020,000E) for one series
    folder, read directly from a sample file rather than parsed from
    the folder name — some STL filenames in the "selected_stl" folder
    embed this same UID (e.g. "...-seriesUID-<uid>.STL") to indicate
    which series (MR vs US) a given mesh was segmented from, so this
    lets 01_load_meshes.py match STL files to the correct series.
    """
    dcm_files = list(folder.glob("*.dcm"))
    if not dcm_files:
        return ""
    ds = pydicom.dcmread(dcm_files[0], stop_before_pixels=True)
    return str(getattr(ds, "SeriesInstanceUID", ""))


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


def find_main_t2_series(dicom_case_root):
    """
    Pick the series most likely to be the primary T2-weighted anatomical
    volume the Bx Tip/Base coordinates were recorded against: prefer the
    non-diffusion series whose SeriesDescription contains a T2 keyword
    and has the most slices (to avoid picking a localizer/scout). Falls
    back to the largest non-diffusion series if no description matches.
    """
    folders = find_series_folders(dicom_case_root)
    if not folders:
        raise FileNotFoundError(f"No DICOM series found under {dicom_case_root}")

    t2_candidates = []
    non_dwi_candidates = []
    for folder in folders:
        dcm_files = list(folder.glob("*.dcm"))
        bvalue = read_bvalue(dcm_files[0])
        if bvalue is not None:
            continue  # diffusion series — never the main T2 volume
        non_dwi_candidates.append((folder, len(dcm_files)))
        description = read_series_description(folder)
        if any(keyword in description for keyword in T2_DESCRIPTION_KEYWORDS):
            t2_candidates.append((folder, len(dcm_files)))

    if t2_candidates:
        return max(t2_candidates, key=lambda item: item[1])[0]

    if non_dwi_candidates:
        print(
            f"WARNING: no SeriesDescription under {dicom_case_root} matched "
            f"T2_DESCRIPTION_KEYWORDS — falling back to the largest "
            f"non-diffusion series. Verify this is the correct anatomical "
            f"series, and add its description keyword to T2_DESCRIPTION_KEYWORDS "
            f"in dicom_utils.py if it's wrong."
        )
        return max(non_dwi_candidates, key=lambda item: item[1])[0]

    raise ValueError(
        f"Could not identify a main T2 series under {dicom_case_root} — "
        f"every series had a readable b-value tag. Inspect SeriesDescription "
        f"tags manually with pydicom.dcmread() on a sample file."
    )


def find_highest_bvalue_series(dicom_case_root):
    """
    For every series folder under dicom_case_root, check the b-value of
    the first file. Return the (folder_path, max_bvalue) with the
    highest b-value found. Series with no b-value tag (e.g. the US
    series, or the T2 series) are skipped.
    """
    folders = find_series_folders(dicom_case_root)
    if not folders:
        raise FileNotFoundError(f"No DICOM series found under {dicom_case_root}")

    best_folder = None
    best_bvalue = -1

    for folder in folders:
        dcm_files = list(folder.glob("*.dcm"))
        bvalue = read_bvalue(dcm_files[0])
        print(f"{folder.name}: b-value = {bvalue}")
        if bvalue is not None and bvalue > best_bvalue:
            best_bvalue = bvalue
            best_folder = folder

    if best_folder is None:
        raise ValueError(
            f"No series with a readable b-value tag was found under "
            f"{dicom_case_root}. This can happen if none of the series are "
            f"diffusion-weighted, or if the b-value is stored in a private "
            f"tag not listed in PRIVATE_BVALUE_TAGS above — check a sample "
            f"file manually with pydicom.dcmread() and inspect ds to find "
            f"the right tag."
        )

    return best_folder, best_bvalue


def load_series_as_image(series_folder):
    """Read a DICOM series with SimpleITK and return the full 3D image."""
    reader = sitk.ImageSeriesReader()
    dicom_names = reader.GetGDCMSeriesFileNames(str(series_folder))
    if not dicom_names:
        raise RuntimeError(
            f"GDCM found no series in {series_folder} "
            f"(path length {len(str(series_folder))} chars) — "
            f"likely the Windows 260-char path limit. Use `subst`."
        )
    reader.SetFileNames(dicom_names)
    return reader.Execute()


def export_series_to_nifti(series_folder, output_path):
    """Load a full DICOM series with SimpleITK and write it as a compressed NIfTI (.nii.gz)."""
    image = load_series_as_image(series_folder)
    sitk.WriteImage(image, str(output_path))
    print(f"Exported {series_folder.name} -> {output_path}")
