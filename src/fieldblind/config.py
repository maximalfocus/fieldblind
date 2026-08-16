"""Runtime settings for the demonstration services."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DATABASE_PATH_VARIABLE: Final = "FIELDBLIND_DB_PATH"
DEFAULT_DATABASE_PATH: Final = Path("/state/secure.db")

#: The second of the two explicit actions needed to start the intentionally vulnerable service.
ALLOW_VULNERABLE_VARIABLE: Final = "ALLOW_VULNERABLE_DEMO"
ALLOW_VULNERABLE_VALUE: Final = "true"


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the service needs to start, all of it local and disposable."""

    database_path: Path
    allow_vulnerable_demo: bool = False

    @classmethod
    def from_environment(cls) -> Settings:
        """Build settings from the environment, falling back to the disposable container path."""
        configured = os.environ.get(DATABASE_PATH_VARIABLE)
        return cls(
            database_path=Path(configured) if configured else DEFAULT_DATABASE_PATH,
            allow_vulnerable_demo=(
                os.environ.get(ALLOW_VULNERABLE_VARIABLE) == ALLOW_VULNERABLE_VALUE
            ),
        )
