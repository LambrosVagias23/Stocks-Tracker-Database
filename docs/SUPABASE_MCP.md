# Supabase MCP setup

Wires Claude Code up to query this project's Supabase database directly,
without going through Python scripts. Useful for ad-hoc inspection, running
one-off SQL, or letting Claude verify schema changes end-to-end.

## What the MCP gives you

Once installed, the following tools become callable from the chat:

| Tool | Does |
|---|---|
| `list_tables` | enumerate public schema |
| `execute_sql` | run arbitrary SELECT / INSERT / UPDATE |
| `apply_migration` | run DDL (CREATE / ALTER / DROP) with safety checks |
| `get_logs` | read Postgres / API / Auth logs |
| `get_project_url`, `get_anon_key` | inspect project config |

Full list: <https://github.com/supabase-community/supabase-mcp>.

## Install

### 1. Create a Personal Access Token (PAT)

1. Open <https://supabase.com/dashboard/account/tokens>
2. Click **Generate new token**, label it e.g. `claude-code-local`
3. Copy the token — you won't see it again.

### 2. Add the server to Claude Code

Open `C:\Users\lambr\.claude\settings.json` (the same file that holds your
other `mcpServers` entries) and add this block under `mcpServers`:

```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": [
        "-y",
        "@supabase/mcp-server-supabase@latest",
        "--read-only",
        "--project-ref=lnqwcmrihmsawrkmzdfe"
      ],
      "env": {
        "SUPABASE_ACCESS_TOKEN": "sbp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
      }
    }
  }
}
```

The project ref `lnqwcmrihmsawrkmzdfe` is the subdomain from
`https://lnqwcmrihmsawrkmzdfe.supabase.co`. Replace the placeholder
`sbp_...` with the PAT you just created.

### 3. Restart Claude Code

Close and reopen (or restart the VSCode extension) so it re-reads
`settings.json` and spawns the MCP server.

## Flags to know

| Flag | Why |
|---|---|
| `--read-only` | **Recommended.** Blocks any write (INSERT/UPDATE/DELETE/DDL). Flip off only when you deliberately want Claude to make schema changes. |
| `--project-ref=<ref>` | Pins the server to one project. Without it, every tool call needs the ref as an argument. |
| `--features=database,docs` | Comma-separated subset of tool groups (database, docs, debugging, development, functions, branching, storage, account). Smaller surface = fewer accidental calls. |

## Verify

After restart, ask in chat:

> list the tables in my Supabase project

Claude should call `list_tables` and come back with `tickers`, `prices`,
`ingest_state`. If it says "no supabase tools available", the server
didn't start — check the Claude Code logs for MCP errors (usually a bad
token or missing `npx`).

## Security notes

- The PAT grants full read access to **every** project owned by your
  account. Create a project-scoped token if you have multiple projects
  and want to isolate.
- Keep `--read-only` on by default. The MCP's own safety banner says the
  same thing, and the prompt-injection surface on an LLM holding raw DB
  write access is real.
- Rotate the PAT periodically — treat it like a long-lived service-role
  key.
- Never commit `settings.json` to a public repo. On this machine it's
  under `C:\Users\lambr\.claude\` which is outside the project.

## Removing it

Delete the `supabase` entry from `mcpServers` and restart Claude Code.
Revoking the PAT from the Supabase dashboard is a belt-and-braces
option if the token has been exposed.
