# Pesquisa da fase 0 — passagens e milhas no Brasil

**Data da pesquisa:** 2026-10-02 (sexta). Testes rodados desta máquina, com IP brasileiro.
Rota de teste: GRU→REC (também GRU→SSA, CGH→SDU, CGH→REC, GRU→LIS), 1 adulto, econômica.

Marcadores: **[TESTADO]** rodado hoje · **[OFICIAL]** site/regulamento oficial · **[BLOG]** artigo 2026 · **[INCERTO]** não confirmado.

---

## Tabela de status das ferramentas

| Ferramenta | Status testado hoje | Evidência | Decisão |
|---|---|---|---|
| **Kiwi MCP** `https://mcp.kiwi.com` | ✅ funciona | Handshake + `tools/list` + 3 buscas OK (2–9 s). BRL funciona. 15 itinerários por busca. Mais barato GRU→REC 10/12: R$ 720–767 (Google achou R$ 618) | **Fonte secundária de dinheiro.** Chamado direto por JSON-RPC (`src/fontes/kiwi.py`) e também em `.mcp.json` |
| **fli** (PyPI `flights==0.9.0`) | ✅ funciona | Data específica: 127–129 resultados, mín. R$ 618, 1,5 s. Calendário: 31/61 dias em BRL, 0,2 s | **Fonte primária de dinheiro e da grade de datas.** Versão fixada |
| fli git main `881aee5` (página `/travel/flights?tfs=`) | ✅ funciona | 18 resultados, mín. R$ 618. Calendário 31 dias em 3,3 s | Plano B (mesma API Python), se a 0.9.0 parar |
| viajante 1.3.1 | ✅ funciona | `search_dates` 20/20 dias, mesmos preços do fli; `get_flights` 43 resultados | Alternativa/conferência; muda rápido demais para ser o núcleo |
| cheapdates (git `916f375`, backend `graph`) | ✅ funciona | Chromium headless, 31/31 dias em 6 s, mesmos preços | Plano C para o calendário se a chamada direta morrer |
| fast-flights 3.1.0 | ⚠️ parcial | Só data específica, 15 resultados, perdeu tarifas LATAM de R$ 618/860; sem calendário | Não usar |
| google-flights-mcp 0.1.0 | não testado | Última versão 2025-09-16, antes da mudança de ago/2026 | Não usar |
| Atores Apify | não testado | Sem `APIFY_TOKEN`; US$ 0,03–2 por 1k resultados | Só como fallback pago |
| **Seats.aero MCP oficial** `https://seats.aero/mcp` | ✅ funciona **sem chave** | Smiles CGH→REC 19.400 milhas + R$ 62,14; Azul GRU→REC 18.000 + R$ 35,75. Limite anônimo: voos em até 60 dias, 50 resultados/chamada, 1.000 req/IP/dia | **Fonte de milhas Smiles/Azul enquanto não houver chave** (`src/fontes/seats.py`) |
| **Seats.aero Partner API** | não testado com chave (sem chave) | Sem chave: `401 missing_partner_key` (não é geobloqueio). Campos conferidos na doc e em fixtures reais | **Cliente próprio pronto** (`src/mcp_seats/cliente.py`); ativa com `SEATS_AERO_API_KEY` |
| **Playwright MCP** `@playwright/mcp` 0.0.83 | ✅ flags conferidas (`--help`); custo medido com Playwright Python | Página do Google Flights: snapshot ARIA ~24 KB (~6k tokens); `evaluate` de 20 linhas ~2,5 KB (~620 tokens); HTML 2,9 MB | **Só confirmação de finalistas e LATAM Pass.** `--snapshot-mode none --image-responses omit`, perfil persistente |
| Site Smiles (deep link) | ✅ funciona sem login | Mostra preço Clube/Diamante e normal | Link de emissão + confirmação ao vivo |
| Site LATAM (milhas) | ⚠️ exige login | `redemption=true` redireciona para login | Playwright com login **manual** do usuário |
| Site Azul (pontos) | ⚠️ não carregou em navegador automatizado | Parâmetros conferidos no código do site; resultados não carregaram (provável bloqueio) | Só link para o usuário; confirmação "quando possível" |
| Balcões (123milhas/MaxMilhas/HotMilhas) | não integrado | Grupo em recuperação judicial | **Fora do MVP** (§7) |

