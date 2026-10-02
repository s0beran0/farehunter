# ✈️ FareHunter

**English** · [Português](README.pt-BR.md) · [Español](README.es.md)

A plugin for Claude that finds the **cheapest way to fly**. It compares cash fares, nearby dates, miles you already have, buying miles and transferring card points. Results come in your currency, with links to book yourself.

- Any country and currency. 30+ airline programs (United, Aeroplan, Flying Blue, Avios, Smiles, LATAM Pass…) and card points (Amex, Chase, Citi, Livelo…).
- Talks to you in your language (English, Português, Español…).
- Runs on your computer with your own accounts. It **never buys, books or asks for passwords**.

## Install

| | |
|---|---|
| 🖥️ **[Claude Desktop](docs/install/claude-desktop.md)** | macOS and Windows, no terminal |
| ⌨️ **[Claude Code](docs/install/claude-code.md)** | Terminal: macOS, Windows and Linux |

## Use

| Type | What it does |
|---|---|
| `/farehunter:profile` | Tell it once about your airports and miles programs |
| `/farehunter:search New York to Lisbon Nov 20, back Nov 27` | Find the cheapest way, or just ask in your own words |
| `/farehunter:miles` | Refresh what each mile is worth and current promotions |
| `/farehunter:setup` | Check the installation when something goes wrong |

## Good to know

- **Balances:** it asks for your balances on every search, because they change all the time. Nothing about your balances is stored.
- **Prices:** they change until you buy. Award seats marked as **cached** must be checked on the program's site.
- **Your data:** it stays in `~/.farehunter/` on your computer.
- **Optional extras:** [Seats.aero Pro](https://seats.aero) adds award search beyond 60 days. LATAM Pass needs you to log in on LATAM's site yourself.

---
[How it works](docs/desenvolvimento.md) · [Research and sources](docs/research.md) · [Decisions](docs/decisoes.md) · MIT license
