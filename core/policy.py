from __future__ import annotations

from dataclasses import dataclass

from .errors import PermissionDeniedError


@dataclass(frozen=True)
class PolicyRule:
    caller_plugin: str
    service: str
    operation: str
    effect: str = "allow"


class PolicyEngine:
    def __init__(self) -> None:
        self._rules: list[PolicyRule] = []
        self.revision = 0

    def set_rules(self, rules: list[PolicyRule]) -> None:
        self._rules = list(rules)
        self.revision += 1

    def allow(self, caller: str, service: str, operation: str, permission: str | None) -> None:
        if not caller:
            raise PermissionDeniedError("caller identity is required")
        matching = [rule for rule in self._rules if rule.caller_plugin in {caller, "*"} and rule.service in {service, "*"} and rule.operation in {operation, "*"}]
        if any(rule.effect == "deny" for rule in matching) or not any(rule.effect == "allow" for rule in matching):
            raise PermissionDeniedError(permission or f"{service}:{operation}")
