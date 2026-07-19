"""Treeview factory to reduce boilerplate in panel UIs."""

from __future__ import annotations

import tkinter as tk
from typing import Any

import ttkbootstrap as ttk


def create_scrolled_treeview(
    parent: tk.Widget,
    columns: list[tuple[str, str, int, Any, bool]],
    selectmode: str = "browse",
    height: int | None = None,
    **kwargs: Any,
) -> ttk.Treeview:
    """Create a Treeview with vertical scrollbar, headings, and column config.

    Args:
        parent: Parent widget.
        columns: List of (name, heading_text, width, anchor, stretch) tuples.
        selectmode: Treeview selectmode.
        height: Optional number of visible rows.
        **kwargs: Passed through to :class:`ttk.Treeview`.

    Returns:
        The configured :class:`ttk.Treeview`.
    """
    col_names = tuple(c[0] for c in columns)
    tree_kwargs: dict[str, Any] = {
        "columns": col_names,
        "show": "headings",
        "selectmode": selectmode,
    }
    if height is not None:
        tree_kwargs["height"] = height
    tree_kwargs.update(kwargs)

    tree = ttk.Treeview(parent, **tree_kwargs)

    for col_name, heading_text, width, anchor, stretch in columns:
        tree.heading(col_name, text=heading_text)
        tree.column(col_name, width=width, anchor=anchor, stretch=stretch)

    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)

    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    return tree
