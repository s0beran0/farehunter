# ✈️ FareHunter — flights & miles finder for Claude

**English** · [Português](README.pt-BR.md) · [Español](README.es.md)

Describe your trip in plain words, in English, Portuguese or Spanish — for example "Porto Alegre to Recife on Nov 20, back Nov 27, 2 adults". FareHunter finds the **cheapest** way to do it. It compares:
- cash fares;
- nearby dates;
- miles you already have;
- buying miles;
- transferring card points;
- mixes (cash one way, miles the other).

You get a ranking in BRL with the links to book yourself.

- Focused on trips **from or within Brazil** (Smiles, LATAM Pass, Azul Fidelidade, Livelo, Esfera; prices in BRL).
- **Runs on your computer**: in the Claude Desktop app (**Code** tab) on macOS and Windows, or in Claude Code in the terminal on Linux. Nothing is hosted.
- **Everyone uses their own keys and accounts.** It **never buys, books or asks for passwords**.
- Talks to you in your language. The report comes in English, Portuguese or Spanish; Claude translates other languages.

## Install (once, ~5 minutes)

**1. Get Claude Desktop** (macOS/Windows): https://claude.ai/download. Sign in (your plan must include Claude Code). On **Linux** there is no Claude Desktop: the installer below offers to install Claude Code for the terminal.

**2. Run the installer.** It checks what is missing and asks before installing anything.

- **macOS:** open **Terminal** (Cmd+Space, type "Terminal") and paste:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows:** open **PowerShell** (Start menu, type "PowerShell") and paste:
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```
- **Linux:** open a terminal and paste (the same script as macOS; it also offers to install [Claude Code](https://code.claude.com/docs/en/setup)):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```

It takes care of:
- **uv**, required: runs the cost engine and downloads Python by itself;
- **Node.js**, optional: only for LATAM Pass miles and for live price checks on Smiles;
- **Git**, on Windows only;
- the **plugin** itself.

**3. (macOS/Windows) If the installer said it couldn't find the `claude` command**, install the plugin from the app. Open Claude Desktop → **Code** tab → pick any folder (e.g. `Documents/trips`) and type:
```
/plugin marketplace add s0beran0/farehunter
/plugin install farehunter@farehunter-marketplace
```

**4. Quit and reopen Claude Desktop** and, in the Code tab, type the command below. On **Linux**, open a terminal in any folder, run `claude` (log in the first time) and type it there:
```
/farehunter:setup
```
It checks everything (internet, uv, Node, keys) and calmly explains whatever is still missing, with links and ready-to-paste commands.

## Use

| Type | What it does |
|---|---|
| `/farehunter:profile` | A quick chat about your airports, how many people travel, bags, which miles and points programs you have, and your language. Done once; change it any time. |
| `/farehunter:search São Paulo to Recife Nov 20, back Nov 27, 2 adults` | The search. It asks for **today's balances** and shows the ranking. You can also just ask in your own words. |
| `/farehunter:miles` | Updates what each mile is worth and the active buy/transfer promotions. Shows the change and only saves if you approve. |
| `/farehunter:setup` | When something goes wrong, or to check the installation. |

> **Why does it ask for balances every time?** Balances change with every purchase, transfer or expiry. A stored, forgotten number would lead to wrong advice, so a balance only counts for that search.

## Optional

- **Seats.aero Pro** (US$ 9.99/month): without it, Smiles and Azul miles only show for flights departing within 60 days; with it, any date.
  - You save the key yourself, in your own terminal, so it never goes through the chat. `/farehunter:setup` shows the command.
  - Check that the "API" tab appears for your account before subscribing.
- **LATAM Pass:** LATAM's site only shows miles prices when you are logged in. When needed, a browser window opens and **you** log in there. The session stays in the plugin's browser.

## Your data

It lives in `~/.farehunter/` (on Windows, `C:\Users\<you>\.farehunter\`; on Linux, `/home/<you>/.farehunter/`):
- profile;
- miles values;
- price history;
- keys (`.env`, only on your computer).

Updating or reinstalling the plugin never deletes it. To see the exact path, ask "where is my data?".

## Update
In Claude Desktop (Code tab), type `/plugin`, open **farehunter** and choose update. From a terminal: `claude plugin update farehunter@farehunter-marketplace`.

## Limitations

- Prices change until ticketing. Miles marked as **cached** must be checked on the program's site.
- Google Flights has no official API. If it fails, FareHunter says so and continues with the other sources.
- Miles prices can be lower for club members or elite tiers (e.g. Clube Smiles, ~8%). The report warns about it.
- Mileage brokers (123milhas, MaxMilhas) are left out on purpose: legal risk, and the ticket can be cancelled.

---

For developers: [docs/desenvolvimento.md](docs/desenvolvimento.md) (Portuguese) · source research: [docs/research.md](docs/research.md) · decisions: [docs/decisoes.md](docs/decisoes.md). To add a language, see "Idiomas" in the developer doc.
