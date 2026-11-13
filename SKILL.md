---
name: memory-governance-mcp
description: Audit, hash-verified long-term memory for AI workspaces. Use when a project needs a versioned memory/context file system, when multiple agents or sessions write the same memory files concurrently, when memory may have been tampered with or batch-corrupted, or before compressing daily work logs into reusable rules. Keywords: long-term memory, context files, version tracking, hash conflict, memory poisoning, audit log, dreaming/distillation, concurrent writes.
---

# memory-governance-mcp (Skill wrapper for the MCP server)

This repository ships an MCP server (`mcp_server.py`) that wraps `ctx.py` — a hash-verified, audit-logged memory layer. **Install it via the MCP config in README.md first; this file tells the agent when and how to use it.**

## When to invoke

- A workspace has a `MEMORY.md` or long-term memory files that are getting long, contradictory, or risky to edit
- Multiple agents / sessions / scheduled jobs write the same context files
- External content (web pages, emails, JDs) is about to be stored into memory — poisoning risk
- Daily logs accumulate but are never distilled into rules
- You suspect memory was modified, overwritten, or batch-corrupted and need to verify/rollback

**Not for**: single-user, single-session projects with one or two small files — direct editing is simpler.

## Tool routing

| Situation | Call |
|---|---|
| Session start / before any write | `memory_status` — see every tracked file's rev/hash and whether it drifted |
| Need current content or a past snapshot | `memory_get` |
| Before putting new content in | `memory_scan` — dry-run toxicity check, writes nothing |
| Writing a shared state file | `memory_put` with `--expect <hash>` from the last read; on conflict (refused), re-read, merge, retry. **Never overwrite blindly.** |
| Append-only daily logs | use `ctx.py append` from the CLI directly (append is not exposed over MCP; a log should never be rewritten via put) |

## Hard rules

1. **Read before write**: every `put` must carry the hash from a `get` in this session. A put without a fresh expect is the failure mode this system exists to prevent.
2. **Proposal, not decision**: batch edits, rewrites, or distillation outputs are proposals. A human reviews and commits them; the agent never self-approves a rewrite of long-term memory.
3. **Scope**: writes only happen inside `.workbuddy/context/` and `.workbuddy/memory/` of the target workspace. Deletions are limited to user-named tracked files and orphaned snapshots. Nothing else is touched.
4. **Rollback**: use the audit log (`history` / `restore` via `ctx.py`) rather than re-typing old content from chat.

## Notes

- Pure Python stdlib, 3.9+. No network, no third-party deps, no shell execution.
- The MCP server never implements memory logic itself — it shells out to `ctx.py`, so CLI and MCP always behave identically.
- Full design rationale and install steps: see `README.md`.
