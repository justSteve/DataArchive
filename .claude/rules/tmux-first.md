# Rule: tmux-First

You are a tmux-first entity. Commands that target your runtime environment MUST execute in tmux via `tmux send-keys`, not in Claude Code's Bash tool.

## Gate Check

Before running a command in Bash, ask: "Would Steve run this in his environment?"

1. If YES → run it in tmux via `tmux send-keys -t <session>:<window> '<command>' Enter`
2. If NO (read-only, git, file exploration) → Bash is fine

## What MUST Run in tmux

- Installing dependencies (pip, npm, bun, apt)
- Running builds or test suites
- Starting/restarting services, servers, bots
- Running scripts you wrote for the zgent
- Any command you'd hand Steve as "run this"
- Verifying tools, wrappers, or utilities before presenting them

## What Does NOT Require tmux

- Reading files, searching code, editing files (Claude Code tools are better)
- Git operations (status, log, diff, commit, push)
- Quick diagnostics (file existence, process status, env vars)
- Commands purely within gtOps that don't target a zgent environment

## How

1. Ensure a tmux session exists: `tmux list-sessions`
2. Use the zgent's window or create one:
   `tmux new-window -t gt-root -n <zgent-name> -c /root/projects/<Zgent>`
3. Send the command:
   `tmux send-keys -t gt-root:<zgent-name> '<command>' Enter`
4. Capture and verify output:
   `tmux capture-pane -t gt-root:<zgent-name> -p`

## Delivery Verification

Before declaring tmux-facing work "done":
1. Capture every pane the user will see
2. Fix everything that looks wrong — error messages, stale output, broken layouts
3. Drive the interaction yourself via send-keys
4. Present results in plain language — lead with what Steve sees, not what you built
