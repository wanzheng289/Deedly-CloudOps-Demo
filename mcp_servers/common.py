from __future__ import annotations

import argparse
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


ToolFn = Callable[..., Any]


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: ToolFn
    parameters: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Minimal MCP-like tool registry used until the MCP SDK is installed."""

    def __init__(self, server_name: str) -> None:
        self.server_name = server_name
        self.tools: dict[str, ToolSpec] = {}

    def tool(self, name: str | None = None, description: str | None = None):
        def decorator(fn: ToolFn) -> ToolFn:
            tool_name = name or fn.__name__
            self.tools[tool_name] = ToolSpec(
                name=tool_name,
                description=description or inspect.getdoc(fn) or "",
                fn=fn,
                parameters=_parameters_schema(fn),
            )
            return fn

        return decorator

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
            for spec in self.tools.values()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name].fn(**(arguments or {}))

    def cli(self) -> None:
        parser = argparse.ArgumentParser(description=f"{self.server_name} MCP-like tool server")
        parser.add_argument("command", choices=["list_tools", "call_tool"])
        parser.add_argument("tool_name", nargs="?")
        parser.add_argument("--args", default="{}", help="JSON object for call_tool arguments.")
        args = parser.parse_args()
        if args.command == "list_tools":
            print(json.dumps(self.list_tools(), ensure_ascii=False, indent=2))
            return
        if not args.tool_name:
            raise SystemExit("tool_name is required for call_tool")
        print(json.dumps(self.call_tool(args.tool_name, json.loads(args.args)), ensure_ascii=False, indent=2))


def _parameters_schema(fn: ToolFn) -> dict[str, Any]:
    signature = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        annotation = parameter.annotation
        properties[name] = {
            "type": _json_type(annotation),
            "description": "",
        }
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        else:
            properties[name]["default"] = parameter.default
    return {"type": "object", "properties": properties, "required": required}


def _json_type(annotation: Any) -> str:
    text = str(annotation).lower()
    if "int" in text:
        return "integer"
    if "float" in text:
        return "number"
    if "bool" in text:
        return "boolean"
    if "list" in text:
        return "array"
    if "dict" in text:
        return "object"
    return "string"


def read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if limit is not None and len(rows) >= limit:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
