# Instalar FareHunter en Claude Code (terminal)

[English](claude-code.md) · [Português](claude-code.pt-BR.md) · **Español**

Para **Mac, Windows y Linux**. En Linux es la única opción, porque allí no existe Claude Desktop.

## Un comando
El instalador instala lo que falte y pregunta antes de cada cosa:
- **uv**, obligatorio;
- **Node.js**, opcional: solo para LATAM Pass y verificación en vivo;
- **Git**;
- **Claude Code**, en Linux;
- el **plugin**.

- **Mac / Linux** (Terminal):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows** (PowerShell):
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

Después abre una terminal, ejecuta `claude` (inicia sesión la primera vez) y escribe `/farehunter:setup`.

## O a mano
Si ya tienes Claude Code ([guía de instalación](https://code.claude.com/docs/en/setup)):
```bash
claude plugin marketplace add s0beran0/farehunter
claude plugin install farehunter@farehunter-marketplace
```
Después ejecuta `claude` y escribe `/farehunter:setup`. Te muestra cómo instalar **uv** si falta.

## Actualizar
```bash
claude plugin marketplace update farehunter-marketplace
claude plugin update farehunter@farehunter-marketplace
```

---
¿Prefieres la app? Mira [Instalar en Claude Desktop](claude-desktop.es.md).
