# Prostate-MRI-US-Biopsy — Dataset Download Guide

This guide covers downloading a **20-case subset** of the TCIA [`Prostate-MRI-US-Biopsy`](https://www.cancerimagingarchive.net/collection/prostate-mri-us-biopsy/) collection: MR + ultrasound DICOM, STL surface meshes, biopsy overlay files, and biopsy/target spreadsheets.

---

## Table of Contents

- [Dataset Overview](#dataset-overview)
- [What You Need to Know Before Processing](#what-you-need-to-know-before-processing)
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Step 1 — Query and Download DICOM + Spreadsheets](#step-1--query-and-download-dicom--spreadsheets)
- [Step 2 — Download STL and Biopsy Overlay Packages](#step-2--download-stl-and-biopsy-overlay-packages)
- [Verify Your Download](#verify-your-download)
- [Script Reference](#script-reference)

---

## Dataset Overview

This collection was derived from tracked biopsy sessions using the Artemis fusion biopsy system: patients received a 3D transrectal ultrasound scan, nonrigidly registered ("fused") to a prior multiparametric MRI so that suspicious MRI-defined regions could be targeted during biopsy. Most cases also include systematic 12-core template biopsies. Each biopsy core's location is tracked relative to both the ultrasound volume and (for ~70% of cases) the MR volume.

For each case, the full collection provides:

- **MR + ultrasound DICOM series** — T2-weighted MRI is the primary sequence; a supplemental release adds diffusion-weighted series (ADC + high b-value, most commonly b=1400).
- **STL surface meshes** — prostate gland and any suspicious target ROI(s), one file per structure.
- **Biopsy overlay files** — Slicer-ready `.mrml` scenes with biopsy cores as color-coded 3D line fiducials.
- **Spreadsheets** — per-core biopsy coordinates/pathology, and per-ROI target scoring.

## What You Need to Know Before Processing

- **STL filenames encode their content:** `Prostate-MRI-US-Biopsy-XXXX-SURFACETYPE-seriesUID-YYYY.STL`, where `XXXX` is the patient number, `YYYY` is the DICOM SeriesInstanceUID it was segmented from, and `SURFACETYPE` is either `ProstateSurface` or `TargetN`. Some cases have **both an MR-derived and a US-derived copy** of the same surface — match on `seriesUID` to get the one you want.
- **Biopsy core color convention:** BLUE = benign, ORANGE = Gleason 3+3, RED = Gleason ≥3+4. Prostate = WHITE, target ROIs = GREEN.
- **~30% of cores have no MR coordinates.** Missing values are filled with a placeholder (`-1000`) rather than left blank — filter these out before using the coordinates.
- **Ultrasound STL surfaces have an axis-permuting transform baked in** for 3D Slicer compatibility. Reverse it (matrix below) if you need the original coordinate frame for quantitative work outside Slicer.

  ```
  Applied to US surfaces:      Inverse (to revert):
    0 1 0                        0 0 1
    0 0 1                        1 0 0
    1 0 0                        0 1 0
  ```

- **A private DICOM tag matters:** `(1129,"Eigen, Inc",1016) VoxelSize` is required to correctly display multi-frame US surfaces — don't strip private tags if you plan to visualize this data.
- Full technical detail (scanner models, acquisition parameters, spreadsheet column definitions) is on the [TCIA collection page](https://www.cancerimagingarchive.net/collection/prostate-mri-us-biopsy/) — this guide only covers what's needed to download and orient yourself in the data.

---

## Prerequisites

**Windows only** — this dataset's DICOM folder nesting can exceed Windows' 260-character path limit. Fix it once, system-wide:

1. Open PowerShell **as Administrator**.
2. Run:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```
3. Restart your computer.

---

## Environment Setup

```powershell
mkdir Radiology
cd Radiology

py install 3.11
py -3.11 -m venv tcia_env
.\tcia_env\Scripts\Activate.ps1

python -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

---

## Step 1 — Query and Download DICOM + Spreadsheets

Place `download_tcia_20_cases.py` in the `Radiology` folder.

**First, create the manifest only** (no DICOM download yet — good for confirming the cohort and estimated download size):

```powershell
python download_tcia_20_cases.py --output "Radiology/TCIA_20_cases" --query-only
```

**Then download everything** (DICOM series + biopsy/target spreadsheets):

```powershell
python download_tcia_20_cases.py --output "Radiology/TCIA_20_cases"
```

This downloads patient-by-patient, so an interrupted run can simply be re-run to resume.

---

## Step 2 — Download STL and Biopsy Overlay Packages

TCIA distributes the STL and biopsy-overlay files as two ZIP packages via IBM Aspera, separately from the DICOM/spreadsheet download above. Two ways to get them:

### Option A — Manual (browser)

1. Go to the [collection page](https://www.cancerimagingarchive.net/collection/prostate-mri-us-biopsy/) and download the STL and Biopsy-Overlays-3DSlicer ZIP packages. You'll be prompted to install two Aspera browser helpers first — install them, then download.
2. Place both ZIP files in `Radiology/TCIA_20_cases/supporting/packages`.

### Option B — Automated (`ascli`)

Install the [IBM Aspera CLI](https://www.ibm.com/products/aspera) (`ascli`) and its transfer runtime once:

```powershell
ascli config transferd install
```

Then let the script fetch both packages directly:

```powershell
python download_tcia_20_cases.py --output "Radiology/TCIA_20_cases" --skip-dicom --skip-spreadsheets --with-aspera
```

### Extract and select the 20 cases

Either way, once both ZIPs are in `supporting/packages`, extract them and copy out only the files for these 20 cases:

```powershell
python download_tcia_20_cases.py --output "Radiology/TCIA_20_cases" --skip-dicom --skip-spreadsheets --organize-support
```

---

## Verify Your Download

You should end up with 20 cases under each of:

```
Radiology/TCIA_20_cases/
├── dicom/
│   └── Prostate-MRI-US-Biopsy-****/.../MR_***/*.dcm, US_***/*.dcm
├── logs/
├── manifests/
│   ├── patient_modality_summary.csv
│   ├── download_summary.json
│   ├── selected_patients.txt
│   └── selected_series.csv
└── supporting/
    ├── selected_overlays/Prostate-MRI-US-Biopsy-****/*.mrml, *.fcsv
    ├── selected_stl/Prostate-MRI-US-Biopsy-****/*.STL
    └── spreadsheets/
        ├── TCIA-Biopsy-Data_2020-07-14.xlsx
        └── Target-Data_2019-12-05.xlsx
```

> **Note:** this is the actual structure `download_tcia_20_cases.py` creates directly under `--output`. If you're working from older notes that show an extra `dataset/` folder above `dicom/`, that layer isn't created by this script — confirm which structure your downstream processing code expects.

---

## Script Reference

| Flag | Effect |
|---|---|
| `--output PATH` | Root output directory (default: `./TCIA_20_cases`) |
| `--query-only` | Build the manifest only; skip DICOM download |
| `--skip-dicom` | Skip both the IDC query and DICOM download entirely |
| `--skip-spreadsheets` | Don't download the biopsy/target spreadsheets |
| `--with-aspera` | Fetch the STL/overlay ZIPs automatically via `ascli` |
| `--organize-support` | Extract package ZIPs and copy out only this cohort's files |

Interrupted at any point (including with **Ctrl+C**)? Just re-run the same command — already-downloaded files are detected and skipped.
