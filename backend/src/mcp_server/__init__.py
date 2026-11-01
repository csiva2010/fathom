"""MCP server exposing finance tools to Claude Desktop over the REST API (MCP-01 to MCP-04).

Claude Desktop launches it over stdio. It is a thin client: every tool calls the backend's
REST API with a personal access token, so provider keys stay on the server and the
numbers match the web app (MCP-02). It imports nothing from the rest of `src`.
"""
