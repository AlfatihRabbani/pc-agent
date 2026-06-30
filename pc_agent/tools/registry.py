"""Tool registry: every PC capability registers here with a JSON schema + risk tier."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..safety import Risk


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON-schema "properties" dict
    required: list[str]
    risk: Risk
    fn: Callable

    def schema(self) -> dict:
        """OpenAI/Gemma-style function schema the dispatcher is shown."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
            },
        }


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, parameters: dict, required: list[str], risk: Risk):
    """Decorator to register a callable as an agent tool."""
    def deco(fn: Callable) -> Callable:
        REGISTRY[name] = Tool(name, description, parameters, required or [], risk, fn)
        return fn
    return deco


def all_schemas() -> list[dict]:
    return [t.schema() for t in REGISTRY.values()]


def get(name: str) -> Tool | None:
    return REGISTRY.get(name)
