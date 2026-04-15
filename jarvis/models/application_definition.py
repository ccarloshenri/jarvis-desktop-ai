from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApplicationDefinition:
    aliases: tuple[str, ...]
    launch_command: str
    process_names: tuple[str, ...]
