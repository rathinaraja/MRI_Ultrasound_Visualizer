"""
06_combine_views.py
---------------------
Combines the mesh-only 3D visualization with the three 2D slice views
into one summary image per case:

    ---------------------------------------------------------------
    |            biopsy_visualization_mesh_only                    |
    ---------------------------------------------------------------
    |   axial_view   |    sagittal_view    |     coronal_view      |
    ---------------------------------------------------------------

Each 2D panel gets a colored border — red for axial, yellow for
sagittal, green for coronal — matching the same axial/sagittal/coronal
labeling convention already used in 04_slice_views.py.

build_combined_summary() takes a case's output_dir (where
build_mesh_only_scene and build_slice_views already wrote their files)
and writes combined_summary.png back into that same folder. Run this
file directly to build every case in one pass:
    python 06_combine_views.py
"""

from PIL import Image, ImageOps

BORDER_COLORS = {
    "axial": (255, 0, 0),        # red
    "sagittal": (255, 255, 0),   # yellow
    "coronal": (0, 200, 0),      # green
}
BORDER_THICKNESS = 12   # px, added around each 2D panel
# Each 2D panel is cover-cropped into this exact box (before the border
# is added), so all three bottom-row columns are identical width AND
# height regardless of each view's own aspect ratio — axial, sagittal,
# and coronal slices are generally NOT the same shape as each other, so
# an aspect-preserving resize alone would leave each panel a different
# height, with visible gaps around the shorter ones.
BOTTOM_PANEL_WIDTH = 500
BOTTOM_PANEL_HEIGHT = 500
DIVIDER_THICKNESS = 6      # px, solid line separating the top scene from the bottom row
DIVIDER_COLOR = (40, 40, 40)


def _bordered_panel(image_path, color, panel_width, panel_height):
    """Load one 2D view, cover-crop it to an exact WxH box (no gaps, no distortion), add a colored border."""
    img = Image.open(image_path).convert("RGB")
    fitted = _cover_resize(img, panel_width, panel_height)
    return ImageOps.expand(fitted, border=BORDER_THICKNESS, fill=color)


def _cover_resize(img, target_w, target_h):
    """
    Scale img up/down (preserving aspect ratio) until it fully covers a
    target_w x target_h box, then center-crop to exactly that size. This
    fills the whole box with no distortion and no padding bands — the
    tradeoff is that some of the image's edges may be cropped off if its
    aspect ratio doesn't match the target box.
    """
    scale = max(target_w / img.width, target_h / img.height)
    scaled_w, scaled_h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    scaled = img.resize((scaled_w, scaled_h))

    left = (scaled_w - target_w) // 2
    top = (scaled_h - target_h) // 2
    return scaled.crop((left, top, left + target_w, top + target_h))


def build_combined_summary(output_dir):
    """
    Read biopsy_visualization_mesh_only.png, axial_view.png,
    sagittal_view.png, and coronal_view.png from output_dir, and write
    combined_summary.png back into it.
    """
    top_path = output_dir / "biopsy_visualization_mesh_only.png"
    axial_path = output_dir / "axial_view.png"
    sagittal_path = output_dir / "sagittal_view.png"
    coronal_path = output_dir / "coronal_view.png"

    missing = [p.name for p in [top_path, axial_path, sagittal_path, coronal_path] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing source image(s) in {output_dir}: {missing}. "
            f"Run build_mesh_only_scene() and build_slice_views() for this "
            f"case first (run_pipeline.py does this automatically)."
        )

    axial = _bordered_panel(axial_path, BORDER_COLORS["axial"], BOTTOM_PANEL_WIDTH, BOTTOM_PANEL_HEIGHT)
    sagittal = _bordered_panel(sagittal_path, BORDER_COLORS["sagittal"], BOTTOM_PANEL_WIDTH, BOTTOM_PANEL_HEIGHT)
    coronal = _bordered_panel(coronal_path, BORDER_COLORS["coronal"], BOTTOM_PANEL_WIDTH, BOTTOM_PANEL_HEIGHT)

    # All three panels are now identical size by construction, so the
    # row is a simple side-by-side paste — no vertical centering or
    # padding needed.
    bottom_height = axial.height
    bottom_width = axial.width + sagittal.width + coronal.width

    bottom_row = Image.new("RGB", (bottom_width, bottom_height), "white")
    x = 0
    for panel in (axial, sagittal, coronal):
        bottom_row.paste(panel, (x, 0))
        x += panel.width

    top_img = Image.open(top_path).convert("RGB")
    # Fit the top scene to the row's width, preserving its full aspect
    # ratio — NO cropping. The earlier "cover" version forced an exact
    # 50/50 split by cropping the top image to fit a fixed height, but
    # that sliced straight through tube spikes near the crop line, so
    # part of a tube ended up flush against the border below it with no
    # gap — reading as if the two rows overlapped. This keeps every bit
    # of the top scene visible; the tradeoff is the top section is no
    # longer forced to exactly half the total height.
    top_aspect = top_img.height / top_img.width
    top_resized = top_img.resize((bottom_width, max(1, round(bottom_width * top_aspect))))

    # A thin solid divider between the two rows, so they read as clearly
    # separate regardless of what colors happen to land on either side
    # of the boundary.
    divider = Image.new("RGB", (bottom_width, DIVIDER_THICKNESS), DIVIDER_COLOR)

    combined = Image.new(
        "RGB",
        (bottom_width, top_resized.height + DIVIDER_THICKNESS + bottom_height),
        "white",
    )
    combined.paste(top_resized, (0, 0))
    combined.paste(divider, (0, top_resized.height))
    combined.paste(bottom_row, (0, top_resized.height + DIVIDER_THICKNESS))

    out_path = output_dir / "combined_summary.png"
    combined.save(out_path)
    print(f"Saved combined summary to: {out_path}")
    return out_path


if __name__ == "__main__":
    import config
    import case_utils

    for case_id in case_utils.get_case_ids():
        print(f"\n=== Combined summary: {case_id} ===")
        paths = case_utils.resolve_case_paths(case_id)
        try:
            build_combined_summary(paths["output_dir"])
        except FileNotFoundError as exc:
            print(f"  WARNING: skipping — {exc}")
