"""
01_load_meshes.py
------------------
Loads the case's STL file(s) using pyvista, and classifies each mesh as
either the "prostate" capsule or a "target" (cancer region) based on
filename keywords, so the visualization script can style them
differently (semi-transparent gray capsule vs. solid colored target).

Some cases in this dataset ship TWO segmentations of the same
structure — one derived from the MR series, one from the US series
(e.g. "...ProstateSurface-seriesUID-<MR uid>.STL" AND
"...ProstateSurface-seriesUID-<US uid>.STL"), plus sometimes a third,
plain-named duplicate ("Prostate.STL") on top. Since every other part
of this pipeline (tubes, MR slice planes) works in the main MR series'
coordinate space, loading the US-derived copy too would draw a second,
wrongly-positioned capsule that the tubes never actually pass through.
load_meshes() takes an optional main_series_uid (see
dicom_utils.read_series_instance_uid) and, when given, keeps only the
STL file(s) tagged with that series — dropping the other series' copy
and any untagged duplicate once a real match is found.

Run this file directly to sanity-check your STL files load correctly:
    python 01_load_meshes.py
"""

import re

import pyvista as pv


def _select_matching_series(stl_files, main_series_uid):
    """
    Given a group of STL files that are all the same structure (e.g.
    every "prostate"-classified file, or every file for one target),
    keep only the one(s) tagged with main_series_uid in their filename
    ("...-seriesUID-<uid>.STL"). Falls back to keeping everything
    if none match — so this is safe to call even for cases that don't
    use this dual-series naming convention at all.
    """
    if main_series_uid is None or len(stl_files) <= 1:
        return stl_files

    def embedded_uid(path):
        match = re.search(r"seriesUID-([\d.]+)", path.name)
        if match is None:
            return None
        # The greedy [\d.]+ also swallows the "." right before the
        # ".STL" extension, so strip any trailing dot(s) off the capture.
        return match.group(1).rstrip(".")

    matching = [p for p in stl_files if embedded_uid(p) == main_series_uid]
    if matching:
        return matching

    # No file's embedded UID matched (e.g. an all-untagged group, or a
    # naming convention we don't recognize) — keep everything rather
    # than risk dropping the only real file.
    return stl_files


def load_meshes(stl_dir, main_series_uid=None):
    """
    Read the case's STL file(s).

    Parameters
    ----------
    stl_dir : Path
    main_series_uid : str or None
        The case's main T2 MR series' SeriesInstanceUID (see
        dicom_utils.read_series_instance_uid). When given, and a case's
        STL folder contains multiple series-tagged copies of the same
        structure, only the one matching this UID is kept.

    Returns
    -------
    dict with two keys:
        "prostate": list of pyvista PolyData meshes (the capsule/surface)
        "targets":  list of pyvista PolyData meshes (cancer lesion(s))
    """
    # Windows filesystems are case-insensitive, so glob("*.STL") and
    # glob("*.stl") would each match the SAME files there, silently
    # doubling every mesh. De-duplicate by resolved path so this works
    # correctly on both case-sensitive and case-insensitive filesystems.
    all_matches = list(stl_dir.glob("*.STL")) + list(stl_dir.glob("*.stl"))
    stl_files = sorted({p.resolve(): p for p in all_matches}.values(), key=lambda p: p.name)
    if not stl_files:
        raise FileNotFoundError(f"No .STL files found in {stl_dir}")

    # Classify by filename — TCIA STL exports typically say "Prostate"
    # or "Target" somewhere in the name.
    prostate_candidates = [p for p in stl_files if "target" not in p.name.lower()]
    target_candidates = [p for p in stl_files if "target" in p.name.lower()]

    prostate_files = _select_matching_series(prostate_candidates, main_series_uid)
    target_files = _select_matching_series(target_candidates, main_series_uid)

    prostate_meshes = []
    for stl_path in prostate_files:
        mesh = pv.read(str(stl_path))
        prostate_meshes.append(mesh)
        print(f"Loaded PROSTATE mesh: {stl_path.name}  ({mesh.n_points} points)")

    target_meshes = []
    for stl_path in target_files:
        mesh = pv.read(str(stl_path))
        target_meshes.append(mesh)
        print(f"Loaded TARGET mesh: {stl_path.name}  ({mesh.n_points} points)")

    return {"prostate": prostate_meshes, "targets": target_meshes}


if __name__ == "__main__":
    import config
    import case_utils
    import dicom_utils

    for case_id in case_utils.get_case_ids():
        print(f"\n=== {case_id} ===")
        paths = case_utils.resolve_case_paths(case_id)
        try:
            main_series_folder = dicom_utils.find_main_t2_series(paths["dicom_root"])
            main_series_uid = dicom_utils.read_series_instance_uid(main_series_folder)
        except (FileNotFoundError, ValueError) as exc:
            print(f"  WARNING: could not determine main series UID ({exc}) — "
                  f"loading without series filtering")
            main_series_uid = None

        meshes = load_meshes(paths["stl_dir"], main_series_uid=main_series_uid)
        print(f"Total prostate meshes: {len(meshes['prostate'])}")
        print(f"Total target meshes:   {len(meshes['targets'])}")
