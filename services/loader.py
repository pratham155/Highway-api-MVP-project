"""
Loader service — reads and parses restaurant data from disk.
"""

import json
from pathlib import Path
from typing import List

from models import Restaurant

_DATA_PATH = Path(__file__).parent.parent / "data" / "data.json"


def load_restaurants() -> List[Restaurant]:
    """
    Load and validate all restaurants from data/data.json.

    Returns:
        A list of validated Restaurant objects.

    Raises:
        FileNotFoundError: If data.json does not exist.
        ValueError: If JSON is malformed or fails Pydantic validation.
    """
    if not _DATA_PATH.exists():
        raise FileNotFoundError(
            f"Restaurant data file not found at: {_DATA_PATH}"
        )

    with _DATA_PATH.open("r", encoding="utf-8") as f:
        raw: list = json.load(f)

    return [Restaurant(**item) for item in raw]
