#!/usr/bin/env bash
# FareHunter installer for macOS and Linux (on Linux it also offers to install Claude Code, since there is no Claude Desktop).
# Usage:  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
# No sudo needed. Only installs what is missing, and asks first.
set -euo pipefail

# Git URL (https avoids needing SSH keys) or a local folder, for testing.
REPO="${FAREHUNTER_REPO:-https://github.com/s0beran0/farehunter.git}"
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
  if { : </dev/tty; } 2>/dev/null; then read -r -p "$1 [Y/n] " r </dev/tty 2>/dev/null || true; fi
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
  elif [ "$OS" = "Linux" ]; then
    warn "$(m "Install the LTS with your package manager (e.g. 'sudo apt install nodejs npm' or 'sudo dnf install nodejs') or from:" "Instale a versão LTS pelo gerenciador de pacotes (ex.: 'sudo apt install nodejs npm' ou 'sudo dnf install nodejs') ou pelo site:" "Instala la versión LTS con tu gestor de paquetes (ej.: 'sudo apt install nodejs npm' o 'sudo dnf install nodejs') o desde:") https://nodejs.org/en/download"
  else
    warn "$(m "Download the LTS version:" "Baixe a versão LTS:" "Descarga la versión LTS:") https://nodejs.org/en/download"
  fi
fi

# 2a) git (Claude downloads plugins with git)
if command -v git >/dev/null 2>&1; then
  ok "git"
else
  if [ "$OS" = "Darwin" ]; then
    warn "$(m "git not found. Install Apple's command line tools (a window will open):" "git não encontrado. Instale as ferramentas de linha de comando da Apple (uma janela vai abrir):" "git no encontrado. Instala las herramientas de línea de comandos de Apple (se abrirá una ventana):") xcode-select --install"
    if ask "$(m "Run it now?" "Rodar agora?" "¿Ejecutar ahora?")"; then xcode-select --install || true; fi
  else
    warn "$(m "git not found. Install it with your package manager, e.g.:" "git não encontrado. Instale pelo gerenciador de pacotes, ex.:" "git no encontrado. Instálalo con tu gestor de paquetes, ej.:") sudo apt install git  |  sudo dnf install git"
  fi
fi

# 2b) Linux: there is no Claude Desktop — use Claude Code in the terminal
if [ "$OS" = "Linux" ] && ! command -v claude >/dev/null 2>&1; then
  warn "$(m "Claude Desktop is not available for Linux; FareHunter runs in Claude Code (terminal). Official installer:" "O Claude Desktop não existe para Linux; o FareHunter roda no Claude Code (terminal). Instalador oficial:" "Claude Desktop no existe para Linux; FareHunter corre en Claude Code (terminal). Instalador oficial:") https://code.claude.com/docs/en/setup"
  if ask "$(m "Install Claude Code now?" "Instalar o Claude Code agora?" "¿Instalar Claude Code ahora?")"; then
    curl -fsSL https://claude.ai/install.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

# 3) Plugin
echo
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code ($(claude --version 2>/dev/null | head -1))"
  if claude plugin marketplace list 2>/dev/null | grep -q "$MARKETPLACE"; then
    claude plugin marketplace update "$MARKETPLACE" >/dev/null 2>&1 || true
    MKT_OK=1
  elif claude plugin marketplace add "$REPO"; then
    MKT_OK=1
  else
    MKT_OK=0
    warn "$(m "Could not download the plugin. Check: internet connection, git installed, and (while the repository is private) access to it." "Não foi possível baixar o plugin. Verifique: internet, git instalado e (enquanto o repositório for privado) acesso a ele." "No se pudo descargar el plugin. Verifica: internet, git instalado y (mientras el repositorio sea privado) acceso a él.")"
  fi
  if [ "$MKT_OK" = 1 ]; then
    if claude plugin install "$PLUGIN@$MARKETPLACE"; then
      ok "$(m "Plugin installed" "Plugin instalado" "Plugin instalado")"
    else
      warn "$(m "Plugin installation failed; see the message above." "A instalação do plugin falhou; veja a mensagem acima." "La instalación del plugin falló; mira el mensaje de arriba.")"
    fi
  fi
else
  if [ "$OS" = "Linux" ]; then
    warn "$(m "Claude Code was not installed. Install it later with: curl -fsSL https://claude.ai/install.sh | bash — then run this installer again." "O Claude Code não foi instalado. Instale depois com: curl -fsSL https://claude.ai/install.sh | bash — e rode este instalador de novo." "Claude Code no se instaló. Instálalo después con: curl -fsSL https://claude.ai/install.sh | bash — y vuelve a ejecutar este instalador.")"
  else
  warn "$(m "The 'claude' command is not in this terminal. Install the plugin from the app:" "O comando 'claude' não está no terminal. Instale o plugin pelo app:" "El comando 'claude' no está en la terminal. Instala el plugin desde la app:")"
  echo "  1. $(m "Download Claude Desktop and sign in:" "Baixe o Claude Desktop e entre na sua conta:" "Descarga Claude Desktop e inicia sesión:") https://claude.ai/download"
  echo "  2. $(m "Open the 'Code' tab and pick any folder (e.g. Documents/trips)" "Abra a aba 'Code' e escolha uma pasta qualquer (ex.: Documentos/viagens)" "Abre la pestaña 'Code' y elige cualquier carpeta (ej.: Documentos/viajes)")"
  echo "  3. $(m "In the message box, type:" "Na caixa de mensagem, digite:" "En el cuadro de mensaje, escribe:")"
  bold "       /plugin marketplace add s0beran0/farehunter"
  bold "       /plugin install $PLUGIN@$MARKETPLACE"
  fi
fi

echo
if [ "$OS" = "Linux" ]; then
  bold "$(m "Done. Next: open a terminal in any folder, run 'claude' (log in the first time) and type:" "Pronto. Próximo passo: abra um terminal numa pasta qualquer, rode 'claude' (faça login na primeira vez) e digite:" "Listo. Siguiente paso: abre una terminal en cualquier carpeta, ejecuta 'claude' (inicia sesión la primera vez) y escribe:")"
else
  bold "$(m "Done. Next, in Claude's Code tab:" "Pronto. Próximo passo, na aba Code do Claude:" "Listo. Siguiente paso, en la pestaña Code de Claude:")"
fi
echo "   /farehunter:setup     $(m "→ checks everything and explains how to fix what is missing" "→ confere tudo e ensina a resolver o que faltar" "→ revisa todo y explica cómo resolver lo que falte")"
echo "   /farehunter:profile   $(m "→ your airports and miles programs (once)" "→ seus aeroportos e programas de milhas (1 vez)" "→ tus aeropuertos y programas de millas (una vez)")"
echo "   /farehunter:search    $(m "São Paulo to Recife Nov 20, back Nov 27" "São Paulo para Recife 20/11, volta 27/11" "São Paulo a Recife 20/11, vuelta 27/11")"
