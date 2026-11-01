/** The Claude Desktop config block for this app's MCP server (MCP-03). */
export function claudeDesktopConfig(token: string, apiUrl: string): string {
  const config = {
    mcpServers: {
      "finance-assistant": {
        command: "/path/to/fathom/backend/.venv/bin/python",
        args: ["-m", "src.mcp_server"],
        env: {
          PYTHONPATH: "/path/to/fathom/backend",
          FINANCE_API_URL: apiUrl,
          FINANCE_API_TOKEN: token,
        },
      },
    },
  };
  return JSON.stringify(config, null, 2);
}
