"""
06_combine_views.py
---------------------
Combines the mesh-only 3D visualization with the three 2D slice views
into one summary image:

    ---------------------------------------------------------------
    |            biopsy_visualization_mesh_only                    |
    ---------------------------------------------------------------
    |   axial_view   |    sagittal_view    |     coronal_view      |
    ---------------------------------------------------------------

Each 2D panel gets a colored border — red for axial, yellow for
sagittal, green for coronal. The top scene is fit to the row's width
with its full aspect ratio preserved (no cropping — an earlier "cover"
version cropped straight through tube spikes near the crop line, which
looked like the two rows overlapped), and a thin divider line
separates the two rows regardless of what colors land at the boundary.
Each bottom panel is cover-cropped into an identical box, so all three
columns come out equal width AND height with no gaps, even though
axial/sagittal/coronal don't share the same aspect ratio as each other.

Run:
    python 06_combine_views.py

Produces:
    <CASE_ROOT>/outputs/combined_summary.png
"""

from PIL import Image, ImageOps
import config

BORDER_COLORS = {
    "axial": (255, 0, 0),        # red
    "sagittal": (255, 255, 0),   # yellow
    "coronal": (0, 200, 0),      # green
}
BORDER_THICKNESS = 12   # px, added around each 2D panel
# Each 2D panel is cover-cropped into this exact box (before the border
# is added), so all three bottom-row columns are identical width AND
# height regardless of each view's own aspect ratio.
BOTTOM_PANEL_WIDTH = 500
BOTTOM_PANEL_HEIGHT = 500
DIVIDER_THICKNESS = 6      # px, solid line separating the top scene from the bottom row
DIVIDER_COLOR = (40, 40, 40)


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


def _bordered_panel(image_path, color, panel_width, panel_height):
    """Load one 2D view, cover-crop it to an exact WxH box (no gaps, no distortion), add a colored border."""
    img = Image.open(image_path).convert("RGB")
    fitted = _cover_resize(img, panel_width, panel_height)
    return ImageOps.expand(fitted, border=BORDER_THICKNESS, fill=color)


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
            f"Run 03_visualize_scene.py (for the mesh-only PNG) and "
            f"04_slice_views.py (for the three 2D views) first."
        )

    axial = _bordered_panel(axial_path, BORDER_COLORS["axial"], BOTTOM_PANEL_WIDTH, BOTTOM_PANEL_HEIGHT)
    sagittal = _bordered_panel(sagittal_path, BORDER_COLORS["sagittal"], BOTTOM_PANEL_WIDTH, BOTTOM_PANEL_HEIGHT)
    coronal = _bordered_panel(coronal_path, BORDER_COLORS["coronal"], BOTTOM_PANEL_WIDTH, BOTTOM_PANEL_HEIGHT)

    # All three panels are identical size by construction, so the row
    # is a simple side-by-side paste — no vertical centering needed.
    bottom_height = axial.height
    bottom_width = axial.width + sagittal.width + coronal.width

    bottom_row = Image.new("RGB", (bottom_width, bottom_height), "white")
    x = 0
    for panel in (axial, sagittal, coronal):
        bottom_row.paste(panel, (x, 0))
        x += panel.width

    top_img = Image.open(top_path).convert("RGB")
    # Fit the top scene to the row's width, preserving its full aspect
    # ratio — NO cropping, so no tube or mesh content is ever cut off.
    top_aspect = top_img.height / top_img.width
    top_resized = top_img.resize((bottom_width, max(1, round(bottom_width * top_aspect))))

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
    build_combined_summary(config.OUTPUT_DIR)
