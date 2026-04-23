# Convention: tmux When It Helps

Claude Code's Bash is the **default** execution environment. Use tmux via
`tmux send-keys` when it genuinely adds value — not as a hard gate.

This convention was previously called "tmux-first" and enforced via hook.
Steve relaxed it on 2026-04-08: the gate added more overhead than value.
COO and every zgent now exercise judgment about when tmux is the right
tool rather than treating Bash as forbidden.

## Default behavior

Run commands in Claude Code's Bash. Read output, reason over it, continue.
This is the fast path for the vast majority of operational work:
diagnostics, file inspection, git operations, one-shot builds, tests that
complete in a reasonable time, installs, validations, ad-hoc scripts.

## When tmux is the right tool

- **Steve explicitly asks** ("run this in tmux", "send-keys that", "drop it into pane X")
- **Interactive programs** that expect a real terminal (htop, vim, claude itself, any REPL)
- **Long-running services or daemons** that must persist past the Claude Code session
  (background servers, watchers, feeds)
- **Live-watch scenarios** where Steve wants to see output scroll in a pane
  while he does other work elsewhere
- **Multi-pane orchestration** where the layout itself is the deliverable
  (dashboards, MOO rooms, desk hubs)

## When Bash is the right tool

- Commands where Claude needs the output for its own reasoning
- Read-only diagnostics and file operations
- Short-lived commands that complete in seconds and return text
- "Can we check X?" or "Is Y present?" questions
- Commands whose output you want to quote back to Steve in the response

## Judgment, not gates

Earlier iterations treated tmux as mandatory for any runtime-facing command.
That created friction: Claude would stop mid-task to ask Steve to open a tmux
session, or refuse to run a 3-second check because "it targets the runtime."
The result was overhead without commensurate benefit.

The new model: **pick the right tool per situation**. If you're unsure,
default to Bash and mention that tmux is available if Steve wants to move
the command there. Steve will ask when he wants it.

## Delivery verification (when you DO use tmux)

When tmux is the right choice, verify end-to-end:

1. Capture every pane the user will see (`tmux capture-pane -t <target> -p`)
2. Fix anything that looks wrong — error messages, stale output, broken layouts
3. Drive the interaction yourself via send-keys
4. Present results in plain language — lead with what Steve sees, not what
   you built
5. Don't hand Steve a tmux command to type when you can send-keys it yourself
