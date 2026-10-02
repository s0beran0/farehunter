# Install FareHunter in Claude Code (terminal)

**English** · [Português](claude-code.pt-BR.md) · [Español](claude-code.es.md)

For **macOS, Windows and Linux**. On Linux this is the only option, because there is no Claude Desktop there.

## One command
It installs whatever is missing and asks before each item:
- **uv**, required;
- **Node.js**, optional: only for LATAM Pass and live price checks;
- **Git**;
- **Claude Code**, on Linux;
- the **plugin**.

- **macOS / Linux** (Terminal):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows** (PowerShell):
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

Then open a terminal, run `claude` (log in the first time) and type `/farehunter:setup`.

## Or by hand
If you already have Claude Code ([install guide](https://code.claude.com/docs/en/setup)):
```bash
claude plugin marketplace add s0beran0/farehunter
claude plugin install farehunter@farehunter-marketplace
```
Then run `claude` and type `/farehunter:setup`. It shows you how to install **uv** if it's missing.

## Update
```bash
claude plugin marketplace update farehunter-marketplace
claude plugin update farehunter@farehunter-marketplace
```

---
Prefer the app? See [Install in Claude Desktop](claude-desktop.md).
