"""
slice_views.py
-------------------
Reproduces the three 2D slice views 3D Slicer shows by default:
    Red    window = Axial    (top-down)
    Yellow window = Sagittal (side view)
    Green  window = Coronal  (front-back)

For each plane, this script:
  1. Extracts the matching 2D pixel slice from the main MR volume, at a
     position chosen to intersect as many biopsy tubes as possible (see
     compute_best_slice_indices) rather than the volume's blind
     midpoint, which can miss the gland entirely.
  2. Slices the prostate/target STL meshes with that same plane, to get
     their boundary outline at that location (white / lime contours).
  3. Slices each biopsy tube mesh with that same plane — a real
     plane/mesh intersection, same principle Slicer uses internally, so
     a diamond-like outline appears where the plane crosses a tube
     near-perpendicular, and an elongated outline where the plane runs
     close to parallel with the tube's length.

Run:
    python slice_views.py

Produces:
    <CASE_ROOT>/outputs/axial_view.png
    <CASE_ROOT>/outputs/sagittal_view.png
    <CASE_ROOT>/outputs/coronal_view.png
"""

import numpy as np
import SimpleITK as sitk
import matplotlib.pyplot as plt

import config
from importlib import import_module

load_meshes = import_module("load_meshes").load_meshes
build_tubes = import_module("build_biopsy_tubes").build_tubes


# ----------------------------------------------------------------------
# NOTE on orientation: this script assumes the MR volume has an
# identity direction matrix (no gantry tilt/rotation) — true for the
# large majority of TCIA prostate MR series. It applies the same
# LPS -> RAS sign flip (config.CONVERT_LPS_TO_RAS) to BOTH the
# background image extent and the mesh/tube contours on all three
# planes, so the overlay always lines up correctly with the background
# even if the absolute left/right or anterior/posterior labeling
# doesn't exactly match a clinical viewer.
# ----------------------------------------------------------------------


def load_mr_volume():
    """Load the main T2 MR series (the one Bx coordinates are defined in) as a full 3D SimpleITK image."""
    matches = list(config.DICOM_ROOT.glob(f"*/MR_{config.MAIN_MRI_SERIES_UID}"))
    if not matches:
        raise FileNotFoundError(
            f"Could not find MR series folder matching "
            f"MR_{config.MAIN_MRI_SERIES_UID} under {config.DICOM_ROOT}"
        )
    series_folder = matches[0]

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


def axis_coords(origin_val, spacing_val, n, flip_sign=False):
    """Physical (mm) coordinate for every voxel index along one axis."""
    coords = origin_val + np.arange(n) * spacing_val
    if flip_sign:
        coords = -coords
    return coords


def _physical_to_index(physical_val, origin_val, spacing_val, flip_sign, n, clamp=True):
    """
    Inverse of axis_coords()/plane_origin's per-axis formula: given a
    physical (mesh-space) coordinate, find the nearest voxel index along
    that axis. Used to center each slice plane on the prostate mesh's
    own centroid instead of blindly using the whole volume's midpoint,
    which can miss the gland (and every tube) entirely if the prostate
    isn't centered in the scan's full field of view along that axis.
    """
    if flip_sign:
        physical_val = -physical_val
    idx = round((physical_val - origin_val) / spacing_val)
    if clamp:
        idx = max(0, min(n - 1, idx))
    return idx


def plot_contour(ax, sliced_polydata, axis_to_drop, color, lw=2.0):
    """
    Draw a pyvista slice result (a PolyData made of line segments) onto
    a 2D matplotlib axis, dropping whichever 3D axis is constant for
    this plane (0=X for sagittal, 1=Y for coronal, 2=Z for axial).
    """
    if sliced_polydata.n_points == 0:
        return   # this mesh/tube doesn't cross this particular slice

    pts_3d = sliced_polydata.points
    pts_2d = np.delete(pts_3d, axis_to_drop, axis=1)

    lines = sliced_polydata.lines
    if lines is not None and len(lines) > 0:
        # VTK flat line format: [n_pts_in_cell, i0, i1, ..., n_pts, j0, j1, ...]
        idx = 0
        drew_any = False
        while idx < len(lines):
            n_pts = lines[idx]
            point_ids = lines[idx + 1: idx + 1 + n_pts]
            segment = pts_2d[point_ids]
            ax.plot(segment[:, 0], segment[:, 1], color=color, linewidth=lw)
            drew_any = True
            idx += n_pts + 1
        if drew_any:
            return

    # Fallback: no line connectivity (e.g. a single intersection point) -
    # draw as a diamond marker, matching Slicer's markup glyph style.
    ax.scatter(pts_2d[:, 0], pts_2d[:, 1], color=color, marker="D", s=30, zorder=5)


