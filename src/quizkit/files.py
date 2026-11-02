"""Generic file helpers, reusable by any quiz."""

import os
import tempfile
from pathlib import Path


def write_atomically(dest: Path, data: bytes) -> None:
    """Write to a temp file in the same folder, then swap it in, so there's never a half-file.

    If anything fails, the temp file is removed and any old `dest` is left untouched.
    """
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
