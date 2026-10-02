# Desenvolvimento — FareHunter

Plugin do Claude Code que encontra o jeito mais barato de viajar a partir do Brasil, ou dentro dele (valores em BRL; conversa e relatório em pt/en/es). Ele compara dinheiro, datas próximas, milhas próprias, compra de milhas, transferência de pontos e combinações. Entrada: `/farehunter:search <pedido>`.

## Layout do plugin
```
.claude-plugin/plugin.json        manifesto (nome "farehunter" → skills /farehunter:<skill>)
.claude-plugin/marketplace.json   marketplace no mesmo repo (source "./")
skills/search|profile|miles|setup/SKILL.md   instruções (em inglês; respondem no idioma do usuário)
agents/*-researcher.md            subagentes (tipo farehunter:<nome>)
.mcp.json                         kiwi, seats-aero (HTTP) e playwright (npx, perfil em ${CLAUDE_PLUGIN_DATA})
scripts/install.sh|.ps1           instaladores de um comando, com mensagens em pt/en/es
config/milheiro.yaml              valor INICIAL; copiado para a pasta de dados no 1º uso
src/ + pyproject.toml + uv.lock   motor Python (CLI `farehunter`), chamado via `uv run --project "${CLAUDE_PLUGIN_ROOT}" farehunter ...`
src/i18n/                         textos do relatório e do motor em pt/en/es (mensagens.py)
```
- `${CLAUDE_PLUGIN_ROOT}` é substituído no texto das skills e dos agentes, mas **não existe como variável de ambiente no Bash**: por isso todo comando leva o caminho já expandido.
- **Dados do usuário** ficam fora do plugin, em `~/.farehunter/` (ou `$FAREHUNTER_DATA`): `config/perfil.yaml`, `config/milheiro.yaml`, `.env` (chaves), `cache/`, `runs/<id>/`, `historico.csv`. Atualizar o plugin não apaga nada. O perfil do navegador do Playwright fica em `${CLAUDE_PLUGIN_DATA}/browser-profile`.
- Saldos **não** são persistidos: vão em `runs/<id>/saldos.json`, só para aquela busca.
- Chaves de API são gravadas pela própria pessoa no terminal (`farehunter chave seats`, com getpass), para não passarem pela conversa.
- Regras de segurança ficam **nas skills e nos agentes** (este arquivo não é carregado pelo plugin).

## Idiomas
- **Instruções:** as skills e os agentes estão em inglês e mandam o modelo conversar no idioma do usuário.
- **Relatório:** sai em pt, en ou es. O idioma é definido por `run novo --idioma` (padrão: o `idioma` do perfil) e gravado no `pedido.json`. Qualquer outro idioma usa `en`, e o modelo traduz sem mexer nos números.
- **Novo idioma:** copie o bloco `"en"` em `src/i18n/mensagens.py`, traduza, inclua o código em `IDIOMAS` (`src/i18n/__init__.py`) e rode `uv run pytest`. O teste exige as mesmas chaves em todos os idiomas.
- **Código interno:** nomes, comentários e chaves de JSON continuam em português.

## Desenvolver localmente
```bash
uv sync && uv run pytest
claude plugin validate . --strict
claude --plugin-dir .          # abre o Claude Code com o plugin desta pasta carregado
```
Antes de publicar uma versão, suba `version` em `.claude-plugin/plugin.json`.

## Código (`src/`, Python 3.12 + uv)
| Pacote | Papel |
|---|---|
| `normalizacao/schema.py` | Schema `Opcao`/`Perna` (valores **por passageiro**; `trecho` = ida/volta/ida_volta) |
| `normalizacao/links.py` | Deep links Smiles/LATAM/Azul (formatos verificados em 2026-10-02) |
| `calculo/custo.py` | Custo efetivo e financiamento de milhas (saldo → compra/transferência mais barata) |
| `calculo/ranking.py` | Combinações ida×volta, deduplicação entre fontes, ranking, referência, matriz, veredito de CPM |
| `calculo/relatorio.py` | Relatório markdown |
| `fontes/` | `google_flights.py` (fli), `kiwi.py` e `seats.py` (MCP via JSON-RPC), `promos.py` (RSS), `coleta.py` (coletas com degradação graciosa) |
| `mcp_seats/cliente.py` | Cliente da Partner API do Seats.aero (ativa com `SEATS_AERO_API_KEY`) |
| `infra/` | config YAML, cache com TTL, contadores de limite, histórico CSV, diretório de execução |

Comandos úteis: `uv run pytest`, `uv run farehunter --help`, `uv run farehunter buscar kiwi --origem GRU --destino REC --ida 2026-12-10`.

## Schema normalizado (para quem escreve opções à mão, ex.: Playwright)
```json
{"fonte": "playwright_latam", "tipo": "milhas", "programa": "latam_pass", "trecho": "ida",
 "pernas": [{"origem": "GRU", "destino": "REC", "data": "2026-12-10", "partida": "07:00", "chegada": "10:10",
             "cia": "LA", "voos": ["LA 3676"], "conexoes": 0, "duracao_min": 190}],
 "milhas": 12000, "taxas_brl": 35.9, "preco_brl": null, "bagagem_inclusa": false,
 "assentos_disponiveis": null, "confirmado_ao_vivo": true, "link": "https://..."}
```
- `tipo` é `dinheiro` ou `milhas`.
- `programa` é `smiles`, `latam_pass` ou `azul` (null para dinheiro).
- Preço, milhas e taxas são **por passageiro**.
- Registre com `uv run farehunter run registrar --run <dir> --fonte <fonte> --arquivo <json>`.

