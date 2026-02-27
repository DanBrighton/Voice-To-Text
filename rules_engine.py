import json
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Dict, Any, Tuple

Action = Tuple[str, Optional[str]]  # (action, param)


@dataclass
class Rule:
    name: str
    pattern: str
    match_type: str
    actions: List[Action]

    def matches(self, text: str) -> bool:
        if self.match_type == "contains":
            return self.pattern.lower() in text.lower()
        if self.match_type == "regex":
            return re.search(self.pattern, text, flags=re.IGNORECASE) is not None
        return False


def load_rules_json(path: str) -> List[Rule]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("rules.json must be a JSON array of rule objects")

    rules: List[Rule] = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            continue

        name = str(r.get("name") or f"rule_{i}")
        pattern = str(r.get("pattern") or "").strip()
        match_type = str(r.get("match_type") or "contains").strip().lower()
        actions_raw = r.get("actions") or []

        if not pattern or not isinstance(actions_raw, list):
            continue

        actions: List[Action] = []
        for a in actions_raw:
            if not isinstance(a, dict):
                continue
            action = str(a.get("action") or "").strip().lower()
            param = a.get("param")
            if not action:
                continue
            actions.append((action, None if param is None else str(param)))

        rules.append(Rule(name=name, pattern=pattern, match_type=match_type, actions=actions))

    return rules


class RuleEngine:
    def __init__(self, rules: List[Rule]):
        self.rules = rules

    def process(self, text: str, dispatch: Callable[[str, Optional[str]], None]) -> None:
        for r in self.rules:
            if not r.get("enabled", True):
                continue
            if r.matches(text):
                for action, param in r.actions:
                    dispatch(action, param)