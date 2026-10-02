# ✈️ FareHunter — flights & miles finder for Claude

**English** · [Português](README.pt-BR.md) · [Español](README.es.md)

Describe your trip in plain words — "New York to Lisbon on Nov 20, back Nov 27, 2 adults" or "Porto Alegre para Recife dia 20/11" — and FareHunter finds the **cheapest** way to do it. It compares:
- cash fares;
- nearby dates;
- miles you already have;
- buying miles;
- transferring card points;
- mixes (cash one way, miles the other).

You get a ranking in **your currency**, with links to book yourself.

- **Works from any country, in any currency.** It knows 30+ airline programs: United, American, Delta, Alaska, Aeroplan, Flying Blue, British Airways/Iberia/Qatar Avios, Miles & More, Turkish, Emirates, Singapore, Cathay, Qantas, LifeMiles, Copa, Aeroméxico, Smiles, LATAM Pass, Azul…
- **It also knows card points:** Amex, Chase, Citi, Capital One, Bilt, Livelo, Esfera… and their transfer partners.
- **Talks to you in your language.** The report comes in English, Portuguese or Spanish; Claude translates any other language.
- **Runs on your computer:** the Claude Desktop app (**Code** tab) on macOS and Windows, or Claude Code in the terminal on Linux. Nothing is hosted.
- **Everyone uses their own keys and accounts.** It **never buys, books or asks for passwords**.

## Install

### Option A — inside Claude Desktop (macOS / Windows, no terminal)

1. Install **Claude Desktop** from https://claude.ai/download and sign in. Your plan must include Claude Code.
2. Open **Settings** and, under *Customization*, click **Plugins**.
3. Click **+ Add** (top right) → **Add marketplace**.
4. In the **URL** field, type `s0beran0/farehunter` (or `https://github.com/s0beran0/farehunter`), choose **Use "…"** and click **Sync**.
5. On the **Discover** tab, **Farehunter** now appears. Click **Add** next to it.
6. Open the **Code** tab, pick any folder (e.g. `Documents/trips`) and type **`/farehunter:setup`**. It checks your computer and walks you through the one required tool (**uv**), with the exact link or command for your system.

> **Prefer typing?** Steps 2–5 can be replaced with these two commands in the Code tab's message box:
> ```
> /plugin marketplace add s0beran0/farehunter
> /plugin install farehunter@farehunter-marketplace
> ```

### Option B — one command in the terminal (macOS / Windows / Linux)

It installs everything that is missing and asks before each item:
- **uv**, required: runs the cost engine and downloads Python by itself;
- **Node.js**, optional: only for LATAM Pass and live price checks;
- **Git**;
- **Claude Code**, on Linux only (there is no Claude Desktop for Linux);
- the **plugin** itself.

- **macOS / Linux** (Terminal):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows** (PowerShell):
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

Then:
- **macOS / Windows:** quit and reopen Claude Desktop. In the **Code** tab, type `/farehunter:setup`.
- **Linux:** open a terminal, run `claude` (log in the first time) and type `/farehunter:setup`.

## Use

| Type | What it does |
|---|---|
| `/farehunter:profile` | A quick chat about your country, currency, airports, how many people travel, bags, and which miles and points programs you have. Once; change it any time. |
| `/farehunter:search New York to Lisbon Nov 20, back Nov 27, 2 adults` | The search. It asks for **today's balances** and shows the ranking. You can also just ask in your own words. |
| `/farehunter:miles` | Updates what each mile/point is worth and the active buy/transfer promotions. Shows the change and only saves if you approve. |
| `/farehunter:setup` | When something goes wrong, or to check the installation. |

> **Why does it ask for balances every time?** Balances change with every purchase, transfer or expiry. A stored, forgotten number would lead to wrong advice, so a balance only counts for that search.

## Optional

- **Seats.aero Pro** (US$ 9.99/month): without it, award availability is only available for flights departing within 60 days; with it, any date.
  - You save the key yourself, in your own terminal, so it never goes through the chat. `/farehunter:setup` shows the command.
  - Check that the "API" tab appears for your account before subscribing.
- **LATAM Pass:** LATAM's site only shows miles prices when you are logged in. When needed, a browser window opens and **you** log in there.

## Your data

It lives in `~/.farehunter/` (Windows: `C:\Users\<you>\.farehunter\`):
- profile;
- miles values;
- price history;
- keys (`.env`, only on your computer).

Updating or reinstalling the plugin never deletes it. Ask "where is my data?" to see the exact path.

## Update
In Claude Desktop: **Settings → Plugins → + Add → Manage marketplaces** and sync **farehunter-marketplace** to fetch the new version (the plugin list keeps showing the old description until you do). In the Code tab you can also type `/plugin`. From a terminal: `claude plugin update farehunter@farehunter-marketplace`.

## Limitations

- Prices change until ticketing. Award seats marked as **cached** must be checked on the program's site.
- Google Flights has no official API. If it fails, FareHunter says so and continues with Kiwi and the other sources.
- Award prices can be lower for club members or elite tiers. The report warns about it.
- Deep links that open the search with your route and dates already filled in exist for Smiles, LATAM and Azul. For other programs, the link opens the program's award-search page.
- Mileage brokers are left out on purpose: legal risk, and the ticket can be cancelled.

---

For developers: [docs/desenvolvimento.md](docs/desenvolvimento.md) · research: [docs/research.md](docs/research.md) · decisions: [docs/decisoes.md](docs/decisoes.md) · add a program: `config/programas.yaml` · add a language: `src/i18n/mensagens.py`.