## Regras de segurança (obrigatórias)
- **Nunca** concluir compra, emissão, transferência de pontos ou pagamento. Parar no link.
- **Nunca** pedir, salvar ou registrar senha de programa de fidelidade, banco ou cartão.
  - Se um site exigir login, o usuário faz login **manualmente** no perfil persistente do Playwright (`./browser-profile`, no .gitignore).
  - Se ele não quiser, pule a fonte e avise.
- **Navegador:**
  - Só leitura, no máximo `playwright_paginas_por_execucao` páginas (contador em `uv run farehunter limite`).
  - Uma página por vez, ~5 s entre páginas.
  - Diante de CAPTCHA ou 403, parar sem contornar (sem proxies, sem trocar user-agent).
- **Seats.aero:** respeitar o limite diário (contador local), não usar Live Search e citar "seats.aero" como fonte.
- **Segredos** só em `.env` (no .gitignore). Ver `.env.example`.
- **Relatório:** dizer sempre o que é **cache** e o que foi **confirmado ao vivo**, e que preços mudam até a emissão.
- **`config/milheiro.yaml`:** nunca preencher com valores inventados. Todo número precisa de fonte e data, e só é gravado com confirmação do usuário (`/atualizar-milheiro`).
- **Balcões de milhas** (123milhas/MaxMilhas/HotMilhas) ficam fora. Ver docs/research.md §7.

## Quando uma fonte quebra
Os adaptadores estão isolados em `src/fontes/`; ver README §"Trocar uma fonte quebrada". Pesquisa e status das ferramentas: `docs/research.md`. Decisões: `docs/decisoes.md`.
## Como o custo é calculado

| Estratégia | Custo efetivo |
|---|---|
| Dinheiro | tarifa × pax (+ mala por trecho, se `bagagem_despachada` e a tarifa não incluir) |
| Milhas próprias | milhas/1000 × `cpm_valor_uso` + taxas |
| Comprar milhas | saldo usado × `cpm_valor_uso` + faltantes × `cpm_compra_atual` (respeitando o mínimo e o múltiplo de compra) + taxas |
| Transferir pontos | pontos = faltantes ÷ (1 + bônus) × proporção (respeitando o mínimo de transferência); custo = pontos × CPM dos pontos + taxas |
| Misto / aeroporto alternativo | soma das pernas; as milhas do mesmo programa somam antes de usar o saldo; + deslocamento × pax por trecho |

- **CPM de equilíbrio** = (tarifa em dinheiro comparável − taxas) ÷ milhas × 1000. Comprar milhas compensa quando ele é maior que `cpm_compra_atual`.
- **Ranking:** por custo; empates por duração e depois por conexões.
- **"Também possível":** estratégias trabalhosas (comprar, transferir, aeroporto alternativo) que economizam menos de `valor_minimo_economia_brl` saem do top e vão para essa seção.

## Limitações conhecidas

- **Google Flights** não tem API oficial. O `fli` usa endpoints internos que mudaram em ago/2026 e funcionam de forma intermitente. Se o calendário falhar, a coleta varre data a data (sweep). Se a busca toda falhar, a fonte aparece como indisponível. O uso é pessoal e de baixo volume; o ToS do Google proíbe automação contra o robots.txt (docs/decisoes.md).
- **Seats.aero** é cache: os dados podem ter horas ou dias. As 1–3 melhores opções em milhas são conferidas no site quando possível:
  - Smiles funciona sem login;
  - Azul costuma bloquear navegador automatizado.
- **Clube e categoria:** o preço em milhas que você vê pode ser menor (Clube Smiles ~8%) do que o das fontes externas. O relatório sinaliza isso.
- **LATAM Pass** só via site com login, no máximo 3 combinações de datas por execução.
- **Taxas** de programas estrangeiros em USD não são convertidas (só Smiles/Azul são usados, ambos em BRL).
- **CPM** muda toda semana; um `milheiro.yaml` velho distorce o veredito "compensa comprar".
- **Balcões de milhas** não são consultados (risco jurídico e de cancelamento; docs/research.md §7).

## Trocar uma fonte quebrada

Cada fonte é um módulo isolado em `src/fontes/`, que devolve `list[Opcao]` (schema em `src/normalizacao/schema.py`). O resto do sistema não sabe de onde vêm os dados.

1. Rode `uv run farehunter buscar <fonte> ...` para ver o erro. O `status.json` da execução também guarda o motivo.
2. **Google Flights:**
   - **Plano B:** instale a versão da página do fli, com a mesma API: `uv add "flights @ git+https://github.com/punitarani/fli@881aee5"`.
   - **Plano C:** use o `cheapdates` com backend `graph` (Chromium) para o calendário.
   - Nos dois casos, adapte só `src/fontes/google_flights.py`.
3. **Kiwi:**
   - Se o JSON-RPC direto falhar, o subagente pode usar a tool `mcp__plugin_farehunter_kiwi__search-flight` e normalizar a resposta com `farehunter normalizar --fonte kiwi`.
   - Se o formato mudar, ajuste `fontes/kiwi.py::normalizar`.
4. **Seats.aero:** MCP anônimo em `fontes/seats.py`; Partner API em `mcp_seats/cliente.py`. Os dois já normalizam para o mesmo schema.
5. **Fonte nova:**
   - Crie `src/fontes/<nome>.py` com uma função que devolva `list[Opcao]`.
   - Chame essa função em `fontes/coleta.py` dentro de `_tentar(...)`, para que falhas virem status.
   - Acrescente o TTL em `infra/cache.py`.
   - Escreva um teste.
6. Registre a mudança em `docs/decisoes.md`.