**Sobre o BotGuard no Google:** a mudança de ago/2026 está documentada ([fli #223](https://github.com/punitarani/fli/issues/223), [PR #230](https://github.com/punitarani/fli/pull/230), [cheapdates graph.py](https://github.com/afgoes/cheapdates)), mas **não se reproduziu hoje**. Um POST simples ao `GetCalendarGraph` sem o cabeçalho `x-goog-batchexecute-bgr` devolveu a grade completa em BRL em 4 rotas. O próprio teste diário do fli falhou em 2026-09-21 e voltou em 2026-09-22 ([fli #258](https://github.com/punitarani/fli/issues/258)): é frágil e intermitente. Por isso a coleta tem fallback automático: calendário → **sweep** (uma busca por data) → fonte indisponível.

---

## 1. Kiwi.com MCP

- **Transporte:** Streamable HTTP. POST JSON-RPC com `Accept: application/json, text/event-stream` e `MCP-Protocol-Version: 2025-06-18`. A resposta vem em SSE. Não exige sessão (não devolve `Mcp-Session-Id`). Nome do servidor: `kiwicom-flight-search`.
- **Tools:** `search-flight` (e `feedback-to-devs`).
- **Parâmetros do `search-flight`:**
  - Obrigatórios: `flyFrom`, `flyTo`, `departureDate` (dd/mm/yyyy). Aceita IATA ou nome de cidade.
  - Datas: `departureDateFlexDays` (±0–10), `departureDateTo`, `returnDate`, `returnDateFlexDays`, `returnDateTo`, `nights_in_dst_from/to`.
  - Passageiros: `adults`, `children`, `infants`.
  - Cabine: `cabinClass` (M = econômica, W = premium, C = executiva, F = primeira).
  - Moeda e idioma: `currency` (BRL funciona), `locale`.
  - Bagagem: `adults_hold_bags`, `adults_hand_bags` (lista, um item por passageiro).
  - Filtros: escalas, preço, cias, horários, conexões, `allow_self_transfer`, `sort`.
- **Limitações:** sem multi-city; sem parâmetro de quantidade (sempre 15 itinerários). O Kiwi combina cias diferentes (self-transfer).
- **Saída:**
  - Por itinerário: `price` (total da busca), `bookingUrl`, `baggage{personalItem,cabinBag,checkedBag}`.
  - `outbound`/`inbound`, com `segments[]` (`carrier`, `flightNumber` como `LA3676`, horários locais).
- **ToS:** T&C de 11/08/26 não falam de scraping; robots.txt bloqueia `/<país>/search`; a API Tequila está fechada para novos cadastros desde mai/2024. O MCP é um canal oficial da Kiwi.

## 2. Google Flights (fli)

- `SearchFlights().search(filtros, currency="BRL", language="pt-BR", country="BR")` devolve `FlightResult` com:
  - `price`, que é o **total para todos os passageiros**: 2 adultos = 2× quando há assento na mesma tarifa (testado: R$ 1.236 para 2 × R$ 618);
  - `duration`, `stops`;
  - `legs[]`, com `airline.name` = código IATA e `flight_number` sem prefixo;
  - horários `departure_datetime` e `arrival_datetime`.
- Ida e volta: `TripType.ROUND_TRIP` com 2 segmentos e `top_n`. Devolve tuplas `(ida, volta)`, e `ida.price` já é o total ida+volta.
- Calendário: `SearchDates().search(DateSearchFilters(...))` devolve `DatePrice(date=tuple, price)`.
  - Ida e volta exige `duration` (noites).
  - Janelas acima de 61 dias são divididas automaticamente; o limite é 305 dias à frente.
- **ToS:** o ToS do Google (30/07/26) proíbe acesso automatizado que viole o robots.txt, e o robots bloqueia `/travel/flights/search`. Não há API oficial. Uso aqui: pessoal, baixo volume, cache de 2h. O risco está registrado em `docs/decisoes.md`.

## 3. Seats.aero

**Plano e termos** ([terms](https://seats.aero/terms), atualizados em 2026-08-12):
- Pro custa US$ 9,99/mês ou US$ 99,99/ano.
- A API vem incluída para usuários Pro "elegíveis": até 1.000 chamadas/dia, com reset à meia-noite UTC e cabeçalho `X-RateLimit-Remaining` ([getting-started](https://developers.seats.aero/reference/getting-started-p), [KB 68](https://docs.seats.aero/article/68-seatsaero-pro-api-access-limits-and-usage)).
- Uso pessoal e não comercial; exige crédito visível "seats.aero".
- **Live Search não está disponível para Pro.**

**Disponibilidade no Brasil:**
- A documentação diz que a API "não está disponível em todos os países", mas **não publica a lista**.
- Daqui, a Partner API responde "missing key", e não geobloqueio.
- **[INCERTO]** Não dá para saber se uma conta Pro brasileira recebe a aba de API. Para tirar a dúvida, assine um mês ou escreva para support@seats.aero.

**Endpoints** (base `https://seats.aero/partnerapi/`, cabeçalho `Partner-Authorization: <chave>`, sem "Bearer"):
- **`GET /search`**
  - Parâmetros: `origin_airport`, `destination_airport` (listas), `start_date`, `end_date`, `cursor`, `take` (10–1000), `skip`, `order_by`, `include_trips`, `only_direct_flights`, `carriers`, `sources`, `cabins`.
  - Resposta: `{data[], count, hasMore, cursor}`.
  - Disponibilidade: `ID`, `Date`, `Source`, `UpdatedAt`, `Route{OriginAirport, DestinationAirport, ...}`.
  - Campos por cabine (Y/W/J/F): `YAvailable`, `YMileageCost` (string) e `YMileageCostRaw` (int), `YTotalTaxes` (centavos), `YRemainingSeats`, `YAirlines`, `YDirect`, além de `TaxesCurrency`.
- **`GET /trips/{id}`**
  - `MileageCost`, `TotalTaxes` (centavos), `FlightNumbers`, `DepartsAt`/`ArrivesAt`.
  - Os horários são **locais do aeroporto, apesar do sufixo Z**.
  - Também traz `Stops`, `Carriers`, `RemainingSeats` e `booking_links`.
- **`GET /availability`** (bulk por programa e região), **`GET /routes?source=`**, **`POST /refresh`** (Pro; 1 chamada por item; dado com mais de 3h é considerado velho).
- Paginação: usar o `cursor` da primeira resposta, `skip` = número de itens já recebidos, enquanto `hasMore`; deduplicar por `ID`.

**Programas:**
- `smiles`: tem contagem de assentos; taxa em BRL.
- `azul`: **sem** contagem de assentos; taxa em BRL.
- **LATAM Pass NÃO é coberto** ([KB 80](https://docs.seats.aero/article/80-does-seats-aero-support-latam-or-latam-pass-awards)). Voos LATAM aparecem via `delta`, `virginatlantic` e `livelo` (`carriers=LA`).
- Idade do cache observada hoje: Smiles de 44 min a 2,9 dias; Azul 4–5 dias.

**MCP oficial anônimo** (`https://seats.aero/mcp`):
- Tools: `get_flights`, `get_flight_details`, `list_routes`, `search_airports` etc.
- `get_flights` aceita `origins`, `destinations`, `start_date`, `end_date`, `programs`, `cabin`, `max_stops` (padrão 0 = só direto), `max_results` ≤ 50, `min_seats`, `sort`.
- Devolve `structuredContent.flights[]` com `miles_price`, `taxes` ("R$62.14 BRL"), `minutes_old`, `remaining_seats`, `flights` ("G31612"), além de `truncated_by`.

**MCPs comunitários** (todos exigem chave da Partner API):

| Servidor | Linguagem | Última atualização | Observação |
|---|---|---|---|
| [gavgrego/seats.aero-mcp-server](https://github.com/gavgrego/seats.aero-mcp-server) | TS | 2026-08-10 | Repasse simples |
| [olsonbd/seats-aero-mcp](https://github.com/olsonbd/seats-aero-mcp) | TS | 2026-09-15 | Melhor tratamento de cota |
| seats-aero-pp-mcp ([printing-press-library](https://github.com/mvanhorn/printing-press-library/tree/main/library/travel/seats-aero)) | Go | 2026-09-11 | Pesado (SQLite) |
| skybluu | Python | 2025-12 | Parado |

**Decisão:** cliente próprio mínimo em Python (httpx). Nenhum dos MCPs mantidos é Python, e o tratamento específico de Brasil é necessário de qualquer forma (taxa em centavos, hora local com Z, Azul sem assentos, idade do cache). Referência Python: [ak2k/flight-cli](https://github.com/ak2k/flight-cli/tree/main/src/flight_cli/providers/seats_aero) (MIT).

## 4. Playwright MCP

- **Versão:** 0.0.83 (npm, 2026-09-28). Por padrão roda com janela (headed); para rodar sem janela, `--headless`.
- **Perfil persistente:**
  - padrão em `~/Library/Caches/ms-playwright/mcp-{canal}-{hash}`;
  - `--user-data-dir <dir>` aponta para outro diretório;
  - `--isolated` roda em memória;
  - também há `--storage-state <arquivo>` e `--save-session`.
- **Para gastar menos tokens:**
  - `--snapshot-mode none`, porque por padrão cada clique ou navegação devolve o snapshot completo;
  - `browser_evaluate` para extrair só os campos necessários;
  - ler o JSON da própria página com `browser_network_requests`/`browser_network_request`;
  - `--image-responses omit`, `--output-dir`;
  - `--caps` mínimo.
- **Config do projeto:** `--user-data-dir ./browser-profile --snapshot-mode none --image-responses omit` (headed, para o usuário poder fazer login manual na LATAM).

## 5. Programas de fidelidade

### 5.1 Busca de resgate e deep links (testados em navegador)

**Smiles: mostra milhas sem login [TESTADO].**
- O resultado traz o preço Clube/Diamante e o normal (ex.: POA→GRU 15/11: 55.900 vs. 60.700).
- Link:
  ```
  https://www.smiles.com.br/mfe/emissao-passagem/?adults=1&children=0&infants=0&cabin=ALL&tripType=2&searchType=both&segments=1&isElegible=false&isFlexibleDateChecked=false&originAirport=POA&originAirportIsAny=false&destinationAirport=GRU&destinAirportIsAny=false&departureDate=1794744000000&returnDate=
  ```
- Datas em epoch ms (usar 12:00 UTC). `tripType`: 1 = ida e volta, 2 = só ida.
- Os nomes `originAirportCode`/`destinationAirportCode` são ignorados pelo site.
- O site está atrás de proteção anti-bot. O link serve para o usuário; não chamar a API interna.

**LATAM: milhas exigem login [TESTADO].**
- Link:
  ```
  https://www.latamairlines.com/br/pt/oferta-voos?origin=POA&destination=GRU&outbound=2026-11-15T12%3A00%3A00.000Z&inbound=null&adt=1&chd=0&inf=0&trip=OW&cabin=Economy&redemption=true&sort=RECOMMENDED
  ```
- `redemption=false` mostra preço em dinheiro sem login. Ida e volta: `trip=RT&inbound=<ISO>`.

**Azul: parâmetros conferidos, resultados não carregaram no navegador automatizado [INCERTO].**
- Link:
  ```
  https://www.voeazul.com.br/br/pt/home/selecao-voo?c[0].ds=POA&c[0].std=11/15/2026&c[0].as=GRU&p[0].t=ADT&p[0].c=1&p[0].cp=false&f.dl=3&f.dr=3&cc=PTS
  ```
- Datas em MM/dd/yyyy; `cc=PTS` = pontos, `cc=BRL` = dinheiro. A emissão com pontos exige login ([BLOG] PdP 2026).

### 5.2 Descontos por clube/status

- **Clube Smiles / Diamante:** preço separado ~8% menor, visto em 10 de 10 voos da amostra [TESTADO].
  - Teto para Diamante em voo GOL doméstico: 35.000 milhas por trecho, 15 voos em 12 meses.
  - Teto para Ouro: 50.000 milhas, 5 voos.
  - Antecedência mínima de 7 dias [OFICIAL].
- **Clube LATAM Pass:** não achei desconto permanente em resgate [INCERTO].
- **Clube Azul:** cupons de 10–20% em resgate doméstico conforme o plano; o titular precisa voar [BLOG].
- **Categorias Azul desde 14/01/2026:** Topázio, Safira, Diamante, Diamante Unique [BLOG].

**Efeito no agente:** o Seats.aero não reflete o desconto do usuário. Quando o perfil tem clube ou categoria, o relatório sinaliza a possível diferença, e a confirmação ao vivo usa o preço do perfil.

### 5.3 Emissão para terceiros

| Programa | Limite |
|---|---|
| Smiles | Titular + 25 pessoas por ano civil (regulamento 13.3.1) [OFICIAL] |
| LATAM Pass | Titular + 24 por 12 meses móveis [BLOG; contagem por bilhete INCERTO] |
| Azul | Lista cadastrada por categoria: 5 a 15 pessoas; 30 dias de carência [BLOG] |

### 5.4 Taxas em resgates

- **Smiles:** taxa de embarque em dinheiro ou milhas. Segurar reserva GOL custa R$ 50 [OFICIAL].
- **LATAM:** sem taxa de resgate desde 19/12/2022 [OFICIAL].
- **Azul:** R$ 69,90 por bilhete quando emitido com menos de 120 dias de antecedência e o titular não viaja (doméstico) [BLOG MD, em vigor desde 18/06/26].

### 5.5 Cancelamento e reembolso

- **Smiles:**
  - Cancelamento grátis em 24h se emitido com 7 dias ou mais de antecedência.
  - Depois disso, reembolso doméstico GOL de ~R$ 400 [BLOG; outras fontes citam 190 e 450, INCERTO].
  - Alteração: R$ 450 doméstico [OFICIAL].
- **LATAM doméstico:** alteração R$ 225, reembolso R$ 250 [OFICIAL].
- **Azul:** reembolso R$ 550 por trecho doméstico; 24h grátis se comprado com 7 dias ou mais [BLOG CeV 13/09/26].

### 5.6 Compra de milhas e transferências

| Programa | Preço cheio / 1.000 | Limites |
|---|---|---|
| Smiles | R$ 80 | Mín. 1.000 por compra, máx. 300.000/ano [OFICIAL] |
| LATAM | R$ 70 (R$ 49 com cartão Itaú LATAM ou Clube) | 1.000 a 999.000 em 12 meses, lotes de 1.000 [OFICIAL] |
| Azul | R$ 70 (base para promoção) | Mínimo não encontrado [INCERTO] |

| De → para (1:1) | Smiles | LATAM | Azul |
|---|---|---|---|
| Livelo | mín. 10.000 | mín. 12.000 | mín. 1.000 |
| Esfera | mín. 30.000 | mín. 30.000 | mín. 30.000 |
| Inter Loop | só Prime/Win/Black | não disponível | todos |
| C6 Átomos | mín. 1.000 | mín. 100 | mín. 100 |

Fontes: blogs de set/2026. A Nubank passou a transferir para a Livelo 1:1 em 29/09/2026.

## 6. Custo do milheiro (CPM)

**Como o mercado calcula:**
- **Custo de compra:** R$ pagos ÷ milhas × 1000.
  - Compra direta: `preço_base × (1 − desconto) ÷ (1 + bônus)`. Exemplo: Smiles com 380% de bônus = R$ 16,67 ([PdP 16/09/26](https://passageirodeprimeira.com/smiles-oferece-ate-380-de-bonus-na-compra-de-milhas/)).
  - Transferência: `CPM_pontos × paridade ÷ (1 + bônus)`. Exemplo: Livelo a R$ 29,50 com 100% = R$ 14,75 ([MD](https://www.melhoresdestinos.com.br/milhas/valor-milheiro-livelo)).
- **Valor de uso:** (tarifa em dinheiro − taxas) ÷ milhas × 1000. É o "CPM de equilíbrio" do relatório ([MilhasBot](https://www.milhasbot.com.br/valores-do-milheiro/), [PdP 17/07/26](https://passageirodeprimeira.com/quanto-vale-uma-milha-quanto-vale-um-ponto-minha-visao/)).

**Referências atuais (R$ / 1.000):**

| Programa | Valor-alvo MD (30/07/26) | Teto de compra MilhasBot (02/10/26) | Valor de uso MilhasBot (02/10/26) |
|---|---|---|---|
| Smiles | 16 | 14–16,50 | 22 |
| LATAM Pass | 26 | 20–24,50 | 28 |
| Azul | 13 | 13–15,75 | 17 |
| Livelo | 30 | 27–30,50 | 23 |
| Esfera | — | — | 22 |

- **Régua de compra Livelo/Esfera:** até R$ 33 é bom, até 30 excelente, até 27 imperdível ([Viaja na Milha 25/05/26](https://viajanamilha.com.br/mapa-da-milha/dicas-do-especialista/livelo-vs-esfera-qual-escolher-como-se-cadastrar-guia-2026)).
- **Mínimos de 2026:**
  - Smiles: Clube R$ 10,80, pontos + dinheiro R$ 14,6–15,5.
  - LATAM: R$ 23,5–24,5.
  - Azul: R$ 9,50–12,76 via clube ou transferência.

**Onde buscar o valor atualizado (em ordem):**
1. RSS (usado por `uv run passagens promos`):
   - `passageirodeprimeira.com/categorias/promocoes/transferencia-de-pontos/feed/`
   - `passageirodeprimeira.com/categorias/promocoes/compra-de-pontos/feed/`
   - `pontospravoar.com/category/promocoes/feed/`
   - `cartoesdecredito.me/feed/`
2. `milhasbot.com.br/valores-do-milheiro/`: atualizada todo mês; separa uso, compra e venda.
3. Páginas de valor-alvo do Melhores Destinos (`/milhas/valor-milheiro-azul-latam-smiles-2026`, `/milhas/valor-milheiro-livelo`).
4. Cartões e Viagens: sem RSS funcionando; acessar via busca.

**Frequência das promoções:**
- **Smiles, bônus de transferência:** 36 campanhas entre jan/24 e ago/26, uma a cada 3–6 semanas. O normal é 80% (60–100%); quem não tem clube ganha 30–50%. 100% é raro ([tabela do PPV, 30/09/26](https://pontospravoar.com/prorrogado-smiles-oferece-ate-70-porcento-bonus-transferencia-pontos-todos-parceiros/)).
- **Azul:** até 110% várias vezes por mês.
- **LATAM:** quase sempre 25%.
- **Compra direta:** Smiles 300–380% de bônus (Clube) quase todo mês; LATAM 62–65% OFF quase todo mês; Livelo 53–58% OFF; Esfera 45–55% OFF.

**Ativas em 02/10/2026:**
- LATAM 65% OFF na compra (termina hoje).
- Azul até 100% de bônus vindo do Inter Loop e da Alloyal (terminam hoje).
- Livelo → Etihad 40%.
- **Nenhum bônus Livelo/Esfera → Smiles ativo**: o último, de 70%, foi até 30/09.

## 7. Balcões de milhas

- **Situação:** 123milhas, MaxMilhas e HotMilhas pertencem ao Grupo 123, em recuperação judicial desde ago/2023. A dívida é de ~R$ 2,3 bi.
- **Plano:** pagamento em 6,5–8 anos com mais de 70% de desconto ([Panrotas 02/26](https://www.panrotas.com.br/agencias-de-viagens/mercado/2026/02/123-milhas-propoe-acordo-para-credores-com-pagamentos-em-quase-8-anos_225827.html), [O Tempo 30/03/26](https://www.otempo.com.br/economia/2026/3/30/123milhas-oferece-dividir-pagamento-a-credores-por-ate-6-5-anos-confira-condicoes-oferecidas)). Assembleia prevista para o 2º semestre [INCERTO].
- **Operação:** continuam vendendo ([Mobills 08/04/26](https://www.mobills.com.br/blog/milhas/maxmilhas-e-confiavel/)), com reclamações de atraso no pagamento a quem vende milhas.
- **Decisão:** **fora do MVP.**
  - Comprar de balcão significa voar com milhas de terceiros, o que os programas proíbem; o bilhete pode ser cancelado.
  - A empresa está em recuperação judicial.
  - O preço de venda (Smiles ~R$ 13, LATAM ~R$ 21 [INCERTO]) no máximo serve como piso informativo do valor da milha.

## 8. Tarifas e bagagem (doméstico)

| Cia | Famílias | Inclui mala de 23 kg | 1ª mala avulsa |
|---|---|---|---|
| GOL | Light / Classic / Flex | Classic, Flex | ~R$ 130 online, R$ 165 em 48h, R$ 180 no aeroporto [BLOG 04/26] |
| LATAM | Light / Standard / Full | Standard, Full [OFICIAL] | ~R$ 140 online, R$ 170–175 perto do voo, R$ 200 no aeroporto [BLOG] |
| Azul | Azul / Mais Azul | Mais Azul | R$ 175–220 online, R$ 220–250 em 48h, R$ 250 no aeroporto [BLOG 08/26] |

Resgates econômicos Smiles em voos GOL e resgates domésticos LATAM **não** incluem mala. A Smiles oferece a "Tarifa Turbinada", que soma mala e assento por ~+5.500 milhas.

## 9. Termos de uso e riscos

**Smiles** ([regulamento 17/06](https://www.smiles.com.br/regulamento-do-programa-smiles-1706)):
- A cláusula 5.3 permite exclusão ou suspensão por:
  - (a) negociar milhas com terceiros;
  - (d) uso "irregular, inadequado ou suspeito";
  - (g) fornecer número ou senha a terceiros.
- Pela 5.3.1, a suspensão pode vir só com suspeita. Pela 5.4, há estorno de milhas e cancelamento de prêmios.
- Não há cláusula explícita sobre robôs, mas o site usa reCAPTCHA e a 5.3(d) é ampla. Houve suspensões em massa em 2022.

**LATAM Pass:**
- A página de termos devolveu 403 para acesso automatizado.
- Pelos resultados de busca: milhas pessoais e intransferíveis; o mau uso leva a confisco e exclusão. Regulamentos de campanha anulam compras feitas por meios "robóticos, repetitivos, automáticos".

**Azul:**
- O regulamento não abriu.
- Pelos resultados de busca: suspensão por negociar pontos ou compartilhar a senha [INCERTO na cláusula exata].

**Google / Kiwi:** ver §1 e §2.

**Regras adotadas** (refletidas no CLAUDE.md e nos subagentes):
1. Nunca guardar ou usar credenciais; o saldo é informado pelo usuário.
2. Nada de compra, transferência, emissão ou venda automática.
3. Sem balcões.
4. Navegador só para leitura, no máximo 15 páginas por execução, sem paralelismo, 5 s entre páginas. Login só manual, num perfil persistente. Se aparecer 403 ou CAPTCHA, parar; sem proxies.
5. Promoções lidas no máximo 1×/dia (cache de 24h).
6. Cada número com fonte e data.

---

## 10. International data (research 2026-10-02)

Seed values for the international programs in `config/programas.yaml` and `config/milheiro.yaml`.

### 10.1 Value per point (US cents)
**Sources:**
- **TPG:** [The Points Guy monthly valuations](https://thepointsguy.com/loyalty-programs/monthly-valuations/), October 2026 (published 2026-10-01).
- **UP:** [Upgraded Points](https://upgradedpoints.com/travel/points-and-miles-valuations/), September 2026 (2026-09-17).
- **FM:** [Frequent Miler reasonable redemption values](https://frequentmiler.com/reasonable-redemption-values-rrvs/), 2026-09-02.
- **NW:** [NerdWallet](https://www.nerdwallet.com/article/travel/airline-miles-and-hotel-points-valuations), 2026-10-02.

**`cpm_valor_uso`** = the **median** of the available sources × 10, giving USD per 1,000. The median is more robust than any single blog. When there is only one source, the value is marked as uncertain.

| id | TPG | UP | FM | NW | median → USD/1,000 |
|---|---|---|---|---|---|
| united | 1.2 | 1.2 | 1.3 | 1.2 | 12.00 |
| american | 1.45 | 1.4 | 1.4 | 1.7 | 14.25 |
| delta | 1.2 | 1.2 | 1.1 | 1.2 | 12.00 |
| alaska | 1.55 | 1.6 | 1.5 | 1.4 | 15.25 |
| aeroplan | 1.5 | 1.5 | 1.4 | 1.1 | 14.50 |
| flyingblue | 1.4 | 1.3 | 1.3 | 1.0 | 13.00 |
| british | 1.4 | 1.25 | 1.1 | 1.2 | 12.25 |
| iberia / qatar | 1.4 | 1.25 | – | – | 13.25 |
| emirates | 1.2 | 1.1 | – | 1.0 | 11.00 |
| etihad | 1.2 | 1.4 | – | – | 13.00 |
| singapore | 1.3 | 1.35 | – | – | 13.25 |
| asiamiles | 1.3 | 1.3 | 1.1 | – | 13.00 |
| turkish | 1.1 | 1.3 | – | 0.8 | 11.00 |
| lifemiles | 1.6 | 1.4 | 1.3 | 1.3 | 13.50 |
| virginatlantic | 1.5 | 1.4 | 1.5 | 0.8 | 14.50 |
| qantas | 1.25 | – | 1.3 | – | 12.75 |
| lufthansa | – | 1.3 | 1.3 | – | 13.00 |
| aeromexico | 0.8 | – | – | – | 8.00 (1 source) |
| finnair | 1.4 | – | – | – | 14.00 (1 source) |
| jal | – | 1.3 | – | – | 13.00 (1 source) |
| amex_mr | 2.0 | 2.2 | 1.5 | – | 20.00 |
| chase_ur | 2.05 | 2.0 | 1.5 | – | 20.00 |
| citi_ty | 1.9 | 1.6 | 1.5 | – | 16.00 |
| capitalone | 1.85 | 1.8 | 1.45 | – | 18.00 |
| bilt | 2.2 | 2.0 | 1.55 | – | 20.00 |
| wellsfargo | 1.75 | 1.5 | 1.4 | – | 15.00 |

No source values copa, velocity, eurobonus or eva; those are left empty.

### 10.2 Cost of buying miles
**Sources:**
- [Upgraded Points buy-promotion tracker](https://upgradedpoints.com/news/current-point-purchase-promotions/), 2026-10-01.
- [The Gate, "miles on sale"](https://thegatewithbriancohen.com/miles-and-points-on-sale-october-2-2026/), 2026-10-02.
- One Mile at a Time and AwardWallet pages for each program; their URLs and dates are in the comments of `milheiro.yaml`.

**`cpm_compra_atual`:**
- Normally the typical recurring promotional price, because promotions come back every few weeks.
- When a promotion is only realistic for huge purchases (Turkish: 250k+ miles), the base price is used instead.
- AUD prices were converted at 1 USD = 1.4411 AUD (Frankfurter, 2026-10-02).
- Programs with no published purchase price are left empty.

### 10.3 Transfer partners
**Sources:**
- [TPG transfer partners guide](https://thepointsguy.com/credit-cards/credit-card-transfer-partners/), 2026-09-01.
- [Citi → JAL](https://thepointsguy.com/news/citi-japan-airlines-transfer-partner/), 2026-09-21.
- [Prince of Travel — Amex MR Canada](https://princeoftravel.com/points-programs/american-express-membership-rewards-canada/), 2026-09-24.
- [Head for Points — Amex MR UK](https://www.headforpoints.com/2026/08/24/best-use-of-amex-membership-rewards-points/), 2026-08-24.
- [Point Hacks — Amex MR Australia](https://www.pointhacks.com.au/american-express/amex-membership-rewards-transfer-partner-pros-cons/), 2026-06-22.

**Uncertain:**
- Minimum transfers of 1,000 for Amex, Chase, Citi and Capital One come from a search summary.
- Bilt's minimum is 2,000 for Blue members and 1,000 for Silver and above.
- Citi transfers 1:1 only on Strata Elite, Strata Premier and Prestige; other Citi cards transfer at 1:0.7.

### 10.4 International promotion feeds (all returned items dated 2026-10-02)
**Feeds:**
- thepointsguy.com/feed
- frequentmiler.com/feed
- onemileatatime.com/feed
- viewfromthewing.com/feed
- headforpoints.com/feed (UK)
- pointhacks.com.au/feed (AU)
- princeoftravel.com/feed (CA)
- upgradedpoints.com/feed

Frequent Miler and View from the Wing return 403 to a browser User-Agent and 200 to a feed-reader UA.

**Transfer-bonus trackers:**
- https://frequentmiler.com/current-point-transfer-bonuses/
- https://thepointsguy.com/loyalty-programs/current-transfer-bonuses/

### 10.5 Exchange rates
| API | Endpoint | Coverage |
|---|---|---|
| Frankfurter (ECB) | `https://api.frankfurter.dev/v1/latest?from=USD` (`.app` redirects to `.dev`) | No ARS, CLP, COP |
| open.er-api.com | `https://open.er-api.com/v6/latest/USD` | Wider, includes ARS, CLP, COP |

Both are free, need no key and were tested 2026-10-02. They are cached for 24h.

### 10.6 Award search pages
- **Opened (HTTP 200):** delta, aeroplan, emirates, asiamiles, aeromexico, qantas, velocity, singapore (home page), virginatlantic (Flying Club page).
- **Domain confirmed only:** american, alaska, iberia, lifemiles, copa, lufthansa, eurobonus, finnair, jal, eva, united, flyingblue, british, qatar, etihad, turkish. These sites return 403 or time out for scripts.
- **Not verified:** ethiopian, saudia.


---

## 11. Timing tips (research 2026-10-02, ~45 sources)

Condensed in `config/dicas.yaml`. Key findings:
- **Booking day vs. flying day:** the day you buy barely matters (1–3%: Google Flights 2025-09-09, Expedia 2026-02-17, CheapAir 2024). The day you fly matters: Mon–Wed is ~13% cheaper than weekends (Google 2025), and domestic Tue ~14% cheaper than Sun (Expedia 2026).
- **Booking windows:**
  - Domestic US: 21–74 days, best ~42 (CheapAir 2024, 917M fares); Google 2025 best 39 (23–51); Going 2026 1–3 months.
  - Domestic Brazil: 28–35 days (KAYAK Brasil 2026-04-16); Melhores Destinos says 25–40 days in low season and 60–90 days in high season.
  - Regional (Americas): 37–87 days (Google, US→Mexico/Caribbean); 70–100 days (CheapAir, US→South America); 31–37 days (KAYAK BR, Brazil→LatAm).
  - Long-haul: CheapAir Europe 120–160 days, Asia 90–120 days; Going 2–8 months (4–10 at peak); Hopper Europe 3–6 months. Google 2025 says "don't wait for drops" on international.
- **Too early / too late:**
  - Domestic US beyond ~205 days costs +36% vs. the prime window (CheapAir).
  - Hopper expects no deals beyond ~150 days.
  - Inside 3 weeks, domestic US prices rise +8% / +26% / +59% at the 3-, 2- and 1-week marks (CheapAir).
- **Short-lead averages:** KAYAK and Expedia average booking-lead figures for international (1–4 weeks) likely reflect who books late, not price behaviour. They are not used for advice.
- **Sales in Brazil:**
  - GOL anniversary (~Jan 15)
  - Semana do Consumidor (~Mar 15)
  - Livelo (Jun 15)
  - LATAM (Jun 22)
  - Azul Fidelidade (Aug 30)
  - Dia do Cliente (Sep 15)
  - Smiles (Oct 18)
  - Black Friday (last Friday of Nov; Smiles Orange Friday up to 100% transfer bonus)
  - Azul (Dec 15)

  Sources: Melhores Destinos 2026-01-21, Passageiro de Primeira 2025-01-03, InfoMoney 2026-03-12, Melhores Cartões 2025-11-28.
- **Sales elsewhere:**
  - USA: January, fall (after Labor Day), Black Friday/Cyber Monday.
  - UK: January sales.
  - Mexico: Hot Sale (late May).
  - Chile: CyberDay (Jun) and CyberMonday (Oct).
  - Argentina: CyberMonday (Nov).
  - Colombia: Black Friday.
- **Seasons:**
  - Brazil: Jan, Jul, late Dec, early Feb; Carnaval and Réveillon almost never have deals.
  - Europe peak: Jun–Aug; late Aug/Sep is ~33% cheaper than late June (Hopper 2025).
  - Caribbean/Mexico: Dec–Apr high; Aug–Sep 20–40% lower, with hurricane risk (Going 2026).
  - Orlando/Miami: Jun–Jul and Dec high.
  - Japan: cherry blossom and Golden Week.
- **Gap:** no published "% of routes that drop later" from Hopper or Google was found.
