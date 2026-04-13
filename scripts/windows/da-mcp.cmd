@echo off
REM DataArchive MCP Server launcher for Windows consumers
REM Used by Claude Desktop, Cowork, and Windows zgents
wsl -d Zgent bun run /root/projects/DataArchive/src/mcp/index.ts
