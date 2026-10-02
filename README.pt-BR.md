# ✈️ FareHunter — passagens e milhas no Claude

[English](README.md) · **Português** · [Español](README.es.md)

Você descreve a viagem com suas palavras — "Porto Alegre para Recife dia 20/11, volta 27/11, 2 adultos" ou "Nova York para Lisboa em novembro" — e o FareHunter procura o jeito **mais barato** de fazê-la. Ele compara:
- tarifa em dinheiro;
- datas próximas;
- milhas que você já tem;
- compra de milhas;
- transferência de pontos do cartão;
- misturas (ida em dinheiro + volta em milhas).

No fim entrega um ranking **na sua moeda**, com os links para você comprar ou emitir.

- **Funciona saindo de qualquer país, em qualquer moeda.** Conhece mais de 30 programas de cias aéreas: Smiles, LATAM Pass, Azul, United, American, Delta, Aeroplan, Flying Blue, Avios (British/Iberia/Qatar), Miles & More, Turkish, Emirates, Singapore, LifeMiles, Copa…
- **Também conhece pontos de cartão:** Livelo, Esfera, Inter Loop, C6 Átomos, Amex, Chase, Citi, Capital One, Bilt… e com quais programas cada um transfere.
- **Conversa no seu idioma.** O relatório sai em português, inglês ou espanhol; outros idiomas o Claude traduz.
- **Roda no seu computador:** no app Claude Desktop (aba **Code**) no Mac e no Windows, ou no Claude Code pelo terminal no Linux. Nada fica hospedado em servidor.
- **Cada pessoa usa as próprias chaves e contas.** Ele **não compra, não emite e nunca pede senha**.

## Instalar

### Opção A — pelo Claude Desktop (Mac / Windows, sem terminal)

1. Instale o **Claude Desktop**: https://claude.ai/download. Entre com sua conta; o plano precisa incluir o Claude Code.
2. Abra a aba **Code** e escolha uma pasta qualquer, por exemplo `Documentos/viagens`.
3. Clique no botão **+** ao lado da caixa de mensagem → **Plugins** → **Add plugin**.
4. No navegador de plugins, adicione o marketplace **`s0beran0/farehunter`** (o repositório no GitHub).
5. Encontre **farehunter** na lista e clique em **Install**.
6. Na caixa de mensagem, digite **`/farehunter:setup`**. Ele confere seu computador e ensina a instalar a única ferramenta obrigatória (**uv**), com o link ou o comando exato para o seu sistema.

> **Prefere digitar?** Os passos 3 a 5 podem ser trocados por estes dois comandos na caixa de mensagem da aba Code:
> ```
> /plugin marketplace add s0beran0/farehunter
> /plugin install farehunter@farehunter-marketplace
> ```

### Opção B — um comando no terminal (Mac / Windows / Linux)

O instalador instala o que falta e pergunta antes de cada item:
- **uv**, obrigatório;
- **Node.js**, opcional: só para LATAM Pass e conferência ao vivo;
- **Git**;
- **Claude Code**, só no Linux, onde não existe Claude Desktop;
- o próprio **plugin**.

- **Mac / Linux** (Terminal):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows** (PowerShell):
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

Depois:
- **Mac / Windows:** feche e abra o Claude Desktop e, na aba **Code**, digite `/farehunter:setup`.
- **Linux:** abra um terminal, rode `claude` (faça login na primeira vez) e digite `/farehunter:setup`.

## Usar

| Digite | Para quê |
|---|---|
| `/farehunter:profile` | Uma conversa rápida sobre país, moeda, aeroportos, quantas pessoas viajam, mala e em quais programas de milhas e pontos você tem conta. Feita uma vez; dá para ajustar quando quiser. |
| `/farehunter:search Porto Alegre para Recife 20/11, volta 27/11, 2 adultos` | A busca. Ele pergunta seus **saldos de hoje** e mostra o ranking. Também dá para só pedir com suas palavras. |
| `/farehunter:miles` | Atualiza quanto vale cada milha/ponto e as promoções de compra e transferência ativas. Mostra a mudança e só grava se você aprovar. |
| `/farehunter:setup` | Quando algo der erro ou para conferir a instalação. |

> **Por que ele pergunta o saldo toda vez?** Saldo muda a cada compra, transferência ou vencimento. Um número salvo e esquecido levaria a recomendações erradas, então o saldo vale só para aquela busca.

## Opcionais

- **Seats.aero Pro** (US$ 9,99/mês): sem ele, a disponibilidade de resgates aparece só para voos que saem em até 60 dias; com ele, qualquer data.
  - A chave é gravada por você mesmo, no seu terminal, sem passar pela conversa. O `/farehunter:setup` mostra o comando.
  - Confira se a aba "API" aparece na sua conta antes de assinar.
- **LATAM Pass:** o site só mostra milhas com login. Quando precisar, abre uma janela do navegador e **você** faz o login ali.

## Seus dados

Ficam em `~/.farehunter/` (no Windows, `C:\Users\<você>\.farehunter\`):
- perfil;
- valores de milheiro;
- histórico de preços;
- chaves (`.env`, só no seu computador).

Atualizar ou reinstalar o plugin não apaga nada. Pergunte "onde ficam meus dados?" para ver o caminho exato.

## Atualizar
No Claude Desktop (aba Code), clique em **+** → **Plugins** → **Manage plugins**, ou digite `/plugin`. Pelo terminal: `claude plugin update farehunter@farehunter-marketplace`.

## Limitações

- Preços mudam até a emissão. Resgates marcados como **cache** precisam ser conferidos no site do programa.
- Google Flights não tem API oficial. Se ele falhar, o agente avisa e segue com o Kiwi e as outras fontes.
- O preço em milhas pode ser menor para quem tem clube ou categoria. O relatório avisa.
- Smiles, LATAM e Azul têm link que já abre a busca com rota e data. Nos outros programas, o link abre a página de busca de resgates do programa.
- Balcões de milhas ficam de fora de propósito: risco jurídico e de cancelamento do bilhete.
