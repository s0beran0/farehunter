# ✈️ FareHunter — passagens e milhas no Claude

[English](README.md) · **Português** · [Español](README.es.md)

Você descreve a viagem com suas palavras (em português, inglês ou espanhol), por exemplo "Porto Alegre para Recife dia 20/11, volta 27/11, 2 adultos". O FareHunter procura o jeito **mais barato** de fazê-la. Ele compara:
- tarifa em dinheiro;
- datas próximas;
- milhas que você já tem;
- compra de milhas;
- transferência de pontos do cartão;
- misturas (ida em dinheiro + volta em milhas).

No fim entrega um ranking em reais, com os links para você comprar ou emitir.

- Feito para viagens **saindo do Brasil ou dentro dele** (Smiles, LATAM Pass, Azul Fidelidade, Livelo, Esfera; preços em BRL).
- **Roda no seu computador**, no app Claude Desktop (aba **Code**). Nada fica hospedado em servidor.
- **Cada pessoa usa as próprias chaves e contas.** Ele **não compra, não emite e nunca pede senha**.
- Conversa no seu idioma. O relatório sai em português, inglês ou espanhol; outros idiomas o Claude traduz.

## Instalar (uma vez, ~5 minutos)

**1. Tenha o Claude Desktop:** https://claude.ai/download. Entre com sua conta (precisa de um plano que inclua o Claude Code).

**2. Rode o instalador.** Ele confere o que falta e pergunta antes de instalar cada coisa.

- **Mac:** abra o **Terminal** (Cmd+Espaço, digite "Terminal") e cole:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows:** abra o **PowerShell** (menu Iniciar, digite "PowerShell") e cole:
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

O instalador cuida de:
- **uv**, obrigatório: roda o motor de cálculo e baixa o Python sozinho;
- **Node.js**, opcional: só para milhas LATAM Pass e para conferir preço ao vivo na Smiles;
- **Git**, só no Windows;
- o próprio **plugin**.

**3. Se o instalador disse que não achou o comando `claude`**, instale o plugin pelo app. Abra o Claude Desktop → aba **Code** → escolha uma pasta qualquer (ex.: `Documentos/viagens`) e digite:
```
/plugin marketplace add s0beran0/farehunter
/plugin install farehunter@farehunter-marketplace
```

**4. Feche e abra o Claude Desktop.** Na aba Code, digite:
```
/farehunter:setup
```
Ele confere tudo (internet, uv, Node, chaves) e explica com calma o que ainda faltar, com links e comandos prontos.

## Usar

| Digite | Para quê |
|---|---|
| `/farehunter:profile` | Uma conversa rápida sobre seus aeroportos, quantas pessoas viajam, mala, em quais programas de milhas e pontos você tem conta e seu idioma. Feita uma vez; dá para ajustar quando quiser. |
| `/farehunter:search São Paulo para Recife 20/11, volta 27/11, 2 adultos` | A busca. Ele pergunta seus **saldos de hoje** e mostra o ranking. Também dá para só pedir com suas palavras. |
| `/farehunter:miles` | Atualiza quanto vale cada milha e as promoções de compra e transferência ativas. Mostra a mudança e só grava se você aprovar. |
| `/farehunter:setup` | Quando algo der erro ou para conferir a instalação. |

> **Por que ele pergunta o saldo toda vez?** Saldo muda a cada compra, transferência ou vencimento. Um número salvo e esquecido levaria a recomendações erradas, então o saldo vale só para aquela busca.

## Opcionais

- **Seats.aero Pro** (US$ 9,99/mês): sem ele, as milhas Smiles e Azul aparecem só para voos que saem em até 60 dias; com ele, qualquer data.
  - A chave é gravada por você mesmo, no seu terminal, sem passar pela conversa. O `/farehunter:setup` mostra o comando.
  - Confira se a aba "API" aparece na sua conta antes de assinar.
- **LATAM Pass:** o site só mostra milhas com login. Quando precisar, abre uma janela do navegador e **você** faz o login ali. A sessão fica guardada no navegador do plugin.

## Seus dados

Ficam em `~/.farehunter/` (no Windows, `C:\Users\<você>\.farehunter\`):
- perfil;
- valores de milheiro;
- histórico de preços;
- chaves (`.env`, só no seu computador).

Atualizar ou reinstalar o plugin não apaga nada. Para ver o caminho exato, pergunte "onde ficam meus dados?".

## Atualizar
No Claude Desktop (aba Code), digite `/plugin`, abra **farehunter** e escolha atualizar. Pelo terminal: `claude plugin update farehunter@farehunter-marketplace`.

## Limitações

- Preços mudam até a emissão. Milhas marcadas como **cache** precisam ser conferidas no site do programa.
- Google Flights não tem API oficial. Se ele falhar, o agente avisa e segue com as outras fontes.
- O preço em milhas pode ser menor para quem tem Clube ou categoria (ex.: Clube Smiles, ~8%). O relatório avisa.
- Balcões de milhas (123milhas, MaxMilhas) ficam de fora de propósito: risco jurídico e de cancelamento do bilhete.
