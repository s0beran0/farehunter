---
name: profile
description: Interview the user (home airport, alternative airports, travellers, checked bag, which miles and card-points programs they have, club/elite status, language) and save their travel profile. Balances are NOT stored — they are asked on every search. Also updates a single item, e.g. "/farehunter:profile I'm Smiles Diamond now".
argument-hint: "[optional: what changed, e.g. 'I joined Clube Smiles']"
---

User context: $ARGUMENTS

> If any `uv` command fails with "command not found" (or `uv` is not recognized), stop and follow the `/farehunter:setup` skill.

You fill in the profile **for the user**, asking in plain language, **in their language** (the language of their message). You **never edit the YAML by hand**: collect the answers into JSON and save them with the validated command below.

## 0. What already exists
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter perfil status
```
- `configurado: false` → full interview (blocks 1–4).
- Already configured and `$ARGUMENTS` says what changed → ask only about that and go to step 5 with a partial JSON.
- Already configured, no arguments → show a short summary of the current profile and ask what to change.

## 1–4. Interview
Use the multiple-choice question tool when there are options; free text for numbers and names. At most 4 questions at a time. Always accept "don't know / skip" (keeps the default).

**Block 1 — Trips**
- Which city/airport do you usually fly from? Accept a city name and convert to IATA (e.g. "Porto Alegre" → POA; "São Paulo" → ask GRU, CGH or both). Confirm the code when in doubt.
- Would you fly from another airport if it were cheaper? If yes: which, and how much it costs to get there **per person, per trip** (bus/ride/parking) → `custo_deslocamento_brl` (BRL).
- How many people usually travel? → `passageiros_padrao`
- Do you usually check a bag? → `bagagem_despachada`
- Store the user's language as `idioma`: `pt`, `en` or `es` (other languages → `en`; you will still talk to them in their language).

**Block 2 — Miles programs**
- Which programs do you have an account with? (multi-select: Smiles, LATAM Pass, Azul Fidelidade, none) → `programas.<smiles|latam_pass|azul>.tem_conta: true`
- For each: do you pay for the program's club, and what is your tier (e.g. Smiles Prata/Ouro/Diamante; Azul Topázio/Safira/Diamante; LATAM Gold/Platinum/Black)? → `clube`, `categoria`
- **Do not ask for balances here.** Say in one sentence: "balances change all the time, so I ask on every search".

**Block 3 — Card points**
- Which card-points programs do you have? (multi-select: Livelo, Esfera, Inter Loop, C6 Átomos, other) → `pontos_programas`. No balances.

**Block 4 — Preferences (offer the defaults)**
- How many days of date flexibility, before/after? (default 3) → `flex_dias_padrao`
- Below how much savings is it not worth buying miles / transferring points / using another airport? (default R$ 50) → `valor_minimo_economia_brl`

## 5. Preview and save
1. Build a JSON with only what was answered (the rest keeps the current/default value), e.g.:
   ```json
   {"idioma": "en", "aeroportos_origem": ["POA"],
    "aeroportos_alternativos_origem": [{"iata": "CXJ", "custo_deslocamento_brl": 90, "observacao": "2h drive"}],
    "passageiros_padrao": 2, "bagagem_despachada": true,
    "programas": {"smiles": {"tem_conta": true, "clube": true, "categoria": "Prata"}},
    "pontos_programas": ["livelo", "inter_loop"],
    "flex_dias_padrao": 3, "valor_minimo_economia_brl": 50}
   ```
2. Preview through standard input (no temp files):
   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter perfil salvar --simular <<'JSON'
   {"aeroportos_origem": ["POA"], "...": "..."}
   JSON
   ```
   If it prints `PERFIL INVÁLIDO`, explain the problem simply, ask again only for that field and retry.
3. Show the user a **short bullet summary** (not raw YAML) and ask "Can I save it?".
4. On "yes", run the same command **without** `--simular` and confirm it was saved.

## Rules
- Never ask for passwords, ID numbers, card numbers or logins.
- Never store balances in the profile (the command refuses). Balances belong to a search, not to the person.
- Don't invent a tier: if unknown, leave it empty and say it can be changed later with `/farehunter:profile`.
