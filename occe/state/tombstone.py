"""Dynamic context tombstoning and stale output pruning engine.

Maintains a session execution DAG tracking file reads and modifications.
When a file is edited, prior full-file reads are superseded and marked
as tombstoned, reclaiming thousands of tokens in long-running agent sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FileReadRecord:
    turn: int
    filepath: str
    token_count: int
    is_tombstoned: bool = False
    superseded_by_turn: Optional[int] = None


class TombstoneTracker:
    """Tracks file reads and generates tombstone placeholders when files are edited."""

    def __init__(self):
        # filepath -> list of FileReadRecord
        self.read_history: Dict[str, List[FileReadRecord]] = {}
        self.tokens_reclaimed: int = 0

    def record_read(self, turn: int, filepath: str, token_count: int) -> FileReadRecord:
        """Record that a file was read at a given turn."""
        norm_path = filepath.strip().replace("\\", "/")
        record = FileReadRecord(turn=turn, filepath=norm_path, token_count=token_count)
        if norm_path not in self.read_history:
            self.read_history[norm_path] = []
        self.read_history[norm_path].append(record)
        return record

    def record_edit(self, turn: int, filepath: str) -> List[str]:
        """Record that a file was modified at a given turn.

        Tombstones all prior active reads for this file and returns
        human-readable tombstone placeholder notices.
        """
        norm_path = filepath.strip().replace("\\", "/")
        placeholders: List[str] = []

        if norm_path not in self.read_history:
            return placeholders

        for record in self.read_history[norm_path]:
            if not record.is_tombstoned and record.turn < turn:
                record.is_tombstoned = True
                record.superseded_by_turn = turn
                reclaimed = max(0, record.token_count - 15)  # 15 tokens for tombstone placeholder
                self.tokens_reclaimed += reclaimed

                placeholder = (
                    f"[OCCE Tombstone: Content of '{norm_path}' read at Turn {record.turn} "
                    f"(~{record.token_count} tokens) superseded by edit at Turn {turn}. "
                    f"Reclaimed {reclaimed} tokens from active memory.]"
                )
                placeholders.append(placeholder)

        return placeholders

    def get_active_reads(self) -> Dict[str, int]:
        """Return a mapping of filepath to total active untombstoned tokens."""
        active: Dict[str, int] = {}
        for path, records in self.read_history.items():
            total = sum(r.token_count for r in records if not r.is_tombstoned)
            if total > 0:
                active[path] = total
        return active
