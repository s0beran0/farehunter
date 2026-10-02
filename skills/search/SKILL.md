---
name: search
description: Find the cheapest way to take a trip — cash fares, nearby dates, the user's miles, buying miles, transferring card points, separate tickets through hubs — and give one recommendation with a complete step-by-step plan. Use for flights/fares/airfare, "passagens", "pasajes", "voos", "vuelos", miles/millas/milhas.
argument-hint: "<trip in plain words, e.g. 'Porto Alegre to Recife Nov 20, back Nov 27, 2 adults'>"
---

User request: $ARGUMENTS

> If a `uv` command fails with "command not found", stop and follow `/farehunter:setup`.

The engine does the searching, validating and math. You: understand the request, run it, explain the result. Talk in the user's language. Every command: `uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter <subcommand>` (below, `farehunter …`).

1. **Profile:** `farehunter perfil status`. If `configurado: false`, run the interview in `${CLAUDE_PLUGIN_ROOT}/skills/profile/SKILL.md` first (reuse what the request already says).
2. **Today's balances:** one question for the programs with `tem_conta: true` and the `pontos_programas` ("don't know" is fine; never ask for logins). Balances are never stored.
3. **Request → command.** IATA codes (every airport of the city if "any airport"). Exact dates → `--ida/--volta [--flex N]`; a window + trip length → `--ida-de --ida-ate --noites 5-7`. Ask only for what is missing and essential.
   ```bash
   farehunter run novo --origem BSB --destino MIA --ida 2026-11-20 --volta 2026-11-27 --flex 1 --pax 1 --idioma pt --saldo smiles=45000 livelo=12000
   farehunter recomendar --run "<run path>"
   ```
   `recomendar` collects everything in parallel (cash, date grid, awards, separate tickets through hubs when the destination is in another country), validates what could win and analyses. It prints a short JSON.
4. **If `validacao.precisam_navegador` is not empty:** call `farehunter:miles-researcher` in mode `confirm` with those ids, then run `farehunter recomendar --run "<run path>"` once more (searches are cached, it's quick). LATAM Pass only if the user has a balance worth using (login is manual, by the user).
5. **Answer** from the `relatorio` file (read it):
   - First: the recommendation, the total, the saving vs the plain cash reference, and 1–3 sentences on why — numbers from the report only.
   - If `fontes_falharam` has `google_flights` (HTTP 429), say right away that the result may miss cheaper airline round-trip fares, and guide the user: offer to open the route in **their** browser (`farehunter google abrir --origem .. --destino .. --ida .. [--volta ..] --moeda .. --pais ..`), ask them to use Google Flights normally for a minute or two and solve any "I'm not a robot" check **themselves**. When they say they're done: `farehunter google liberar`, then `farehunter recomendar --run "<run path>"` again. Never click or solve verification checks yourself.
   - If `coletado.posicionamento` exists, one line: does the origin fly nonstop, and which hubs also do.
   - Then the full **step-by-step plan** from the report (never shorten it to "buy at X"), then a short list of alternatives.
   - End with the report's **timing tips** (too early / good time / buy soon, sales coming before the trip, high season, cheaper flying days) in 2–4 lines. If it says it's still early, say plainly that waiting and watching usually pays, and when the good window starts.
   - No menus, no "which do you prefer". If nothing could be validated, say so and why, and do the one useful next step yourself.

Rules: never buy, book, transfer points or pay; never handle passwords; recommend only validated data (the engine already excludes cache/calendar hints); mileage brokers are out of scope.
