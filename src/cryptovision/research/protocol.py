"""Protocol freezing: hashes of the protocol text and configuration, checked before every run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptovision.data.storage import atomic_write_bytes
from cryptovision.research.exceptions import ProtocolIntegrityError

HASH_DEFINITION = "SHA-256 of file bytes with CRLF normalized to LF"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def lock_path(config_path: Path) -> Path:
    """`configs/experiments/x-v1.toml` is frozen in `research/protocols/x-v1.lock.json`."""
    root = config_path.resolve().parents[2]
    return root / "research" / "protocols" / f"{config_path.stem}.lock.json"


@dataclass(frozen=True)
class ProtocolLock:
    path: Path
    data: dict

    @property
    def files(self) -> dict[str, str]:
        return dict(self.data["files"])

    @property
    def frozen_at(self) -> str:
        return str(self.data["frozen_at"])

    @property
    def fingerprint(self) -> str:
        """One hash identifying the frozen protocol and configuration together."""
        joined = "\n".join(f"{name}={digest}" for name, digest in sorted(self.files.items()))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def read_lock(path: Path) -> ProtocolLock:
    if not path.exists():
        raise ProtocolIntegrityError(f"No protocol lock at {path}; freeze the protocol first.")
    return ProtocolLock(path=path, data=json.loads(path.read_text(encoding="utf-8")))


def verify_lock(lock: ProtocolLock, root: Path) -> list[str]:
    """Return a list of mismatches between the lock and the files on disk (empty = intact)."""
    problems = []
    for name, expected in lock.files.items():
        path = root / name
        if not path.exists():
            problems.append(f"{name}: missing")
        elif file_sha256(path) != expected:
            problems.append(f"{name}: modified after freezing")
    return problems


def require_intact(lock: ProtocolLock, root: Path) -> None:
    problems = verify_lock(lock, root)
    if problems:
        raise ProtocolIntegrityError(
            "The frozen protocol was changed: "
            + "; ".join(problems)
            + ". Create a new protocol version instead of editing a frozen one."
        )


def freeze(
    *,
    protocol_id: str,
    protocol_version: str,
    files: list[Path],
    root: Path,
    destination: Path,
    repository_head: str,
    empirical_results_seen: bool,
    reason: str = "",
    now: datetime | None = None,
) -> ProtocolLock:
    """Write a new lock. Refuses to replace an existing one."""
    if destination.exists():
        raise ProtocolIntegrityError(
            f"{destination} already exists; frozen protocols are immutable."
        )
    data = {
        "protocol_id": protocol_id,
        "protocol_version": protocol_version,
        "frozen_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "files": {path.relative_to(root).as_posix(): file_sha256(path) for path in files},
        "hash_definition": HASH_DEFINITION,
        "repository_head_at_freeze": repository_head,
        "empirical_regime_statistics_seen_before_freeze": empirical_results_seen,
        "reason": reason,
        "statement": "Locally pre-specified; not externally registered.",
    }
    atomic_write_bytes(destination, (json.dumps(data, indent=2) + "\n").encode("utf-8"))
    return ProtocolLock(path=destination, data=data)
