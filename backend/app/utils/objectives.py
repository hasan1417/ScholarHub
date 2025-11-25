import re
from typing import List, Optional

OBJECTIVE_PATTERN = re.compile(r"^\s*\d+[\).\-\s]*")


def parse_scope(scope: Optional[str]) -> List[str]:
    if not scope:
        return []
    entries = re.split(r"\r?\n|•", scope)
    parsed: List[str] = []
    for entry in entries:
        if not entry:
            continue
        cleaned = re.sub(OBJECTIVE_PATTERN, "", entry).strip()
        if cleaned:
            parsed.append(cleaned)
    return parsed
