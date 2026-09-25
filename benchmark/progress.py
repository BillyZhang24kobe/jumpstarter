from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from typing import TypeVar


T = TypeVar("T")


def progress(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    desc: str,
    unit: str,
) -> Iterable[T]:
    """Show a tqdm progress bar in interactive terminals, with a no-op fallback."""
    try:
        from tqdm.auto import tqdm
    except Exception:  # noqa: BLE001 - progress bars should never block benchmark runs.
        return iterable

    force = os.environ.get("BENCHMARK_PROGRESS") == "1"
    disable = not force and not sys.stderr.isatty()
    return tqdm(iterable, total=total, desc=desc, unit=unit, dynamic_ncols=True, disable=disable)
