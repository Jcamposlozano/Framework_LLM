"""Create-only, atomic JSON files. Contains sensitive artifacts, never diagnostic logs."""

import os
import re
import tempfile
from pathlib import Path
from typing import TypeVar

from extracteval.core.base import Contract
from extracteval.core.hashing import canonical_bytes, content_hash

T = TypeVar("T", bound=Contract)


class JSONRunStore:
    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise ValueError("Run-directory symlinks are forbidden")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise ValueError("Unsafe artifact name")
        path = self.root / (name + ".json")
        if path.is_symlink():
            raise ValueError("Artifact symlinks are forbidden")
        return path

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def put(self, name: str, value: Contract) -> None:
        path = self._path(name)
        data = canonical_bytes(value)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Immutable artifact already exists with different content")
            return
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            try:
                # Atomic create without an overwrite window, including concurrent writers.
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError("Concurrent immutable artifact conflict") from None
        finally:
            os.unlink(temporary)

    def get(self, name: str, contract: type[T]) -> T:
        return contract.model_validate_json(self._path(name).read_bytes())

    def artifact_hashes(self) -> dict[str, str]:
        import json

        return {
            path.stem: content_hash(json.loads(self._path(path.stem).read_bytes()))
            for path in sorted(self.root.glob("*.json"))
            if not path.stem.startswith("manifest")
        }
