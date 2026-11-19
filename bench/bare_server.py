"""Bridge-only MCP server for the benchmark's bare baseline.

It has the same name as the full server, so the tool names match, but it offers
only the two bridge tools. A model in the bare run never sees the calculators or
the knowledge tools, so it can't waste turns calling tools it isn't allowed to use.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import server  # noqa: E402

# The benchmark drives FreeCAD with free-form code, so it needs the code tool on.
os.environ.setdefault("FREECAD_MCP_ALLOW_CODE", "1")

mcp = FastMCP("shapebert")
mcp.tool()(server.run_freecad_code)
mcp.tool()(server.get_document_info)

if __name__ == "__main__":
    mcp.run()
