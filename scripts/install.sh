#!/usr/bin/env bash
# FareHunter installer for macOS and Linux.
# Usage:  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
# No sudo needed. Only installs what is missing, and asks first.
set -euo pipefail

REPO="${FAREHUNTER_REPO:-s0beran0/farehunter}"
MARKETPLACE="farehunter-marketplace"
PLUGIN="farehunter"

# Language: FAREHUNTER_LANG, else the system locale (pt / es / en).
L="${FAREHUNTER_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}}"
case "$L" in pt*) L=pt ;; es*) L=es ;; *) L=en ;; esac
m() {  # m "english" "português" "español"
  case "$L" in pt) printf '%s' "$2" ;; es) printf '%s' "$3" ;; *) printf '%s' "$1" ;; esac
}
ok() { printf '\033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m• %s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ask() {  # works even with "curl | bash" (reads from the terminal)
  local r=""
  if [ -r /dev/tty ]; then read -r -p "$1 [Y/n] " r </dev/tty || true; fi
  case "${r:-y}" in [yYsS]*) return 0 ;; *) return 1 ;; esac
}

OS="$(uname -s)"
bold "== FareHunter — $(m "installation" "instalação" "instalación") ($OS) =="
echo

# 1) uv (runs the Python cost engine; installs Python by itself)
if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version | awk '{print $2}')"
else
  warn "$(m "uv is missing (Python manager by Astral). Official installer:" "Falta o uv (gerenciador de Python da Astral). Instalador oficial:" "Falta uv (gestor de Python de Astral). Instalador oficial:") https://docs.astral.sh/uv/"
  if ask "$(m "Install uv now?" "Instalar o uv agora?" "¿Instalar uv ahora?")"; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv"
  else
    warn "$(m "FareHunter does not work without uv. Install later with:" "Sem o uv o agente não funciona. Instale depois com:" "Sin uv el agente no funciona. Instálalo después con:") curl -LsSf https://astral.sh/uv/install.sh | sh"
  fi
fi

# 2) Node.js (optional: browser for LATAM Pass and live price checks)
if command -v npx >/dev/null 2>&1; then
  ok "Node $(node --version)"
else
  warn "$(m "Node.js not found. It is OPTIONAL: only for the automatic browser (LATAM Pass miles and live checks on Smiles)." "Node.js não encontrado. É OPCIONAL: só para o navegador automático (milhas LATAM Pass e conferência ao vivo na Smiles)." "Node.js no encontrado. Es OPCIONAL: solo para el navegador automático (millas LATAM Pass y verificación en vivo en Smiles).")"
  if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    if ask "$(m "Install Node with Homebrew (brew install node)?" "Instalar o Node com o Homebrew (brew install node)?" "¿Instalar Node con Homebrew (brew install node)?")"; then brew install node; fi
  else
    warn "$(m "Download the LTS version:" "Baixe a versão LTS:" "Descarga la versión LTS:") https://nodejs.org/en/download"
  fi
fi

# 3) Plugin
echo
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code ($(claude --version 2>/dev/null | head -1))"
  claude plugin marketplace add "$REPO" || warn "$(m "(marketplace already added)" "(marketplace já adicionado)" "(marketplace ya agregado)")"
  claude plugin install "$PLUGIN@$MARKETPLACE" && ok "$(m "Plugin installed" "Plugin instalado" "Plugin instalado")"
else
  warn "$(m "The 'claude' command is not in this terminal. Install the plugin from the app:" "O comando 'claude' não está no terminal. Instale o plugin pelo app:" "El comando 'claude' no está en la terminal. Instala el plugin desde la app:")"
  echo "  1. $(m "Download Claude Desktop and sign in:" "Baixe o Claude Desktop e entre na sua conta:" "Descarga Claude Desktop e inicia sesión:") https://claude.ai/download"
  echo "  2. $(m "Open the 'Code' tab and pick any folder (e.g. Documents/trips)" "Abra a aba 'Code' e escolha uma pasta qualquer (ex.: Documentos/viagens)" "Abre la pestaña 'Code' y elige cualquier carpeta (ej.: Documentos/viajes)")"
  echo "  3. $(m "In the message box, type:" "Na caixa de mensagem, digite:" "En el cuadro de mensaje, escribe:")"
  bold "       /plugin marketplace add $REPO"
  bold "       /plugin install $PLUGIN@$MARKETPLACE"
fi

echo
bold "$(m "Done. Next, in Claude's Code tab:" "Pronto. Próximo passo, na aba Code do Claude:" "Listo. Siguiente paso, en la pestaña Code de Claude:")"
echo "   /farehunter:setup     $(m "→ checks everything and explains how to fix what is missing" "→ confere tudo e ensina a resolver o que faltar" "→ revisa todo y explica cómo resolver lo que falte")"
echo "   /farehunter:profile   $(m "→ your airports and miles programs (once)" "→ seus aeroportos e programas de milhas (1 vez)" "→ tus aeropuertos y programas de millas (una vez)")"
echo "   /farehunter:search    $(m "São Paulo to Recife Nov 20, back Nov 27" "São Paulo para Recife 20/11, volta 27/11" "São Paulo a Recife 20/11, vuelta 27/11")"
