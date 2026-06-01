@echo off
REM DataArchive MCP Server launcher for Windows consumers
REM Used by Claude Desktop, Cowork, and Windows zgents
REM
REM Sets DA_CACHE_PATH to a Windows-accessible location so Windows consumers
REM can reach cached files via C:\ rather than through the WSL /tmp filesystem.
wsl -d Zgent --exec env DA_CACHE_PATH=/mnt/c/DataArchive-cache /usr/local/bin/bun run /root/projects/DataArchive/src/mcp/index.ts
