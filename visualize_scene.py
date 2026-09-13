"""
visualize_scene.py
-----------------------
Two 3D visualizations of the same case:

  build_scene() — the full scene:
      - prostate capsule (semi-transparent gray mesh)
      - target/lesion mesh(es) (solid colored)
      - biopsy tubes (colored blue/orange/red per Gleason rule)
      - MR slice plane(s) shown as flat image planes, for context
      - black background

  build_mesh_only_scene() — mesh + cores only, no MR/US slice planes,
      matching the reference exemplar figure's look: a two-tone
      vertical gradient background (colors sampled directly from that
      reference image) instead of black.

Both crop the saved PNG down to its actual content afterward, since a
fixed rectangular window always leaves some blank margin around a
scene sized by reset_camera() alone.

Run:
    python visualize_scene.py

Produces:
    <CASE_ROOT>/outputs/biopsy_visualization.png (+ .html)
    <CASE_ROOT>/outputs/biopsy_visualization_mesh_only.png (+ .html)
"""

import SimpleITK as sitk
import numpy as np
import pyvista as pv
from PIL import Image

import config
from importlib import import_module

load_meshes = import_module("load_meshes").load_meshes
build_tubes = import_module("build_biopsy_tubes").build_tubes


# ----------------------------------------------------------------------
# Which MR slice planes to show inside the full 3D scene, like Slicer's
# "show slice intersections in 3D view" feature. Only used by
# build_scene() — build_mesh_only_scene() never shows MR/US planes.
# ----------------------------------------------------------------------
MR_PLANES_TO_SHOW = ["axial", "sagittal"]

# Vertical gradient background for build_mesh_only_scene(), sampled
# directly from the reference exemplar image's top/bottom edges (away
# from the mesh/tubes), not guessed.
MESH_ONLY_BACKGROUND_TOP = "#7576c0"
MESH_ONLY_BACKGROUND_BOTTOM = "#bfc0e8"


def find_main_series_folder():
    """Locate this case's main T2 MR series folder using its known series UID."""
    matches = list(config.DICOM_ROOT.glob(f"*/MR_{config.MAIN_MRI_SERIES_UID}"))
    return matches[0] if matches else None


def load_mr_volume(dicom_series_dir):
    """Read a DICOM series with SimpleITK and return the full 3D image + numpy array."""
    reader = sitk.ImageSeriesReader()
    dicom_names = reader.GetGDCMSeriesFileNames(str(dicom_series_dir))
    if not dicom_names:
        raise RuntimeError(
            f"GDCM found no series in {dicom_series_dir} "
            f"(path length {len(str(dicom_series_dir))} chars) — "
            f"likely the Windows 260-char path limit. Use `subst`."
        )
    reader.SetFileNames(dicom_names)
    image = reader.Execute()
    array = sitk.GetArrayFromImage(image)   # shape: (z, y, x)
    return image, array


def build_mr_plane(image, array, plane, idx=None):
    """
    Build a pyvista plane textured with MR intensity, positioned in 3D
    physical (patient) space, for ANY orientation - "axial", "sagittal",
    or "coronal". idx: voxel index along the slice's normal axis.
    Defaults to the middle of the volume if not given.
    """
    size = image.GetSize()        # (nx, ny, nz)
    spacing = image.GetSpacing()  # (sx, sy, sz)
    origin = image.GetOrigin()    # (ox, oy, oz)

    if plane == "axial":
        idx = array.shape[0] // 2 if idx is None else idx
        slice_2d = array[idx, :, :]                      # shape (ny, nx)
        center = (origin[0] + (size[0] - 1) * spacing[0] / 2,
                  origin[1] + (size[1] - 1) * spacing[1] / 2,
                  origin[2] + idx * spacing[2])
        direction = (0, 0, 1)
        i_size, j_size = size[0] * spacing[0], size[1] * spacing[1]
        i_res, j_res = size[0] - 1, size[1] - 1
    elif plane == "coronal":
        idx = array.shape[1] // 2 if idx is None else idx
        slice_2d = array[:, idx, :]                       # shape (nz, nx)
        center = (origin[0] + (size[0] - 1) * spacing[0] / 2,
                  origin[1] + idx * spacing[1],
                  origin[2] + (size[2] - 1) * spacing[2] / 2)
        direction = (0, 1, 0)
        i_size, j_size = size[0] * spacing[0], size[2] * spacing[2]
        i_res, j_res = size[0] - 1, size[2] - 1
    elif plane == "sagittal":
        idx = array.shape[2] // 2 if idx is None else idx
        slice_2d = array[:, :, idx]                       # shape (nz, ny)
        center = (origin[0] + idx * spacing[0],
                  origin[1] + (size[1] - 1) * spacing[1] / 2,
                  origin[2] + (size[2] - 1) * spacing[2] / 2)
        direction = (1, 0, 0)
        i_size, j_size = size[1] * spacing[1], size[2] * spacing[2]
        i_res, j_res = size[1] - 1, size[2] - 1
    else:
        raise ValueError(f"Unknown plane: {plane}")

    # Normalize intensities to 0-255 for consistent grayscale display
    slice_2d = slice_2d.astype(np.float32)
    slice_2d -= slice_2d.min()
    if slice_2d.max() > 0:
        slice_2d /= slice_2d.max()
    slice_2d = (slice_2d * 255).astype(np.uint8)

    mesh_plane = pv.Plane(
        center=center,
        direction=direction,
        i_size=i_size,
        j_size=j_size,
        i_resolution=max(i_res, 1),
        j_resolution=max(j_res, 1),
    )
    # pv.Plane's default resolution may not exactly match slice_2d's
    # point count in edge cases — flatten in matching (i,j) order.
    n_plane_points = mesh_plane.n_points
    flat = slice_2d.flatten(order="F")
    if len(flat) != n_plane_points:
        # safety net: resample flat array length to match plane points
        # (only triggers on off-by-one edge cases from resolution rounding)
        flat = np.resize(flat, n_plane_points)
    mesh_plane["intensity"] = flat

    if config.CONVERT_LPS_TO_RAS:
        mesh_plane.points[:, 0] *= -1
        mesh_plane.points[:, 1] *= -1

    return mesh_plane


