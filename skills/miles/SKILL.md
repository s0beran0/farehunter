---
name: miles
description: Update the miles-value table (CPM — cost per 1,000 miles/points for Smiles, LATAM Pass, Azul, Livelo, Esfera) with current buy-miles promotions and transfer bonuses; shows the diff and only saves after the user confirms. Use when the user asks about miles value, "valor do milheiro", promotions, transfer bonuses, or when a search warns the table is stale.
---

> If any `uv` command fails with "command not found" (or `uv` is not recognized), stop and follow the `/farehunter:setup` skill.

Talk to the user **in their language** (the language of their message).

1. Call the subagent `farehunter:promos-researcher`.
2. With its proposal:
   - Show the user the table "field | current | proposed | source | valid until" and the [UNCERTAIN] items, translated to their language.
   - Validate and show the diff by passing the full proposed YAML through standard input:
     ```bash
     uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter milheiro propor <<'YAML'
     ...full proposed yaml...
     YAML
     ```
     If it prints `MILHEIRO INVÁLIDO`, fix the YAML and retry.
3. **Ask** whether to save. Save only on an explicit "yes", running the same command with `salvar` instead of `propor`. The user may approve only some fields: then apply only those.
4. After saving, run `uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter milheiro checar` and report the result.

Never invent values and never save without confirmation.
