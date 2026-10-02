---
name: search
description: Find the cheapest way to take a trip anywhere — cash fares, nearby dates, miles the user already has, buying miles, transferring card points, and mixes (cash one way, miles the other) — and produce a ranked report with links to book manually. Use when the user asks for flights/fares/airfare, "passagens", "pasajes", "voos", "vuelos", miles/millas/milhas redemptions, or "is it worth using miles".
argument-hint: "<trip in plain words, e.g. 'Porto Alegre to Recife Nov 20, back Nov 27, 2 adults'>"
---

User request: $ARGUMENTS

> If any `uv` command fails with "command not found" (or `uv` is not recognized), stop and follow the `/farehunter:setup` skill, which teaches how to install what is missing.

You are the orchestrator. **Never do math in your head**: every cost, saving, CPM and ranking comes from the `analisar` command. Your job: understand the request, run the collectors, decide what to confirm live, and explain the result.

## Language
- Talk to the user in **their language**: the language of their message; if unclear, the `idioma` in the profile.
- Pass `--idioma pt|en|es` to `run novo`. For any other language, pass `en` and translate the final report faithfully into the user's language without changing any number, date or link.
- The command outputs (JSON keys, field names) are in Portuguese; never show raw keys to the user — explain in their language.
- Every amount in a run is in one currency: the profile's `moeda` (override with `--moeda` if the user asks for another). Award taxes in other currencies are converted automatically; CPM values too.

All commands below use the plugin's engine:
`uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter <subcommand>`

## 0. Profile
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter perfil status
```
- `configurado: false` → say in one sentence that you need to get to know them once (home airport, which miles/points programs they use), then **run the interview** by following `${CLAUDE_PLUGIN_ROOT}/skills/profile/SKILL.md` (read it). Reuse whatever the request already says (origin, number of travellers). If they prefer to skip, continue with just the request and say that miles they own will not be considered.

## 0.1 Today's balances (every search)
Balances are **never stored**: they change with every purchase, transfer and expiry, and an old number silently produces wrong advice.
- In a single question, ask the **current** balance only for programs with `tem_conta: true` and for the `pontos_programas` in the profile (e.g. "How much do you have today? United: __ · Amex MR: __ — you can check in the app; 'don't know' is fine"). Use registry ids in `--saldo` (e.g. `united=60000 amex_mr=80000`).
- If the request already states a balance ("I have 60k Smiles"), use it without asking again.
- Accept "45k", "45 mil", "45.000", "45,000" → 45000. "Don't know" → omit that program (the report warns it was not considered). "I have none" → pass `--saldo` with no values.
- Never ask for logins or passwords to check balances.

## 1. Understand the request
Extract origin(s) and destination(s) as IATA codes (include every airport of the city when the user says "any airport", e.g. Rio → GIG SDU), passengers, cabin (default economy) and checked bag. Dates:
- **Exact dates** → `--ida` / `--volta`.
- **A window and a trip length** ("leave between Nov 2 and 26, 5 to 7 days") → `--ida-de 2026-11-02 --ida-ate 2026-11-26 --noites 5-7`. The engine enforces it; never filter dates by hand.
Without an origin, use `aeroportos_origem` from the profile. Ask **only** for what is missing and essential (destination or date).

## 2. Prepare
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter milheiro checar
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter run novo --origem <IATA...> --destino <IATA...> (--ida YYYY-MM-DD [--volta YYYY-MM-DD] [--flex N] | --ida-de YYYY-MM-DD --ida-ate YYYY-MM-DD --noites N-M) [--pax N] [--cabine economy] --idioma <pt|en|es> [--moeda USD] [--pais US] [--hubs GRU GIG ...] --saldo smiles=45000 livelo=12000
```
- If `milheiro checar` reports values older than 15 days, mention it in one line and continue.
- Keep the absolute `run` path printed by `run novo`; below it is `$RUN`.

