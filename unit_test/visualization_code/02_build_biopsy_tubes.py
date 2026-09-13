"""
02_build_biopsy_tubes.py
-------------------------
Reads the per-case biopsy CSV (tip/base MRI coordinates + Gleason score
per core) and builds one pyvista "tube" mesh per biopsy core, colored
according to the task's rule:

    no Gleason score present      -> blue   (benign)
    Gleason Primary+Secondary 3+3 -> orange (GG1)
    any other combination         -> red    (GG2 or higher)

Run directly to sanity-check the CSV parses and tubes build correctly:
    python 02_build_biopsy_tubes.py
"""

import pandas as pd
import pyvista as pv
import config


# Column names as given in the task. If your CSV uses slightly
# different header text, add alternates to these lists — the code
# below picks whichever one it actually finds in the file.
TIP_X_CANDIDATES = ["Bx Tip X (MRI Coord)", "Bx_Tip_X_MRI_Coord", "Tip_X"]
TIP_Y_CANDIDATES = ["Bx Tip Y (MRI Coord)", "Bx_Tip_Y_MRI_Coord", "Tip_Y"]
TIP_Z_CANDIDATES = ["Bx Tip Z (MRI Coord)", "Bx_Tip_Z_MRI_Coord", "Tip_Z"]
BASE_X_CANDIDATES = ["Bx Base X (MRI Coord)", "Bx_Base_X_MRI_Coord", "Base_X"]
BASE_Y_CANDIDATES = ["Bx Base Y (MRI Coord)", "Bx_Base_Y_MRI_Coord", "Base_Y"]
BASE_Z_CANDIDATES = ["Bx Base Z (MRI Coord)", "Bx_Base_Z_MRI_Coord", "Base_Z"]
PRIMARY_CANDIDATES = ["Gleason Primary", "Bx Gleason Primary", "Primary Gleason", "GleasonPrimary"]
SECONDARY_CANDIDATES = ["Gleason Secondary", "Bx Gleason Secondary", "Secondary Gleason", "GleasonSecondary"]

# TCIA's own documentation for this collection: MRI coordinates are
# only recorded for ~70% of cores, and missing values are filled with a
# placeholder rather than left blank. In the shared spreadsheet that
# placeholder is -1000 for the X/Y columns but +1000 for the Z columns
# — so check the magnitude, not a fixed sign. Building a tube from
# these draws a needle track 1000+ mm away in empty space, so these
# rows must be dropped before building tubes.
MISSING_COORD_MAGNITUDE = 1000


def _find_column(df, candidates):
    """Return the first candidate column name that actually exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def get_color(primary, secondary):
    """
    Apply the task's color rule.
    - Missing/NaN primary or secondary -> benign -> blue
    - 3 + 3                             -> orange
    - anything else (3+4, 4+3, 4+4...)  -> red
    """
    if pd.isna(primary) or pd.isna(secondary):
        return config.COLOR_BENIGN
    p, s = int(primary), int(secondary)
    if p == 3 and s == 3:
        return config.COLOR_GG1
    return config.COLOR_HIGHER


def build_tubes(csv_path, tube_radius=1.0):
    """
    Build one pyvista tube mesh per row (biopsy core) in the CSV.

    Returns
    -------
    list of (mesh, color_string) tuples — one per core.
    """
    df = pd.read_csv(csv_path)
    print("CSV columns found:", df.columns.tolist())

    tip_x_col = _find_column(df, TIP_X_CANDIDATES)
    tip_y_col = _find_column(df, TIP_Y_CANDIDATES)
    tip_z_col = _find_column(df, TIP_Z_CANDIDATES)
    base_x_col = _find_column(df, BASE_X_CANDIDATES)
    base_y_col = _find_column(df, BASE_Y_CANDIDATES)
    base_z_col = _find_column(df, BASE_Z_CANDIDATES)
    primary_col = _find_column(df, PRIMARY_CANDIDATES)
    secondary_col = _find_column(df, SECONDARY_CANDIDATES)

    missing = [name for name, col in [
        ("tip X", tip_x_col), ("tip Y", tip_y_col), ("tip Z", tip_z_col),
        ("base X", base_x_col), ("base Y", base_y_col), ("base Z", base_z_col),
    ] if col is None]
    if missing:
        raise ValueError(
            f"Could not find CSV columns for: {missing}. "
            f"Actual columns are: {df.columns.tolist()}. "
            f"Add the real header names to the *_CANDIDATES lists above."
        )
    if primary_col is None or secondary_col is None:
        print("WARNING: Gleason Primary/Secondary columns not found — "
              "every core will be treated as benign (blue). "
              "Check the *_CANDIDATES lists against your real column names.")

    coord_cols = [tip_x_col, tip_y_col, tip_z_col, base_x_col, base_y_col, base_z_col]
    has_placeholder = (df[coord_cols].abs() == MISSING_COORD_MAGNITUDE).any(axis=1)
    n_dropped = int(has_placeholder.sum())
    if n_dropped:
        print(f"Skipping {n_dropped} core(s) with missing MRI coordinates (±{MISSING_COORD_MAGNITUDE} placeholder)")
    df = df[~has_placeholder]

    tubes = []
    for _, row in df.iterrows():
        tip = [row[tip_x_col], row[tip_y_col], row[tip_z_col]]
        base = [row[base_x_col], row[base_y_col], row[base_z_col]]

        # Optional LPS -> RAS conversion, see config.py comment for why.
        # (Currently False for this case — the raw coordinates already
        # match the STL mesh's frame; see config.py's note.)
        if config.CONVERT_LPS_TO_RAS:
            tip = [-tip[0], -tip[1], tip[2]]
            base = [-base[0], -base[1], base[2]]

        # Build a straight line between tip and base, then thicken it
        # into a 4-sided "tube" (diamond cross-section when viewed
        # near-perpendicular) — this is the biopsy needle track.
        line = pv.Line(tip, base)
        tube = line.tube(radius=tube_radius, n_sides=4)

        primary = row[primary_col] if primary_col else None
        secondary = row[secondary_col] if secondary_col else None
        color = get_color(primary, secondary)

        tubes.append((tube, color))

    print(f"Built {len(tubes)} biopsy tube meshes")
    return tubes


if __name__ == "__main__":
    tubes = build_tubes(config.BIOPSY_CSV)
    colors_used = [c for _, c in tubes]
    print("Color breakdown:",
          {c: colors_used.count(c) for c in set(colors_used)})
