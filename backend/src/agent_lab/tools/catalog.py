"""Every tool an agent may be given, by name."""

from agent_lab.tools.base import Tool
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER

TOOLS: dict[str, Tool] = {t.name: t for t in (CALCULATOR, WEATHER)}
