# ui-probe Command IPC Specification

## Purpose

Enable Claude to programmatically control VS Code by writing commands to a file that ui-probe watches and executes.

## Architecture

```
Claude (Bash tool)  →  writes  →  ui-commands.json
                                       ↓
ui-probe extension  ←  watches  ←  fs.watchFile()
        ↓
VS Code API calls (createTerminal, splitTerminal, etc.)
        ↓
ui-probe extension  →  writes  →  ui-state.log / ui-results.json
                                       ↓
Claude (Read tool)  ←  reads   ←  confirmation/state
```

## Command File Format

Location: `${workspaceFolder}/ui-commands.json`

```json
{
  "id": "cmd-1736445678",
  "timestamp": "2026-01-09T15:08:00Z",
  "commands": [
    {
      "action": "createTerminal",
      "params": {
        "name": "API Server",
        "command": "bun run api",
        "location": "panel"
      }
    },
    {
      "action": "splitTerminal",
      "params": {
        "name": "Frontend Dev",
        "command": "bun run dev",
        "direction": "right"
      }
    }
  ]
}
```

## Supported Actions

### Terminal Control
- `createTerminal` - Create new terminal with name and optional command
- `splitTerminal` - Split existing terminal
- `closeTerminal` - Close terminal by name
- `sendToTerminal` - Send text to named terminal
- `focusTerminal` - Focus a terminal by name

### Editor Control
- `openFile` - Open file at optional line/column
- `splitEditor` - Split editor view
- `closeEditor` - Close active or named editor

### Layout Control
- `setLayout` - Set editor/panel layout (e.g., "2x2", "sidebar-left")
- `focusPanel` - Focus terminal panel, output, etc.

## Results File Format

Location: `${workspaceFolder}/ui-results.json`

```json
{
  "id": "cmd-1736445678",
  "timestamp": "2026-01-09T15:08:01Z",
  "status": "completed",
  "results": [
    { "action": "createTerminal", "success": true, "terminalId": 1 },
    { "action": "splitTerminal", "success": true, "terminalId": 2 }
  ]
}
```

## Implementation Notes

### In ui-probe extension.ts

```typescript
// Add to activate()
const commandFile = path.join(workspaceRoot, 'ui-commands.json');
let lastCommandId = '';

fs.watchFile(commandFile, { interval: 500 }, async () => {
  try {
    const content = JSON.parse(fs.readFileSync(commandFile, 'utf8'));
    if (content.id !== lastCommandId) {
      lastCommandId = content.id;
      await executeCommands(content.commands);
      writeResults(content.id, results);
    }
  } catch (e) {
    // Ignore parse errors during file writes
  }
});

async function executeCommands(commands: Command[]) {
  for (const cmd of commands) {
    switch (cmd.action) {
      case 'createTerminal':
        const term = vscode.window.createTerminal({
          name: cmd.params.name,
          location: vscode.TerminalLocation.Panel
        });
        if (cmd.params.command) {
          term.sendText(cmd.params.command);
        }
        term.show();
        break;
      // ... other actions
    }
  }
}
```

## Integration with DataArchive

Once implemented, Claude can:

1. Write commands to `ui-commands.json`
2. Wait briefly for execution
3. Read `ui-results.json` to confirm
4. Read `ui-state.log` for current state

This eliminates the "one keystroke" requirement - Claude can fully orchestrate the dev environment.

## Related Beads

- DataArchive-m77: Integrate IDEasPlatform ui-probe for programmatic VS Code control
- DataArchive-5mm: Establish Claude autonomy framework for VS Code control

## Next Steps

1. Create this enhancement as a bead in IDEasPlatform
2. Implement file watcher in ui-probe
3. Add command executor with VS Code API calls
4. Test with DataArchive dev environment setup