## 3. Collect in parallel
Launch **in the same message** three plugin subagents with the absolute `$RUN` path:
- `farehunter:cash-researcher` — exact dates (it skips itself for date windows).
- `farehunter:dates-researcher` — the date grid (windows and trip lengths included).
- `farehunter:miles-researcher` in mode `collect` — every award program Seats.aero covers that matters for this user. No LATAM Pass yet.

## 4. Separate tickets through a hub (when it can pay off)
Run it whenever the trip is **international or long-haul**, or the origin is not a big hub (e.g. BSB→MIA: GRU, GIG, VCP, REC, FOR… may have cheaper flights to Miami, and BSB→hub is a cheap domestic hop):
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter coletar posicionamento --run "$RUN"
```
It finds which of the country's busiest airports (Seats.aero airport traffic; or `--hubs` from `run novo`) actually fly **nonstop** to the destination (Kiwi nonstop check; Seats.aero tracked award routes as a second signal), stores those nonstop flights as validated options, and fetches the positioning flights from/to the origin. Airports without service are never searched. Its JSON output has `origem` (does the origin itself fly nonstop?) and `hubs` (other airports with service). Mention both in one line, e.g. "BSB flies nonstop to Miami (American); GRU and GIG also do, so splitting tickets was compared". Never describe the hub list as the only airports with nonstop service: the origin is excluded from it by design. The engine then composes separate tickets with a minimum connection time (`conexao_bilhetes_separados_min`, default 3 h) and flags the risks.

## 5. Validate until the winner is real (mandatory loop)
Calendar prices (no specific flight) and Seats.aero awards (cache) are **hints, never answers**. Repeat at most 3 rounds:
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter pendencias --run "$RUN" --max 4
```
- `detalhar` not empty → `uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter coletar detalhes --run "$RUN"` (per-date searches with specific flights).
- `confirmar_milhas` not empty → `farehunter:miles-researcher` in mode `confirm` with those ids (live check on the program's site; it removes awards that are gone and updates miles/taxes).
- `pronto: true` → stop. Also stop when the browser page budget runs out; what was not validated simply stays out of the recommendation.
- **LATAM Pass** (only for LATAM flights, only if the user has a LATAM Pass balance worth using): ask the miles researcher for at most 3 date pairs; login is manual by the user. If they don't log in, skip it and say so in one line.

## 6. Final analysis (validated data only)
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter analisar --run "$RUN"
```
This mode ranks **only validated options** (cash with a specific flight fetched now, awards confirmed live) and writes the price history. `--exploratorio` exists only for debugging; never base an answer on it.

## 7. Answer — direct and complete
1. **One recommendation**, first line: what to buy, when, total cost, and the saving vs the plain cash reference. 1–3 sentences on **why** it wins, using only numbers from the report.
2. **The step-by-step plan** from the report ("How to do it"), in the user's language and complete: check availability → transfer points / buy miles (amounts, links, bonus deadlines) → book each award (flight, time, miles + taxes, link) → buy each cash ticket (flight, time, price, link) → separate-ticket instructions → bags → total → final checks. Never shorten it to "buy at X".
3. Then the short supporting data (top alternatives, date matrix, miles verdicts) and the sources that failed, if any.
- **Never present unvalidated numbers** (cache, calendar) as options, prices or estimates. Don't list them.
- **No menus at the end.** Don't ask "which path do you prefer?". Only if there is **no** validated option at all, say so plainly, say what could not be validated and why, and do the single most useful next step yourself (e.g. widen the window) instead of offering a list.

## Rules (mandatory)
- Never buy, book, transfer points or pay. Stop at the link.
- Never ask for, store or log passwords for loyalty programs, banks or cards.
- Recommend only what was validated in this run; prices still change until ticketing — say it once.
- If a source failed, say which one and what it means for the result (e.g. "without Google Flights, only 15 Kiwi options were compared").
- Mileage brokers (123milhas, MaxMilhas, HotMilhas…) are out of scope on purpose (legal and cancellation risk).
