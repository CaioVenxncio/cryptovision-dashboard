"""Result bundles: immutable, hash-verified directories of research outputs.

A bundle is written to a hidden staging directory and renamed into place only
when complete. Bundles are never overwritten: identical inputs produce the
same content-derived identifier, and a repeated run is compared with the
existing bundle instead of replacing it.

Byte-identical: the JSON/CSV/Markdown result files for identical inputs,
software and platform (they contain no timestamps). `manifest.json` records
creation time and environment and therefore differs between runs.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import cryptovision
from cryptovision.data.storage import atomic_write_bytes, sha256_bytes, sha256_file
from cryptovision.research.exceptions import ArtifactError

MANIFEST = "manifest.json"
DEFAULT_RESULTS_DIR = Path("research") / "results"


def _clean(value: Any) -> Any:
    """Replace non-finite floats by None (JSON has no NaN) and normalize containers."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, float | np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def canonical_json(data: Any) -> bytes:
    text = json.dumps(_clean(data), indent=2, sort_keys=True, default=_json_default)
    return (text + "\n").encode("utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def content_id(payload: dict[str, Any]) -> str:
    """Stable identifier derived from the inputs that determine a result."""
    return sha256_bytes(canonical_json(payload))[:16]


def git_state(root: Path) -> dict[str, Any]:
    try:
        head = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(  # noqa: S603
                ["git", "status", "--porcelain"],  # noqa: S607
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
        )
        return {"commit": head, "working_tree_dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "working_tree_dirty": None}


def environment(root: Path) -> dict[str, Any]:
    import pyarrow

    return {
        "cryptovision": cryptovision.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyarrow": pyarrow.__version__,
        "git": git_state(root),
    }


@dataclass(frozen=True)
class WrittenBundle:
    path: Path
    created: bool  # False: an identical-input bundle already existed
    identical: bool | None  # comparison with the existing bundle when created is False
    differences: tuple[str, ...] = ()


def write_bundle(
    directory: Path, files: dict[str, bytes], metadata: dict[str, Any]
) -> WrittenBundle:
    """Create `directory` atomically with `files` and a manifest of their hashes.

    If the directory already exists, nothing is written; the new files are
    compared byte-for-byte with the existing ones and the outcome returned.
    """
    if MANIFEST in files:
        raise ArtifactError("manifest.json is reserved")
    if directory.exists():
        differences = []
        for name, data in files.items():
            existing = directory / name
            if not existing.exists():
                differences.append(f"{name}: missing in existing bundle")
            elif existing.read_bytes() != data:
                differences.append(f"{name}: content differs")
        return WrittenBundle(directory, False, not differences, tuple(differences))

    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = directory.with_name(f".staging-{directory.name}-{uuid.uuid4().hex[:8]}")
    staging.mkdir()
    try:
        for name, data in files.items():
            atomic_write_bytes(staging / name, data)
        manifest = {
            **metadata,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        }
        atomic_write_bytes(staging / MANIFEST, canonical_json(manifest))
        staging.rename(directory)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return WrittenBundle(directory, True, None)


def read_manifest(directory: Path) -> dict[str, Any]:
    path = directory / MANIFEST
    if not path.exists():
        raise ArtifactError(f"No result bundle at {directory}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_json(directory: Path, name: str) -> dict[str, Any]:
    return json.loads((directory / name).read_text(encoding="utf-8"))


def verify_bundle(directory: Path) -> list[tuple[str, bool, str]]:
    """Recompute file hashes and compare them with the manifest."""
    manifest = read_manifest(directory)
    checks = []
    for name, expected in manifest["files"].items():
        path = directory / name
        if not path.exists():
            checks.append((name, False, "missing"))
            continue
        actual = sha256_file(path)
        checks.append((name, actual == expected, actual))
    listed = set(manifest["files"]) | {MANIFEST}
    for path in sorted(directory.iterdir()):
        if path.name not in listed:
            checks.append((path.name, False, "not listed in manifest"))
    return checks


def list_bundles(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    found = []
    for manifest in sorted(root.glob("**/" + MANIFEST)):
        if any(part.startswith(".") for part in manifest.relative_to(root).parts):
            continue
        found.append((manifest.parent, json.loads(manifest.read_text(encoding="utf-8"))))
    return found