def render_one_slice(image, array, meshes, tubes, plane, out_path, slice_indices):
    """
    plane: one of "axial", "sagittal", "coronal"
    slice_indices: dict with keys "axial", "coronal", "sagittal" giving
        the voxel index to slice at for each plane — see
        compute_best_slice_indices().
    """
    size = image.GetSize()        # (nx, ny, nz)
    spacing = image.GetSpacing()  # (sx, sy, sz)
    origin = image.GetOrigin()    # (ox, oy, oz)
    flip = config.CONVERT_LPS_TO_RAS

    if plane == "axial":
        axis_to_drop = 2                       # dropping Z -> looking down Z axis
        idx = slice_indices["axial"]            # array shape is (z, y, x)
        slice_2d = array[idx, :, :]
        plane_origin = (0, 0, origin[2] + idx * spacing[2])
        plane_normal = (0, 0, 1)
        h_coords = axis_coords(origin[0], spacing[0], size[0], flip)   # X horizontal
        v_coords = axis_coords(origin[1], spacing[1], size[1], flip)   # Y vertical
    elif plane == "coronal":
        axis_to_drop = 1                       # dropping Y -> looking along Y axis
        idx = slice_indices["coronal"]
        slice_2d = array[:, idx, :]
        y_val = origin[1] + idx * spacing[1]
        if flip:
            y_val = -y_val
        plane_origin = (0, y_val, 0)
        plane_normal = (0, 1, 0)
        h_coords = axis_coords(origin[0], spacing[0], size[0], flip)   # X horizontal
        v_coords = axis_coords(origin[2], spacing[2], size[2], False)  # Z vertical (no flip)
    elif plane == "sagittal":
        axis_to_drop = 0                       # dropping X -> looking along X axis
        idx = slice_indices["sagittal"]
        slice_2d = array[:, :, idx]
        x_val = origin[0] + idx * spacing[0]
        if flip:
            x_val = -x_val
        plane_origin = (x_val, 0, 0)
        plane_normal = (1, 0, 0)
        h_coords = axis_coords(origin[1], spacing[1], size[1], flip)   # Y horizontal
        v_coords = axis_coords(origin[2], spacing[2], size[2], False)  # Z vertical (no flip)
    else:
        raise ValueError(f"Unknown plane: {plane}")

    extent = [h_coords.min(), h_coords.max(), v_coords.min(), v_coords.max()]

    # A fixed square (6,6) figure with imshow's default aspect-preserving
    # behavior left black letterbox bars whenever the data's actual
    # width:height ratio wasn't 1:1 (which it usually isn't for these
    # slices). Instead, size the figure to the data's real aspect ratio
    # and place axes that fill the canvas exactly (0,0 to 1,1) — no
    # matplotlib margins, no letterbox.
    h_range = extent[1] - extent[0]
    v_range = extent[3] - extent[2]
    aspect_ratio = (v_range / h_range) if h_range else 1.0
    fig_width = 6
    fig_height = max(fig_width * aspect_ratio, 0.1)

    fig = plt.figure(figsize=(fig_width, fig_height))
    ax = fig.add_axes([0, 0, 1, 1])  # fill the entire figure canvas
    ax.imshow(slice_2d, cmap="gray", extent=extent, origin="lower", aspect="auto")

    for prostate_mesh in meshes["prostate"]:
        sliced = prostate_mesh.slice(normal=plane_normal, origin=plane_origin)
        plot_contour(ax, sliced, axis_to_drop, color="white", lw=1.5)

    for target_mesh in meshes["targets"]:
        sliced = target_mesh.slice(normal=plane_normal, origin=plane_origin)
        plot_contour(ax, sliced, axis_to_drop, color="lime", lw=1.5)

    for tube_mesh, color in tubes:
        sliced = tube_mesh.slice(normal=plane_normal, origin=plane_origin)
        plot_contour(ax, sliced, axis_to_drop, color=color, lw=2.0)

    # No on-image title — the plane name is already in the filename, and
    # a title would need reserved vertical space above the frame, which
    # is exactly the letterboxing this fills edge-to-edge.
    ax.axis("off")
    plt.savefig(out_path, dpi=150, facecolor="black")
    plt.close(fig)
    print(f"Saved {plane} view to: {out_path}")


def compute_centroid_slice_indices(meshes, image):
    """
    Pick the voxel index for each plane based on the prostate mesh's
    own centroid, rather than the whole scan volume's midpoint. Used as
    a fallback by compute_best_slice_indices() when there are no tubes
    to optimize against.
    """
    size = image.GetSize()
    spacing = image.GetSpacing()
    origin = image.GetOrigin()
    flip = config.CONVERT_LPS_TO_RAS

    prostate_meshes = meshes.get("prostate", [])
    if not prostate_meshes:
        print("WARNING: no prostate mesh found — centering slices on the volume midpoint instead")
        return {
            "axial": size[2] // 2,
            "coronal": size[1] // 2,
            "sagittal": size[0] // 2,
        }

    combined = prostate_meshes[0]
    for extra in prostate_meshes[1:]:
        combined = combined.merge(extra)
    center_x, center_y, center_z = combined.center

    return {
        "axial": _physical_to_index(center_z, origin[2], spacing[2], False, size[2]),
        "coronal": _physical_to_index(center_y, origin[1], spacing[1], flip, size[1]),
        "sagittal": _physical_to_index(center_x, origin[0], spacing[0], flip, size[0]),
    }


