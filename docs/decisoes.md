# Decisões

Por que cada ferramenta e cada regra foi escolhida, e o resultado de cada fase. Base: `docs/research.md` (2026-10-02).

## Ferramentas

| Necessidade | Escolha | Por quê | Alternativas descartadas ou em reserva |
|---|---|---|---|
| Dinheiro, data fixa | **fli** (`flights==0.9.0`) + **Kiwi** | O fli traz a cobertura do Google (129 resultados; achou R$ 618 que o Kiwi não tinha). O Kiwi é canal oficial e estável e serve de segunda opinião. Os dois são deduplicados por número de voo. | fast-flights (perde tarifas), google-flights-mcp (parado) |
| Grade ±N dias | **Calendário do fli** (só ida + ida e volta por duração) → **sweep** automático se falhar | 0,2 s por calendário; a mudança de ago/2026 não se reproduziu hoje, mas é intermitente | viajante (conferência), cheapdates `graph` (plano C com Chromium) |
| Milhas Smiles/Azul | **MCP oficial anônimo do Seats.aero** agora; **Partner API** quando houver chave | O MCP funciona sem chave a partir do Brasil (até 60 dias); o cliente da API está pronto e muda automaticamente com `SEATS_AERO_API_KEY` | MCPs comunitários: todos em TS/Go, finos, exigem chave |
| LATAM Pass | **Playwright** no site, login manual do usuário | O Seats.aero não cobre; o site exige login para milhas | — |
| Confirmação ao vivo | **Playwright** no deep link do programa | Smiles mostra milhas sem login; Azul costuma bloquear automação (best effort) | — |
| Promoções / CPM | **RSS** (PdP, PPV, cartoesdecredito.me) + MilhasBot via WebFetch | Os feeds trazem % e "último dia" no título; a leitura é barata e cacheada por 24h | Scraping de páginas sem RSS |
| Balcões | **Fora** | Grupo 123 em recuperação judicial; milhas de terceiros violam os regulamentos | — |

### Chamar MCPs por código em vez de pelo modelo
Kiwi e Seats.aero são MCPs HTTP sem sessão. `src/fontes/mcp_http.py` faz `initialize` + `tools/call` e entrega o JSON direto ao normalizador. Uma busca do Kiwi devolve ~20 KB; dezenas delas passando pelo contexto do modelo custariam caro e abririam margem para erro de transcrição. As tools continuam no `.mcp.json` para uso interativo e como fallback do subagente.

### Risco aceito: Google Flights
O ToS do Google proíbe automação contra o robots.txt, e o robots bloqueia `/travel/flights/search`. A pesquisa recomendou API licenciada (Amadeus/Duffel/SerpApi), mas a spec pede Google Flights, e o uso aqui é pessoal, de baixo volume (~20–30 chamadas por execução) e com cache de 2h. Mitigações:
- a fonte está isolada e pode ser desligada com `--fontes kiwi`;
- se ela falhar, o relatório segue com o Kiwi.

Revisitar se aparecer bloqueio ou se o uso crescer.

## Regras de cálculo (escolhas além da spec)

- **Valores por passageiro no schema.** O fli e o Kiwi devolvem o total da busca, e os adaptadores dividem pelo número de passageiros. A busca é feita com o número real de passageiros, para respeitar a disponibilidade da mesma tarifa.
- **Saldo de milhas compartilhado na combinação.** Ida e volta no mesmo programa somam as milhas antes de usar o saldo. Os pontos de cartão são um pool único para todos os programas da combinação.
- **Financiamento do que falta:** usa a fonte mais barata por milha entre compra (com mínimo e múltiplo) e transferência (bônus vigente, proporção, mínimo de transferência, limitada ao saldo de pontos). Se o mínimo de transferência tornar a transferência mais cara que comprar, compra.
- **Saldo é usado primeiro, como diz a spec,** mesmo quando `cpm_valor_uso` > `cpm_compra_atual` (hoje: Smiles 22 × 16,50). Nesse caso, usar milhas próprias "custa" mais que comprar. É o custo de oportunidade que o usuário declarou. Se preferir valorar o saldo pelo custo de reposição, ponha `cpm_valor_uso` = `cpm_compra_atual`.
- **Sem `cpm_valor_uso`, cai no `cpm_compra_atual`.** Sem nenhum dos dois, a opção não é ranqueada e vira aviso (nunca se inventa um valor).
- **Bônus de transferência com data `ate` vencida vale 0.**
- **Deduplicação entre fontes** por (tipo, programa, trecho, datas, números de voo): fica o mais barato, e um dado confirmado ao vivo vence o do cache mesmo se for mais caro.
- **Top 5 sem repetição:** combinações com mesma estratégia, cias e custo se agrupam; as outras datas aparecem como "mesmo custo também em".
- **Referência** = melhor tarifa só em dinheiro, na data exata, sem aeroporto alternativo.
- **CPM de equilíbrio:** compara com a tarifa em dinheiro do mesmo voo; se não houver, da mesma cia, rota e data; se não houver, da mesma rota e data. A base usada aparece no relatório.
- **Aeroporto alternativo:** `custo_deslocamento_brl` é cobrado por trecho e por passageiro (cada ida até o aeroporto ou volta dele).
- **Riscos sinalizados:**
  - milhas em cache;
  - preço que pode variar por clube ou categoria (fonte externa);
  - conexão abaixo de `conexao_curta_min`;
  - ida e volta em bilhetes de cias diferentes;
  - Kiwi combinando cias.

