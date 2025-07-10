import logging
import json
from pathlib import Path


logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict | list:
    if not path.exists():
        return {} if path.name != "requests.json" else []

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error loading '{path}' ({e}).")
        return {} if path.name != "requests.json" else []


"""
Maybe, future features:

def is_request_closed(request_number: int) -> bool:
    data = _load_json(Path("data/requests.json"))
    try:
        if not isinstance(data, list):
            logger.error("'data/requests.json' contains incorrect data.")
            return False

        for request in data:
            if request.get("number") == request_number:
                return request.get("status") == 2

        logger.warning(f"Request #{request_number} was not found in the 'data/requests.json'.")
        return False
    except Exception as e:
        logger.error(f"Request #{request_number} status verification error ({e}).")
        return False
"""
