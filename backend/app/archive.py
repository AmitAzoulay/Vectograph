"""Safe extraction of uploaded .zip archives.

The scanner works on real files on disk (rglob + read_text), so we extract to a
temporary directory. Extraction is guarded against the classic "zip slip"
path-traversal attack and against decompression bombs.
"""
from __future__ import annotations

import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Guard rails against decompression bombs (zip can lie about sizes).
MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024  # 500 MB
MAX_ENTRIES = 20_000
MAX_COMPRESSION_RATIO = 200


class UnsafeArchiveError(ValueError):
    """Raised when an archive fails a safety check."""


@contextmanager
def extracted_archive(zip_bytes: bytes) -> Iterator[Path]:
    """Extract ``zip_bytes`` into a temp dir and clean it up afterwards.

    Usage::

        with extracted_archive(data) as root:
            result = scan_directory(root)
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="vectograph_"))
    try:
        with zipfile.ZipFile(_as_file_like(zip_bytes)) as archive:
            _validate(archive)
            _extract(archive, tmp_dir)
        # Nested archives often wrap the project in a single top-level folder.
        yield _resolve_root(tmp_dir)
    finally:
        _remove_tree(tmp_dir)


class _as_file_like:
    """Tiny adapter so ZipFile can read from an in-memory buffer."""

    def __init__(self, data: bytes) -> None:
        import io

        self._buf = io.BytesIO(data)

    def __getattr__(self, item):  # pragma: no cover - passthrough
        return getattr(self._buf, item)


def _validate(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise UnsafeArchiveError("Archive contains too many entries")

    total = 0
    for info in infos:
        name = info.filename
        # Reject absolute paths and any traversal outside the target dir.
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise UnsafeArchiveError(f"Unsafe path in archive: {name}")
        if info.file_size > MAX_TOTAL_UNCOMPRESSED:
            raise UnsafeArchiveError(f"Entry too large: {name}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise UnsafeArchiveError("Archive expands beyond the size limit")
        # Ratio check: a tiny compressed entry that expands enormously is a bomb.
        if info.compress_size > 0:
            if info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise UnsafeArchiveError(f"Suspicious compression ratio: {name}")


def _extract(archive: zipfile.ZipFile, target: Path) -> None:
    for info in archive.infolist():
        # Skip directories and symlinks (ZipFile does not restore symlinks well).
        if info.is_dir():
            continue
        # Re-resolve the destination and confirm it is still inside `target`.
        dest = (target / info.filename).resolve()
        if not str(dest).startswith(str(target.resolve())):
            raise UnsafeArchiveError(f"Path escapes target: {info.filename}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, open(dest, "wb") as out:
            out.write(src.read())


def _resolve_root(tmp_dir: Path) -> Path:
    """If the zip wrapped everything in one folder, descend into it once."""
    entries = [p for p in tmp_dir.iterdir() if not p.name.startswith("__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return tmp_dir


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
