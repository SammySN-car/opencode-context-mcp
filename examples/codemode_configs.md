# OCCE v3 Code-Mode Client Configurations (All Agents)

Run OCCE in **TypeScript Code Mode** (`execute_occe_ts`) across any MCP-compatible client:

## 1. Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.occe-codemode]
command = "python"
args = ["-m", "occe.codemode_server"]
```

## 2. Claude Code CLI (`~/.claude.json`) & Claude Desktop

```json
{
  "mcpServers": {
    "occe-codemode": {
      "command": "python",
      "args": ["-m", "occe.codemode_server"]
    }
  }
}
```

## 3. OpenCode CLI (`opencode.jsonc`)

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "occe-codemode": {
        "type": "local",
        "command": ["python", "-m", "occe.codemode_server"]
      }
    }
  }
}
```

## 4. Cursor IDE (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "occe-codemode": {
      "command": "python",
      "args": ["-m", "occe.codemode_server"]
    }
  }
}
```