### Saldos por busca, não no perfil (2026-10-02)
Saldo de milhas e pontos muda com cada compra, transferência ou vencimento. Guardado no perfil, um valor velho distorce o ranking em silêncio. Decisão:
- o perfil guarda só dados estáveis: programas em que a pessoa tem conta, clube e categoria;
- o saldo é perguntado a cada `/passagens` e gravado em `data/runs/<id>/saldos.json`, com data e hora;
- o relatório mostra os saldos usados; sem saldo informado, avisa que milhas próprias não entraram;
- `perfil salvar` recusa um campo `saldo`.

## Fases e resultados

### Fase 0 — Pesquisa (2026-10-02)
Quatro pesquisas paralelas (ferramentas com testes reais, Seats.aero, programas, mercado e riscos), consolidadas em `docs/research.md`.

### Fases 1–2 — Esqueleto e motor
Estrutura da spec §9, configs com valores da pesquisa e motor em `src/calculo/`. Os testes cobrem dinheiro, bagagem, milhas próprias, compra parcial, mínimo de compra, transferência com bônus, bônus vencido, mínimo de transferência, misto com saldo compartilhado, aeroporto alternativo, assentos, conexão curta, CPM de equilíbrio, ranking e desempate, referência e "também possível", matriz, agrupamento e deduplicação.

### Fase 3 — Dinheiro + datas (execução real)
`GRU→REC`, 20/11 → 27/11, ±2 dias, 1 adulto:

| Coleta | Tempo | Resultado |
|---|---|---|
| Dinheiro (data exata) | 32 s | Google 115 opções, Kiwi 45 |
| Grade de datas | 6,7 s | Google 55 (calendário só ida + 9 durações), Kiwi flex 15 |

Referência: R$ 1.147,00 ida e volta (Azul) na data pedida. Matriz 5×5 completa.

### Fase 4 — Milhas (execução real)
- Seats.aero MCP anônimo: 127 resgates (Smiles + Azul, ida e volta) em 8 s.
- Melhor resultado: ida Azul 24.000 + volta Smiles 28.000 milhas, comprando tudo a R$ 21 e R$ 16,50/milheiro. Saiu R$ 1.062,29, ou R$ 84,71 abaixo da referência.
- CPM de equilíbrio: Smiles R$ 19,27 e Azul R$ 22,47, ambos acima do custo de compra. Veredito "compensa".
- Confirmação ao vivo testada no site Smiles via Playwright, sem login. O voo REC→GRU 28/11 12h45 estava disponível, com card "a partir de 27.200 milhas" contra 28.000 no cache.
- Aprendizados registrados no subagente:
  - a lista da Smiles não mostra o número do voo, então o casamento é pelo horário;
  - a taxa só aparece no detalhe da tarifa;
  - "a partir de" pode ser o preço Clube.
- **Ainda não testado:** coleta LATAM Pass (precisa do login manual do usuário), Partner API (precisa da chave) e confirmação Azul.

### Fase 5 — Promoções
`uv run passagens promos` lê 4 feeds RSS. Hoje trouxe, por exemplo:
- "Último dia! LATAM Pass oferece até 65% de desconto";
- "Azul … 100% de bônus … Alloyal".

O `/atualizar-milheiro` mostra o diff e só grava com confirmação.

### Fase 6 — Robustez
- Cache com TTL por fonte: dinheiro 2h, milhas 6h, promoções 24h.
- Contadores diários e por execução: Seats API 1.000, Seats MCP 300, Playwright 15 páginas.
- Histórico CSV com comparação "subiu/desceu".
- **Degradação testada:**
  - teste automatizado: grade do Google quebrada cai para sweep, e Kiwi fora fica registrado como falha;
  - execução real com Google desligado (`GRU→SSA`): o relatório saiu só com o Kiwi e avisou "google_flights indisponível".

### Fase 7 — Documentação
README (instalação, uso, cálculo, limitações, como trocar uma fonte) e CLAUDE.md (regras para o agente).

