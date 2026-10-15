"""Safe file responses for the single page application's static files."""

import ntpath
import os
from urllib.parse import unquote

from fastapi.responses import FileResponse


def _decode_path(path: str) -> str:
    """Decode nested URL escapes before checking for traversal components."""
    decoded = path
    while True:
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            return decoded
        decoded = next_decoded


def spa_file_response(static_dir: str, path: str) -> FileResponse:
    """Serve a static file, or the SPA entry point when no safe file matches."""
    root = os.path.realpath(static_dir)
    index_path = os.path.join(root, "index.html")
    decoded_path = _decode_path(path).replace("\\", os.sep)

    # Do not let join() discard the static root for absolute paths. Treat both
    # POSIX and Windows absolute paths as invalid, regardless of host platform.
    file_path = None
    if not os.path.isabs(decoded_path) and not ntpath.isabs(decoded_path):
        candidate = os.path.realpath(os.path.join(root, decoded_path))
        try:
            if os.path.commonpath((root, candidate)) == root and os.path.isfile(candidate):
                file_path = candidate
        except (OSError, ValueError):
            pass

    if file_path is None:
        file_path = index_path

    basename = os.path.basename(file_path)
    should_revalidate = (
        file_path == index_path
        or basename == "sw.js"
        or (basename.startswith("manifest") and basename.endswith(".json"))
    )
    headers = {"Cache-Control": "no-cache"} if should_revalidate else None
    return FileResponse(file_path, headers=headers)
