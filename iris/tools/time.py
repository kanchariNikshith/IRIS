"""Read the laptop's local date and time."""
from datetime import datetime

from iris.tools.registry import ToolResult


def get_time() -> ToolResult:
    return ToolResult("verified", "The local date and time is " + datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") + ".")