## Pendências que dependem do usuário
1. **Perfil real:** responder à entrevista do `/configurar-perfil` (o `/passagens` a dispara sozinho na primeira vez). O perfil está como "não configurado"; o exemplo acima rodou com saldos zerados, por isso "compra todas as milhas".
2. **Chave do Seats.aero** (`SEATS_AERO_API_KEY`), para voos a mais de 60 dias. Confirmar se a aba API aparece para uma conta brasileira.
3. **Login manual na LATAM** na janela do Playwright (perfil `./browser-profile`), para habilitar LATAM Pass.

## Distribuição como plugin (2026-10-02)
- **Sem hospedagem.** Cada pessoa roda tudo no próprio computador, no Claude Desktop (aba Code) ou no Claude Code, com as próprias chaves.
- **Formato:** plugin do Claude Code, com o marketplace no mesmo repositório:
  - instalação: `/plugin marketplace add <dono/repo>` + `/plugin install passagens@passagens-marketplace`;
  - comandos viraram skills: `/passagens:buscar`, `:perfil`, `:milheiro`, `:configurar`.
- **Instaladores de um comando** (`scripts/instalar.sh`, `scripts/instalar.ps1`): usam os instaladores oficiais (uv da Astral; Node via Homebrew/winget ou link do nodejs.org) e perguntam antes de cada item.
- **`/passagens:configurar`** roda `passagens diagnostico` e ensina a resolver cada pendência, com comando e link por sistema. Testado em modo headless: o caminho do plugin foi substituído e o diagnóstico rodou.
- **Dados fora do plugin** (`~/.agente-passagens`), porque a pasta do plugin é substituída a cada atualização. Não usamos `${CLAUDE_PLUGIN_DATA}` para os dados do Python porque ele não existe como variável no Bash; ele é usado só no `.mcp.json`, para o perfil do navegador.
- **Chaves de API** são gravadas pelo próprio usuário no terminal (`passagens chave seats`, entrada oculta), para não ficarem no histórico da conversa. Descartamos `userConfig` sensível porque o valor seria injetado no texto da skill, ou seja, no contexto do modelo.

## Nome internacional e multi-idioma (2026-10-02)
- **Nome:** o plugin passou a se chamar **farehunter** (antes "passagens"), para fazer sentido em qualquer idioma.
  - Skills: `/farehunter:search`, `:profile`, `:miles`, `:setup`.
  - Subagentes: `farehunter:cash-researcher`, `dates-researcher`, `miles-researcher`, `promos-researcher`.
  - CLI: `farehunter`. Pasta de dados: `~/.farehunter`.
  - Repositório previsto: `s0beran0/farehunter`.
- **Skills e agentes em inglês**, com a regra de conversar no idioma do usuário. As descrições incluem palavras em pt e es ("passagens", "pasajes", "milhas", "millas"), para a skill ser acionada mesmo sem o comando com barra.
- **Relatório e textos do motor em pt/en/es**, num catálogo em `src/i18n/mensagens.py`:
  - números e datas formatados por idioma (R$1,147.00 / R$ 1.147,00; "Nov 20 (Fri)" / "20/11 (vie)");
  - outro idioma cai em `en`, e o modelo traduz o relatório sem tocar em números;
  - um teste exige que todos os idiomas tenham as mesmas chaves.
- **Instaladores com mensagens em pt/en/es**, conforme o idioma do sistema (ou `FAREHUNTER_LANG`).
- **O que continua em português:** código interno, chaves do JSON e os dados de domínio (programas brasileiros, BRL). Multi-idioma não significa multi-país: as fontes e os programas continuam os do Brasil.

## Internacionalização de verdade (2026-10-02)
- **Moeda da busca:** cada busca usa uma moeda só (`moeda` do perfil ou `--moeda`), e todo valor é convertido para ela.
  - O motor ficou neutro em moeda: os campos `*_brl` viraram `preco`, `taxas`, `custo` etc.
  - O Google Flights e o Kiwi já buscam na moeda e no país do usuário (`pais` define o ponto de venda).
- **Câmbio sem chave:** Frankfurter (BCE), com open.er-api.com como fallback para ARS, CLP, COP etc. Cache de 24h.
  - As taxas de resgate (USD, GBP, EUR…) são convertidas.
  - Os CPMs do milheiro são convertidos da moeda de cada programa para a moeda da busca.
  - Se não houver cotação, o valor fica de fora e o relatório avisa.
- **Registro de programas** (`config/programas.yaml`, parte do plugin): 30 programas de milhas e 14 de pontos.
  - O registro guarda nome, cias, fonte no Seats.aero, link e as transferências (proporção e mínimo).
  - Isso substitui as listas fixas de Smiles/LATAM/Azul espalhadas pelo código.
  - Adicionar um programa é editar um YAML.
