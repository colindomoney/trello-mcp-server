import logging
import os
from importlib.metadata import version, PackageNotFoundError

import uvicorn
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.routing import Mount

from server.tools.tools import register_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


try:
    _version = version("trello-mcp")
except PackageNotFoundError:
    try:
        import tomllib
        from pathlib import Path
        with open(Path(__file__).parent / "pyproject.toml", "rb") as _f:
            _version = tomllib.load(_f)["project"]["version"]
    except Exception:
        _version = "unknown"

# Initialize MCP server
mcp = MCPServer("Trello MCP Server", version=_version)

# Register tools
register_tools(mcp)


@mcp.tool()
async def get_server_info() -> dict:
    """Returns server version, configuration, and Trello API connectivity status."""
    import httpx
    api_key = os.getenv("TRELLO_API_KEY", "")
    token = os.getenv("TRELLO_TOKEN", "")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.trello.com/1/members/me",
                params={"key": api_key, "token": token},
                timeout=5,
            )
        trello_status = "ok" if r.status_code == 200 else f"error {r.status_code}"
        trello_user = r.json().get("fullName") if r.status_code == 200 else None
    except Exception as e:
        trello_status = f"unreachable: {e}"
        trello_user = None

    try:
        import subprocess
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        sha = "unknown"

    return {
        "server": "Trello MCP Server",
        "version": _version,
        "git_sha": sha,
        "trello_api_status": trello_status,
        "trello_user": trello_user,
        "api_key_set": bool(api_key),
        "token_set": bool(token),
    }


def start_claude_server():
    """Start the MCP server in Claude app mode"""
    try:
        # Verify environment variables
        if not os.getenv("TRELLO_API_KEY") or not os.getenv("TRELLO_TOKEN"):
            raise ValueError(
                "TRELLO_API_KEY and TRELLO_TOKEN must be set in environment variables"
            )

        logger.info("Starting Trello MCP Server in Claude app mode...")
        mcp.run()
        logger.info("Trello MCP Server started successfully")
    except Exception as e:
        logger.error(f"Error starting Claude server: {str(e)}")
        raise


def start_sse_server():
    """Start the MCP server in SSE mode using uvicorn"""
    try:
        # Verify environment variables
        if not os.getenv("TRELLO_API_KEY") or not os.getenv("TRELLO_TOKEN"):
            raise ValueError(
                "TRELLO_API_KEY and TRELLO_TOKEN must be set in environment variables"
            )

        host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_SERVER_PORT", "8000"))

        # Create Starlette app with MCP server mounted
        app = Starlette(
            routes=[
                Mount("/", app=mcp.sse_app()),
            ]
        )

        logger.info(
            f"Starting Trello MCP Server in SSE mode on http://{host}:{port}..."
        )
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        logger.error(f"Error starting SSE server: {str(e)}")
        raise


if __name__ == "__main__":
    try:
        # Check which mode to run in (default to true for Claude app mode)
        use_claude = os.getenv("USE_CLAUDE_APP", "true").lower() == "true"

        if use_claude:
            # Run in Claude app mode
            start_claude_server()
        else:
            # Run in SSE mode
            start_sse_server()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise
