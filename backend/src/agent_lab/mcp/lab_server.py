"""The lab's own MCP server: the built-in tools, for the lab's host and outside clients."""

from agent_lab.mcp.server import Server
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER

LAB = Server("glasshouse", "0.1.0", [CALCULATOR, WEATHER])
BUILT_INS = tuple(LAB.tools)  # configs name these without the `lab/` prefix