def crop_to_solid_background(image_path, background_rgb, tolerance=10, padding=15):
    """
    reset_camera() fits the 3D view to the scene's bounds, but a fixed
    rectangular window still leaves a margin since 3D framing can't
    match a 2D bounding box exactly. This crops the saved PNG down to
    the actual non-background content, with a small padding margin —
    for a solid (non-gradient) background color like "black".
    """
    img = Image.open(image_path).convert("RGB")
    arr = np.array(img).astype(int)
    bg = np.array(background_rgb)
    diff = np.abs(arr - bg).sum(axis=2)
    mask = diff > tolerance
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return  # nothing found (e.g. an all-background render) — leave as-is
    x0 = max(int(xs.min()) - padding, 0)
    x1 = min(int(xs.max()) + padding, img.width - 1)
    y0 = max(int(ys.min()) - padding, 0)
    y1 = min(int(ys.max()) + padding, img.height - 1)
    img.crop((x0, y0, x1 + 1, y1 + 1)).save(image_path)


def _add_meshes_and_tubes(plotter):
    """Load and add the prostate capsule, target mesh(es), and biopsy tubes to plotter."""
    meshes = load_meshes(config.STL_DIR, main_series_uid=config.MAIN_MRI_SERIES_UID)

    for prostate_mesh in meshes["prostate"]:
        plotter.add_mesh(
            prostate_mesh,
            color="lightgray",
            opacity=0.25,          # semi-transparent, so tubes show through
            smooth_shading=True,
        )

    for target_mesh in meshes["targets"]:
        plotter.add_mesh(
            target_mesh,
            color="green",
            opacity=0.6,
            smooth_shading=True,
        )

    tubes = build_tubes(config.BIOPSY_CSV)
    for tube_mesh, color in tubes:
        plotter.add_mesh(tube_mesh, color=color, opacity=1.0)


def build_scene():
    """Build and save the full 3D scene (mesh + tubes + MR slice planes, black background)."""
    plotter = pv.Plotter(off_screen=True, window_size=(1200, 1000))
    plotter.set_background("black")

    _add_meshes_and_tubes(plotter)

    # --- MR slice plane(s) for anatomical context ---
    main_series_folder = find_main_series_folder()
    if main_series_folder is not None:
        image, array = load_mr_volume(main_series_folder)
        for plane_name in MR_PLANES_TO_SHOW:
            mesh_plane = build_mr_plane(image, array, plane_name)
            # IMPORTANT: cmap, clim, and show_scalar_bar must be set
            # explicitly on EVERY plane. Omitting any of these on one
            # call can cause pyvista to fall back to a different default
            # colormap for that mesh (commonly showing up as an odd
            # khaki/olive tint instead of proper grayscale).
            plotter.add_mesh(
                mesh_plane,
                scalars="intensity",
                cmap="gray",
                clim=[0, 255],
                opacity=0.7,
                show_scalar_bar=False,
            )
    else:
        print(f"WARNING: could not find MR series folder matching "
              f"MR_{config.MAIN_MRI_SERIES_UID} under {config.DICOM_ROOT} "
              f"- skipping MR slice plane(s).")

    # --- Camera + export ---
    # camera_position="iso" only sets the VIEW DIRECTION, not the zoom —
    # reset_camera() then slides the camera in along that direction
    # until every actor (mesh + tubes) just fits the frame, removing
    # the excess blank border a generic "iso" default would leave.
    plotter.camera_position = "iso"
    plotter.reset_camera()
    plotter.enable_anti_aliasing()

    out_path = config.OUTPUT_DIR / "biopsy_visualization.png"
    plotter.screenshot(str(out_path))
    crop_to_solid_background(out_path, background_rgb=(0, 0, 0))
    print(f"Saved visualization to: {out_path}")

    html_path = config.OUTPUT_DIR / "biopsy_visualization.html"
    plotter.export_html(str(html_path))
    print(f"Saved interactive HTML to: {html_path}")


def build_mesh_only_scene():
    """
    Build and save a mesh-and-cores-only 3D scene — no MR/US slice
    planes — matching the reference exemplar figure's look: a two-tone
    vertical gradient background instead of black.
    """
    plotter = pv.Plotter(off_screen=True, window_size=(1200, 1000))
    plotter.set_background(MESH_ONLY_BACKGROUND_BOTTOM, top=MESH_ONLY_BACKGROUND_TOP)

    _add_meshes_and_tubes(plotter)

    plotter.camera_position = "iso"
    plotter.reset_camera()
    plotter.enable_anti_aliasing()

    out_path = config.OUTPUT_DIR / "biopsy_visualization_mesh_only.png"
    plotter.screenshot(str(out_path))
    print(f"Saved mesh-only visualization to: {out_path}")

    html_path = config.OUTPUT_DIR / "biopsy_visualization_mesh_only.html"
    plotter.export_html(str(html_path))
    print(f"Saved mesh-only interactive HTML to: {html_path}")


def main():
    build_scene()
    build_mesh_only_scene()


if __name__ == "__main__":
    main()
