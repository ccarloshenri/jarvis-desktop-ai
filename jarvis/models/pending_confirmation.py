"""State held between two turns when the correction service asks the user
to confirm a medium-confidence entity resolution.

Intentionally minimal: just the command we would execute if the user
confirms, plus the short spoken form we used in the question so we can
echo it back in the follow-up ("Ok, tocando Marina Sena então.").
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.models.command import Command


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    candidate_command: Command
    spoken_candidate: str
    original_target: str