def _count_intersecting_tubes(tubes, plane_normal, plane_origin):
    """How many tube meshes actually cross this plane (n_points > 0 after slicing)."""
    count = 0
    for tube_mesh, _ in tubes:
        if tube_mesh.slice(normal=plane_normal, origin=plane_origin).n_points > 0:
            count += 1
    return count


def _best_index_for_axis(axis_name, bound_lo, bound_hi, origin_val, spacing_val, flip_axis, n, tubes):
    """
    Search every voxel index within the prostate's bounding range on one
    axis (plus a small padding margin), and return whichever index's
    slice plane intersects the most biopsy tubes.
    """
    idx_a = _physical_to_index(bound_lo, origin_val, spacing_val, flip_axis, n)
    idx_b = _physical_to_index(bound_hi, origin_val, spacing_val, flip_axis, n)
    lo, hi = min(idx_a, idx_b), max(idx_a, idx_b)
    pad = max(2, round((hi - lo) * 0.15))
    lo = max(0, lo - pad)
    hi = min(n - 1, hi + pad)

    best_idx, best_count = (lo + hi) // 2, -1
    for idx in range(lo, hi + 1):
        phys = origin_val + idx * spacing_val
        if flip_axis:
            phys = -phys
        if axis_name == "axial":
            plane_origin, plane_normal = (0, 0, phys), (0, 0, 1)
        elif axis_name == "coronal":
            plane_origin, plane_normal = (0, phys, 0), (0, 1, 0)
        else:
            plane_origin, plane_normal = (phys, 0, 0), (1, 0, 0)

        count = _count_intersecting_tubes(tubes, plane_normal, plane_origin)
        if count > best_count:
            best_count = count
            best_idx = idx

    return best_idx, best_count


def compute_best_slice_indices(meshes, tubes, image):
    """
    Instead of fixing each plane at the prostate's centroid and hoping
    tubes happen to cross it, searches every candidate position within
    (and slightly beyond) the prostate's bounding box on each axis, and
    picks whichever position actually intersects the most biopsy tubes.
    This is what lets a single 2D slice show as many needle bars as a
    flat plane can possibly capture.

    Falls back to compute_centroid_slice_indices() if there are no
    tubes to search against, or no prostate mesh at all.
    """
    if not tubes:
        print("WARNING: no biopsy tubes to optimize against — falling back to centroid-only centering")
        return compute_centroid_slice_indices(meshes, image)

    prostate_meshes = meshes.get("prostate", [])
    if not prostate_meshes:
        return compute_centroid_slice_indices(meshes, image)

    size = image.GetSize()
    spacing = image.GetSpacing()
    origin = image.GetOrigin()
    flip = config.CONVERT_LPS_TO_RAS

    combined = prostate_meshes[0]
    for extra in prostate_meshes[1:]:
        combined = combined.merge(extra)
    xmin, xmax, ymin, ymax, zmin, zmax = combined.bounds

    idx_sagittal, count_s = _best_index_for_axis("sagittal", xmin, xmax, origin[0], spacing[0], flip, size[0], tubes)
    idx_coronal, count_c = _best_index_for_axis("coronal", ymin, ymax, origin[1], spacing[1], flip, size[1], tubes)
    idx_axial, count_a = _best_index_for_axis("axial", zmin, zmax, origin[2], spacing[2], False, size[2], tubes)

    print(f"Best slice picks out of {len(tubes)} tubes -> "
          f"axial: {count_a} tube(s), coronal: {count_c} tube(s), sagittal: {count_s} tube(s)")

    return {"axial": idx_axial, "coronal": idx_coronal, "sagittal": idx_sagittal}


def main():
    image = load_mr_volume()
    array = sitk.GetArrayFromImage(image)   # shape (z, y, x)

    meshes = load_meshes(config.STL_DIR, main_series_uid=config.MAIN_MRI_SERIES_UID)
    tubes = build_tubes(config.BIOPSY_CSV)

    slice_indices = compute_best_slice_indices(meshes, tubes, image)

    render_one_slice(image, array, meshes, tubes, "axial",    config.OUTPUT_DIR / "axial_view.png", slice_indices)
    render_one_slice(image, array, meshes, tubes, "sagittal", config.OUTPUT_DIR / "sagittal_view.png", slice_indices)
    render_one_slice(image, array, meshes, tubes, "coronal",  config.OUTPUT_DIR / "coronal_view.png", slice_indices)


if __name__ == "__main__":
    main()
