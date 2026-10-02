# Instalar o FareHunter no Claude Code (terminal)

[English](claude-code.md) · **Português** · [Español](claude-code.es.md)

Para **Mac, Windows e Linux**. No Linux é a única opção, porque lá não existe Claude Desktop.

## Um comando
O instalador instala o que faltar e pergunta antes de cada item:
- **uv**, obrigatório;
- **Node.js**, opcional: só para LATAM Pass e conferência ao vivo;
- **Git**;
- **Claude Code**, no Linux;
- o **plugin**.

- **Mac / Linux** (Terminal):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows** (PowerShell):
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

Depois abra um terminal, rode `claude` (faça login na primeira vez) e digite `/farehunter:setup`.

## Ou na mão
Se você já tem o Claude Code ([guia de instalação](https://code.claude.com/docs/en/setup)):
```bash
claude plugin marketplace add s0beran0/farehunter
claude plugin install farehunter@farehunter-marketplace
```
Depois rode `claude` e digite `/farehunter:setup`. Ele mostra como instalar o **uv**, se faltar.

## Atualizar
```bash
claude plugin marketplace update farehunter-marketplace
claude plugin update farehunter@farehunter-marketplace
```

---
Prefere o app? Veja [Instalar no Claude Desktop](claude-desktop.pt-BR.md).
