"""terminal output helpers."""
from __future__ import annotations

import json as _json


def print_json(data) -> None:
    print(_json.dumps(data, ensure_ascii=False, indent=2, default=str))


def print_table(rows: list, columns: list) -> None:
    """columns: list of (header, key) pairs."""
    if not rows:
        print("(nothing to show)")
        return
    headers = [h for h, _ in columns]
    data = [[_fmt(row.get(k, "")) for _, k in columns] for row in rows]
    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells):
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

    print(fmt_row(headers))
    print(fmt_row(["-" * w for w in widths]))
    for row in data:
        print(fmt_row(row))


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
