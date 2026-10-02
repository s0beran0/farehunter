# FareHunter installer for Windows (PowerShell).
# Usage (PowerShell):  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
# No admin rights needed. Only installs what is missing, and asks first.
$ErrorActionPreference = "Stop"

# Git URL (https avoids needing SSH keys) or a local folder, for testing.
$Repo = if ($env:FAREHUNTER_REPO) { $env:FAREHUNTER_REPO } else { "https://github.com/s0beran0/farehunter.git" }
$Marketplace = "farehunter-marketplace"
$Plugin = "farehunter"

# Language: FAREHUNTER_LANG, else the Windows UI language (pt / es / en).
$L = if ($env:FAREHUNTER_LANG) { $env:FAREHUNTER_LANG } else { (Get-UICulture).TwoLetterISOLanguageName }
if ($L -like "pt*") { $L = "pt" } elseif ($L -like "es*") { $L = "es" } else { $L = "en" }
function M($en, $pt, $es) { switch ($L) { "pt" { $pt } "es" { $es } default { $en } } }
function Ok($t) { Write-Host "✓ $t" -ForegroundColor Green }
function Warn($t) { Write-Host "• $t" -ForegroundColor Yellow }
function Ask($t) { $r = Read-Host "$t [Y/n]"; return ($r -eq "" -or $r -match "^[yYsS]") }
function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Write-Host "== FareHunter — $(M 'installation' 'instalação' 'instalación') (Windows) ==" -ForegroundColor Cyan

# 1) uv (required)
if (Has "uv") { Ok "uv ($(uv --version))" }
else {
  Warn "$(M 'uv is missing (Python manager by Astral). Official site:' 'Falta o uv (gerenciador de Python da Astral). Site oficial:' 'Falta uv (gestor de Python de Astral). Sitio oficial:') https://docs.astral.sh/uv/"
  if (Ask (M 'Install uv now?' 'Instalar o uv agora?' '¿Instalar uv ahora?')) {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    Ok "uv"
  } else { Warn (M 'FareHunter does not work without uv. Run this installer again any time.' 'Sem o uv o agente não funciona. Rode este instalador de novo quando quiser.' 'Sin uv el agente no funciona. Ejecuta este instalador de nuevo cuando quieras.') }
}

# 2) Node.js (optional)
if (Has "npx") { Ok "Node ($(node --version))" }
else {
  Warn (M 'Node.js not found. It is OPTIONAL: only for the automatic browser (LATAM Pass miles and live checks on Smiles).' 'Node.js não encontrado. É OPCIONAL: só para o navegador automático (milhas LATAM Pass e conferência ao vivo na Smiles).' 'Node.js no encontrado. Es OPCIONAL: solo para el navegador automático (millas LATAM Pass y verificación en vivo en Smiles).')
  if ((Has "winget") -and (Ask (M 'Install Node LTS with winget?' 'Instalar o Node LTS com o winget?' '¿Instalar Node LTS con winget?'))) {
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  } else { Warn "$(M 'Download the LTS (.msi):' 'Baixe a versão LTS (.msi):' 'Descarga la versión LTS (.msi):') https://nodejs.org/en/download" }
}

# 3) Git for Windows (Claude Code on Windows runs commands through Git Bash)
if (Has "git") { Ok "Git" }
else {
  Warn (M 'Git for Windows not found; Claude Code needs it on Windows.' 'Git for Windows não encontrado; o Claude Code precisa dele no Windows.' 'Git for Windows no encontrado; Claude Code lo necesita en Windows.')
  if ((Has "winget") -and (Ask (M 'Install Git with winget?' 'Instalar o Git com o winget?' '¿Instalar Git con winget?'))) {
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
  } else { Warn "$(M 'Download:' 'Baixe em:' 'Descarga:') https://git-scm.com/download/win" }
}

# 4) Plugin
if (Has "claude") {
  Ok "Claude Code"
  $mktOk = $false
  if ((claude plugin marketplace list 2>$null) -match $Marketplace) {
    claude plugin marketplace update $Marketplace 2>$null | Out-Null; $mktOk = $true
  } else {
    claude plugin marketplace add $Repo
    if ($LASTEXITCODE -eq 0) { $mktOk = $true }
    else { Warn (M 'Could not download the plugin. Check: internet connection, Git installed, and (while the repository is private) access to it.' 'Não foi possível baixar o plugin. Verifique: internet, Git instalado e (enquanto o repositório for privado) acesso a ele.' 'No se pudo descargar el plugin. Verifica: internet, Git instalado y (mientras el repositorio sea privado) acceso a él.') }
  }
  if ($mktOk) {
    claude plugin install "$Plugin@$Marketplace"
    if ($LASTEXITCODE -eq 0) { Ok (M 'Plugin installed' 'Plugin instalado' 'Plugin instalado') }
    else { Warn (M 'Plugin installation failed; see the message above.' 'A instalação do plugin falhou; veja a mensagem acima.' 'La instalación del plugin falló; mira el mensaje de arriba.') }
  }
} else {
  Warn (M "The 'claude' command is not in this terminal. Install the plugin from the app:" "O comando 'claude' não está no terminal. Instale o plugin pelo app:" "El comando 'claude' no está en la terminal. Instala el plugin desde la app:")
  Write-Host "  1. $(M 'Download Claude Desktop and sign in:' 'Baixe o Claude Desktop e entre na sua conta:' 'Descarga Claude Desktop e inicia sesión:') https://claude.ai/download"
  Write-Host "  2. $(M "Open the 'Code' tab and pick any folder (e.g. Documents\trips)" "Abra a aba 'Code' e escolha uma pasta qualquer (ex.: Documentos\viagens)" "Abre la pestaña 'Code' y elige cualquier carpeta (ej.: Documentos\viajes)")"
  Write-Host "  3. $(M 'In the message box, type:' 'Na caixa de mensagem, digite:' 'En el cuadro de mensaje, escribe:')"
  Write-Host "       /plugin marketplace add s0beran0/farehunter" -ForegroundColor White
  Write-Host "       /plugin install $Plugin@$Marketplace" -ForegroundColor White
}

Write-Host ""
Write-Host (M "Done. Next, open Claude (the Code tab in Claude Desktop, or run 'claude' in a terminal) and type:" "Pronto. Próximo passo: abra o Claude (aba Code do Claude Desktop, ou rode 'claude' no terminal) e digite:" "Listo. Siguiente paso: abre Claude (pestaña Code de Claude Desktop, o ejecuta 'claude' en una terminal) y escribe:") -ForegroundColor Cyan
Write-Host "   /farehunter:setup     $(M '-> checks everything and explains how to fix what is missing' '-> confere tudo e ensina a resolver o que faltar' '-> revisa todo y explica cómo resolver lo que falte')"
Write-Host "   /farehunter:profile   $(M '-> your airports and miles programs (once)' '-> seus aeroportos e programas de milhas (1 vez)' '-> tus aeropuertos y programas de millas (una vez)')"
Write-Host "   /farehunter:search    $(M 'São Paulo to Recife Nov 20, back Nov 27' 'São Paulo para Recife 20/11, volta 27/11' 'São Paulo a Recife 20/11, vuelta 27/11')"
