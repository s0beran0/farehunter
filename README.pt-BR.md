# ✈️ FareHunter

[English](README.md) · **Português** · [Español](README.es.md)

Um plugin para o Claude que encontra o **jeito mais barato de voar**. Ele compara tarifa em dinheiro, datas próximas, milhas que você já tem, compra de milhas e transferência de pontos do cartão. O resultado sai na sua moeda, com os links para você comprar ou emitir.

- Qualquer país e moeda. Mais de 30 programas de milhas (Smiles, LATAM Pass, Azul, United, Aeroplan, Flying Blue, Avios…) e pontos de cartão (Livelo, Esfera, Amex, Chase…).
- Conversa no seu idioma (Português, English, Español…).
- Roda no seu computador, com as suas contas. Ele **não compra, não emite e nunca pede senha**.

## Instalar

| | |
|---|---|
| 🖥️ **[Claude Desktop](docs/install/claude-desktop.pt-BR.md)** | Mac e Windows, sem terminal |
| ⌨️ **[Claude Code](docs/install/claude-code.pt-BR.md)** | Terminal: Mac, Windows e Linux |

## Usar

| Digite | Para quê |
|---|---|
| `/farehunter:profile` | Conte uma vez seus aeroportos e programas de milhas |
| `/farehunter:search Porto Alegre para Recife 20/11, volta 27/11` | Procura o jeito mais barato; também dá para pedir com suas palavras |
| `/farehunter:miles` | Atualiza quanto vale cada milha e as promoções ativas |
| `/farehunter:setup` | Confere a instalação quando algo der errado |

## Bom saber

- **Saldos:** ele pergunta seus saldos a cada busca, porque eles mudam o tempo todo. Nada sobre seus saldos fica guardado.
- **Preços:** mudam até a compra. Resgates marcados como **cache** precisam ser conferidos no site do programa.
- **Seus dados:** ficam em `~/.farehunter/`, no seu computador.
- **Extras opcionais:** o [Seats.aero Pro](https://seats.aero) libera a busca de resgates além de 60 dias. A LATAM Pass exige que você mesmo faça login no site da LATAM.

---
[Como funciona](docs/desenvolvimento.md) · [Pesquisa e fontes](docs/research.md) · [Decisões](docs/decisoes.md) · licença MIT