- **Milheiro mesclado:** a tabela do usuário (`~/.farehunter/config/milheiro.yaml`) vence programa a programa. Programas que só existem na tabela do plugin entram sozinhos, então uma atualização do plugin traz programas novos sem apagar os valores do usuário.
- **Valores internacionais:**
  - **Uso:** mediana de TPG, Upgraded Points, Frequent Miler e NerdWallet, em USD por 1.000.
  - **Compra:** preço promocional recorrente, com data de fim quando houver. Programas sem preço publicado ficam vazios, sem chute.
  - Fontes em `docs/research.md` §10.
- **Programas consultados no Seats.aero:**
  - os do perfil (`tem_conta`) mais os parceiros de transferência dos pontos do usuário;
  - sem nenhum dos dois, todos os programas, sem filtro.
- **Promoções por região do país:** Brasil, EUA, Reino Unido, Austrália e Canadá; os demais países usam os blogs dos EUA. Os feeds são lidos com User-Agent honesto de leitor RSS (todos responderam 200). Além dos feeds, há páginas que listam os bônus de transferência ativos.
- **Links:**
  - Smiles, LATAM e Azul abrem a busca já com rota e data.
  - Os outros programas abrem a página de resgates oficial; algumas URLs só tiveram o domínio confirmado, porque os sites bloqueiam scripts.
- **Comentários e docstrings em inglês** (pedido do usuário). Os identificadores continuam em português.

## Descoberta de hubs com voo real (2026-10-02)
- **Lista de aeroportos do país:** vem do `search_airports` do Seats.aero (MCP anônimo), ordenada por voos semanais, e funciona para qualquer país. O `config/hubs.yaml` fica só como fallback sem internet.
- **Teste de voo direto:** uma busca no Kiwi por aeroporto com `max_sector_stopovers=0`, 4 em paralelo. BSB→MIA levou 9 s para 14 aeroportos e achou GRU e GIG com voo direto, com 56 voos válidos já com preço. Aeroportos sem serviço não recebem nenhuma busca, o que também poupa o Google, que estava dando 429.
- **Lacunas do Kiwi:** ele não vende todas as cias (ex.: LATAM). Por isso o `list_routes(origem, destino)` do Seats.aero mantém como candidato o aeroporto com rota de resgate rastreada, marcado como "pode ter conexão".
- **Cache:** aeroportos ficam em cache por 30 dias e rotas por 7 dias.

## Economia de tokens e Google mínimo (2026-10-02)
- **Medição antes da mudança** (busca JFK→LHR):
  - o orquestrador fez 24 turnos e leu ~1,1 milhão de tokens de contexto, cerca de 46 mil por turno;
  - os 3 subagentes de coleta leram ~210 mil.
  - O custo vinha do vaivém do orquestrador, não do tamanho das instruções.
- **`farehunter recomendar`:** um comando faz a busca toda. Ele coleta em paralelo (dinheiro, datas, milhas e hubs quando o destino é em outro país), roda o ciclo de validação (pendências → detalhes) e a análise final, e devolve um JSON curto.
  - Os subagentes de coleta (cash e dates researcher) foram removidos.
  - O de milhas fica só para confirmar no navegador o que `precisam_navegador` listar.
- **Skill de busca:** de 8,9 KB para ~2,8 KB. As descrições sempre carregadas caíram para ~230 caracteres cada.
- **Google:** orçamento de 12 chamadas reais por busca (cache não conta; chamada barrada pela pausa também não).
  - Chamadas serializadas, com 2 s de intervalo.
  - Pausa de 30 min após HTTP 429.
  - Os trechos de posicionamento usam só o Kiwi.
  - Quando o Google está fora, os detalhes da data também vêm do Kiwi.
  - Menos calendários ida e volta: só durações dentro de ±flex.
- **Não automatizamos o "não sou um robô" do Google** nem tentamos driblar anti-bot. O extrator da Smiles em Python/Playwright foi testado e descartado: um Chromium limpo, com ou sem janela, fica parado no "Aguarde enquanto buscamos". A confirmação continua com o subagente de navegador, que usa o Chrome real do usuário.

## Dicas de quando comprar (2026-10-02)
- **Base:** `config/dicas.yaml`, montada com ~45 fontes datadas (`docs/research.md` §11). Não faz nenhuma chamada ao Google.
- **Antecedência:** cada busca recebe uma classificação conforme a antecedência e o tipo de viagem (doméstica Brasil / doméstica / Américas / intercontinental): cedo, um pouco cedo, boa hora, fim da faixa ou tarde.
- **Promoções:** o plugin lista as promoções do país do usuário que caem antes do último bom momento de compra. Avisa quando elas costumam trazer bônus de milhas.
- **Temporada e dia de voo:** marca alta temporada no destino e lembra que o dia de voar pesa mais que o dia de comprar.
- **Fora da análise:** as dicas nunca mudam o ranking. Qualquer erro nelas é ignorado, para não quebrar a busca.
