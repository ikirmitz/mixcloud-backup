"""
Shared Rich console utilities for consistent CLI output.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    value = value.strip().lower()
    return value not in {"", "0", "false", "no", "off"}


def _resolve_color_setting(force_color: bool | None) -> bool | None:
    if force_color is not None:
        return force_color
    if _env_flag("MIXCLOUD_LRC_NO_COLOR"):
        return False
    if _env_flag("MIXCLOUD_LRC_COLOR"):
        return True
    return None


class ConsoleOutput:
    def __init__(self, force_color: bool | None = None, stream=None):
        color_setting = _resolve_color_setting(force_color)
        self._force_terminal = color_setting if color_setting is not None else None
        self._no_color = (not color_setting) if color_setting is not None else None
        self._stream = stream
        self._console = self._create_console(stream or sys.stdout)

    def _create_console(self, stream):
        return Console(
            file=stream,
            force_terminal=self._force_terminal,
            no_color=self._no_color,
            highlight=False,
            soft_wrap=True,
        )

    def _ensure_console(self):
        if self._stream is not None:
            return
        current_stream = sys.stdout
        if self._console.file is not current_stream:
            self._console = self._create_console(current_stream)

    def print(self, message: str = "", style: str | None = None):
        self._ensure_console()
        self._console.print(message, style=style)

    def info(self, message: str):
        self._ensure_console()
        self._console.print(message, style="cyan")

    def warn(self, message: str):
        self._ensure_console()
        self._console.print(message, style="yellow")

    def error(self, message: str):
        self._ensure_console()
        self._console.print(message, style="red")

    def success(self, message: str):
        self._ensure_console()
        self._console.print(message, style="green")

    def rule(self, title: str | None = None):
        self._ensure_console()
        self._console.rule(title or "", characters="-")

    def panel(self, title: str, message: str, style: str | None = None):
        self._ensure_console()
        panel = Panel(message, title=title, border_style=style or "", box=box.ASCII)
        self._console.print(panel)

    def table(self, title: str, columns: Sequence[str], rows: Iterable[Sequence[str]]):
        self._ensure_console()
        table = Table(title=title, box=box.ASCII, show_header=True, header_style="bold")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*[str(item) for item in row])
        self._console.print(table)

    def summary_table(self, title: str, rows: Iterable[Sequence[str]]):
        self._ensure_console()
        table = Table(title=title, box=box.ASCII, show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        for row in rows:
            table.add_row(*[str(item) for item in row])
        self._console.print(table)


_console = ConsoleOutput()


def configure_console(no_color: bool | None = None):
    global _console
    force_color = False if no_color else None
    _console = ConsoleOutput(force_color=force_color)


def get_console() -> ConsoleOutput:
    return _console
