"""Windows Task Scheduler control via schtasks.exe."""
from __future__ import annotations

from ..safety import Risk
from .registry import tool
from ._shell import run


@tool(
    name="list_scheduled_tasks",
    description="List Task Scheduler tasks. Optionally filter by a folder/name substring.",
    parameters={
        "filter": {"type": "string", "description": "Substring to match in task name (optional)."}
    },
    required=[],
    risk=Risk.READ,
)
def list_scheduled_tasks(filter: str = "") -> str:  # noqa: A002
    out = run(["schtasks", "/query", "/fo", "table", "/nh"], timeout=30)
    if filter:
        lines = [ln for ln in out.splitlines() if filter.lower() in ln.lower()]
        return "\n".join(lines[:50]) or f"No tasks matching '{filter}'."
    return "\n".join(out.splitlines()[:50])


@tool(
    name="create_scheduled_task",
    description="Create a scheduled task that runs a program on a schedule. "
                "schedule_type is ONCE/DAILY/WEEKLY/ONLOGON/ONSTART.",
    parameters={
        "name": {"type": "string", "description": "Unique task name."},
        "program": {"type": "string", "description": "Full path or command to run."},
        "schedule_type": {
            "type": "string",
            "enum": ["ONCE", "DAILY", "WEEKLY", "ONLOGON", "ONSTART"],
        },
        "start_time": {
            "type": "string",
            "description": "HH:MM for ONCE/DAILY/WEEKLY (e.g. '14:30'). Ignored otherwise.",
        },
    },
    required=["name", "program", "schedule_type"],
    risk=Risk.TASK,
)
def create_scheduled_task(name: str, program: str, schedule_type: str,
                          start_time: str = "") -> str:
    cmd = ["schtasks", "/create", "/tn", name, "/tr", program,
           "/sc", schedule_type.upper(), "/f"]
    if schedule_type.upper() in ("ONCE", "DAILY", "WEEKLY") and start_time:
        cmd += ["/st", start_time]
    return run(cmd, timeout=30)


@tool(
    name="run_scheduled_task",
    description="Run an existing scheduled task immediately by name.",
    parameters={"name": {"type": "string", "description": "Existing task name."}},
    required=["name"],
    risk=Risk.TASK,
)
def run_scheduled_task(name: str) -> str:
    return run(["schtasks", "/run", "/tn", name], timeout=30)


@tool(
    name="delete_scheduled_task",
    description="Delete a scheduled task by name.",
    parameters={"name": {"type": "string", "description": "Task name to delete."}},
    required=["name"],
    risk=Risk.TASK,
)
def delete_scheduled_task(name: str) -> str:
    return run(["schtasks", "/delete", "/tn", name, "/f"], timeout=30)
