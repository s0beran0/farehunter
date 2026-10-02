"""CLI `farehunter`: what the orchestrator and subagents call via `uv run --project <plugin> farehunter ...`.

Flow of a search run:
  farehunter run novo --origem GRU --destino REC --ida 2026-12-10 --volta 2026-12-17 [--flex 3] [--pax 2]
      → creates runs/<id>/pedido.json and prints the directory
  farehunter run registrar --run <dir> --fonte kiwi --arquivo opcoes.json     (already normalized options)
  farehunter run falha     --run <dir> --fonte google_flights --motivo "..."
  farehunter analisar --run <dir>
      → relatorio.md, ranking.json and new rows in historico.csv
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import i18n
from calculo.ranking import Pedido, analisar
from calculo.relatorio import gerar_relatorio
from infra import historico, runs
from infra.cache import Cache, chave_busca
from infra.config import carregar_env, carregar_milheiro, carregar_perfil, preparar_dados
from infra.limites import Contadores, LimiteExcedido
from normalizacao.schema import carregar_opcoes

RUNS_DIR = runs.RUNS_DIR


def _json_out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _ler_json(caminho: str | Path):
    if str(caminho) == "-":
        return json.load(sys.stdin)
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


# --- run ---------------------------------------------------------------------------------------

def _parse_saldos(itens: list[str]) -> dict[str, int] | None:
    """['smiles=45000', 'livelo=12.000', 'azul=0'] → dict. None if any item is invalid."""
    saldos = {}
    for item in itens:
        nome, _, valor = item.partition("=")
        try:
            saldos[nome.strip().lower()] = int(valor.replace(".", "").replace("_", "").strip())
        except ValueError:
            print(f"error: invalid balance '{item}' (use program=number, e.g. smiles=45000)", file=sys.stderr)
            return None
    return saldos


def cmd_run_saldos(a) -> int:
    saldos = _parse_saldos(a.saldo or [])
    if saldos is None:
        return 2
    _json_out(runs.gravar_saldos(Path(a.run), saldos))
    return 0


def cmd_run_novo(a) -> int:
    perfil = carregar_perfil()
    origens = [s.upper() for s in (a.origem or perfil.aeroportos_origem)]
    if not origens:
        print("erro: informe --origem ou preencha aeroportos_origem no perfil.yaml", file=sys.stderr)
        return 2
    noites_min = noites_max = None
    if a.noites:
        partes = a.noites.replace(" ", "").split("-")
        noites_min, noites_max = int(partes[0]), int(partes[-1])
    if not a.ida and not a.ida_de:
        print("erro: informe --ida YYYY-MM-DD ou --ida-de/--ida-ate", file=sys.stderr)
        return 2
    pedido = {
        "origens": origens,
        "destinos": [s.upper() for s in a.destino],
        "data_ida": a.ida or a.ida_de,
        "data_volta": a.volta,
        "flex_dias": a.flex if a.flex is not None else perfil.flex_dias_padrao,
        "passageiros": a.pax or perfil.passageiros_padrao,
        "cabine": a.cabine,
        "ida_de": a.ida_de,
        "ida_ate": a.ida_ate or a.ida_de,
        "noites_min": noites_min,
        "noites_max": noites_max,
        "hubs": [h.upper() for h in (a.hubs or [])],
    }
    Pedido(**pedido)  # validates
    from infra import perfil_io

    bruto = perfil_io.carregar_bruto()
    pedido["idioma"] = i18n.normalizar(a.idioma or bruto.get("idioma"))
    pedido["moeda"] = (a.moeda or bruto.get("moeda") or "BRL").upper()
    pedido["pais"] = (a.pais or bruto.get("pais") or "BR").upper()
    saldos = _parse_saldos(a.saldo or [])
    if saldos is None:
        return 2
    rid = f"{datetime.now():%Y%m%d-%H%M%S}_{origens[0]}-{pedido['destinos'][0]}"
    d = RUNS_DIR / rid
    (d / "opcoes").mkdir(parents=True, exist_ok=True)
    (d / "bruto").mkdir(exist_ok=True)
    (d / "pedido.json").write_text(json.dumps(pedido, indent=2), encoding="utf-8")
    if a.saldo is not None:
        runs.gravar_saldos(d, saldos)
    (d / "status.json").write_text("{}", encoding="utf-8")
    _json_out({"run": str(d), "pedido": pedido, "alternativos_origem": [x.iata for x in perfil.aeroportos_alternativos_origem]})
    return 0


def cmd_run_registrar(a) -> int:
    run = Path(a.run)
    dados = _ler_json(a.arquivo)
    if isinstance(dados, dict):
        dados = dados.get("opcoes", [])
    opcoes, avisos = carregar_opcoes(dados)
    n = runs.registrar_opcoes(run, a.fonte, opcoes)
    _json_out({"fonte": a.fonte, "registradas": n, "descartadas": len(avisos), "avisos": avisos[:10]})
    return 0


def cmd_run_falha(a) -> int:
    runs.registrar_falha(Path(a.run), a.fonte, a.motivo)
    _json_out({"fonte": a.fonte, "registrado": "falha"})
    return 0


def cmd_run_opcao(a) -> int:
    achado = runs.buscar_opcao(Path(a.run), a.id)
    if achado is None:
        print(f"option {a.id} not found", file=sys.stderr)
        return 1
    _json_out(achado[1])
    return 0


def cmd_run_confirmar(a) -> int:
    _json_out(runs.confirmar(Path(a.run), a.id, a.via, milhas=a.milhas, taxas=a.taxas, preco=a.preco,
                             indisponivel=a.indisponivel, link=a.link, obs=a.obs))
    return 0


def cmd_perfil(a) -> int:
    import difflib

    from infra import perfil_io

    if a.acao == "status":
        bruto = perfil_io.carregar_bruto()
        _json_out({"configurado": bool(bruto.get("configurado")), "faltando": perfil_io.faltando(bruto), "perfil": bruto})
        return 0
    respostas = _ler_json(a.arquivo)
    try:
        if a.simular:
            atual = perfil_io.carregar_bruto()
            novo = perfil_io.validar(perfil_io._mesclar(atual, {**respostas, "configurado": True}))
            antigo_txt = perfil_io.ARQUIVO.read_text(encoding="utf-8") if perfil_io.ARQUIVO.exists() else ""
            novo_txt = perfil_io.renderizar(novo)
        else:
            novo, antigo_txt = perfil_io.salvar(respostas)
            novo_txt = perfil_io.ARQUIVO.read_text(encoding="utf-8")
    except perfil_io.PerfilInvalido as e:
        print(f"PERFIL INVÁLIDO: {e}", file=sys.stderr)
        return 2
    diff = "".join(difflib.unified_diff(antigo_txt.splitlines(True), novo_txt.splitlines(True),
                                        "perfil.yaml (atual)", "perfil.yaml (novo)"))
    _json_out({"gravado": not a.simular, "diff": diff, "faltando": perfil_io.faltando(novo)})
    return 0


def cmd_analisar(a) -> int:
    from passagens.analise import analisar_execucao

    texto, ranking = analisar_execucao(Path(a.run), top=a.top, exploratorio=a.exploratorio,
                                       gravar_historico=not a.sem_historico)
    if a.json:
        _json_out({"relatorio": str(Path(a.run) / "relatorio.md"), "top": ranking[: a.top]})
    else:
        print(texto)
    return 0


# --- utilities for subagents ---------------------------------------------------------------------

def cmd_cache(a) -> int:
    c = Cache()
    chave = chave_busca(*a.chave)
    if a.acao == "get":
        dados = c.get(a.fonte, chave, a.ttl)
        if dados is None:
            print("MISS", file=sys.stderr)
            return 1
        _json_out(dados)
    elif a.acao == "set":
        _json_out({"salvo": str(c.set(a.fonte, chave, _ler_json(a.arquivo)))})
    else:
        _json_out({"removidos": c.limpar_expirados()})
    return 0


def cmd_limite(a) -> int:
    perfil = carregar_perfil()
    ct = Contadores(limites=perfil.limites)
    if a.acao == "consumir":
        try:
            restante = ct.consumir(a.nome, a.qtd, execucao=a.run)
        except LimiteExcedido as e:
            print(f"LIMITE: {e}", file=sys.stderr)
            return 3
        _json_out({"nome": a.nome, "restante": restante})
    else:
        _json_out({n: {"usado": ct.usado(n, a.run), "limite": ct.limites[n]} for n in ct.limites})
    return 0


def cmd_milheiro(a) -> int:
    import difflib

    import yaml

    from infra.config import CONFIG_DIR, milheiro_de_dict

    arq = CONFIG_DIR / "milheiro.yaml"
    if a.acao == "checar":
        m = carregar_milheiro()
        avisos = m.avisos_validade(date.today())
        _json_out({"valido": not avisos, "avisos": avisos, "arquivo": str(arq)})
        return 0 if not avisos else 1
    if a.acao == "mostrar":
        print(arq.read_text(encoding="utf-8"))
        return 0
    # propor / salvar: full YAML from --arquivo or stdin
    novo_txt = sys.stdin.read() if a.arquivo == "-" else Path(a.arquivo).read_text(encoding="utf-8")
    try:
        milheiro_de_dict(yaml.safe_load(novo_txt) or {})
    except (yaml.YAMLError, ValueError, TypeError, AttributeError) as e:
        print(f"MILHEIRO INVÁLIDO: {e}", file=sys.stderr)
        return 2
    antigo = arq.read_text(encoding="utf-8") if arq.exists() else ""
    diff = "".join(difflib.unified_diff(antigo.splitlines(True), novo_txt.splitlines(True),
                                        "milheiro.yaml (atual)", "milheiro.yaml (proposto)"))
    if a.acao == "salvar":
        arq.write_text(novo_txt, encoding="utf-8")
    _json_out({"gravado": a.acao == "salvar", "diff": diff})
    return 0


def cmd_dados(a) -> int:
    from infra.config import CONFIG_DIR, DADOS

    _json_out({"dados": str(DADOS), "config": str(CONFIG_DIR), "runs": str(RUNS_DIR),
               "browser_profile": str(DADOS / "browser-profile"), "env": str(DADOS / ".env")})
    return 0


def cmd_diagnostico(a) -> int:
    """Check the environment and say, for each item, whether it is OK and how to fix it."""
    import platform
    import shutil

    import httpx

    from infra import perfil_io
    from infra.config import DADOS

    itens = []

    def item(nome, ok, detalhe, como_resolver=""):
        itens.append({"item": nome, "ok": ok, "detalhe": detalhe, "como_resolver": "" if ok else como_resolver})

    item("sistema", True, f"{platform.system()} {platform.release()} · Python {platform.python_version()}")
    item("pasta de dados", DADOS.exists(), str(DADOS), "will be created on first use")
    node = shutil.which("npx")
    item("node/npx (opcional)", bool(node), node or "not found",
         "Only needed for LATAM Pass and live confirmation. Download the LTS: https://nodejs.org/en/download")
    from fontes.mcp_http import HEADERS

    http = httpx.Client(timeout=15)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "diagnostico", "version": "0"}}}
    for nome, url, mcp in [("internet: Kiwi", "https://mcp.kiwi.com", True),
                           ("internet: Seats.aero", "https://seats.aero/mcp", True),
                           ("internet: Google Flights", "https://www.google.com/travel/flights", False)]:
        try:
            r = http.post(url, headers=HEADERS, json=init) if mcp else http.get(url)
            item(nome, r.status_code < 400, f"HTTP {r.status_code}", "The service returned an error; try again later.")
        except httpx.HTTPError as e:
            item(nome, False, type(e).__name__, "Check the connection, VPN or company firewall.")
    chave = bool(os.environ.get("SEATS_AERO_API_KEY"))
    item("chave Seats.aero (opcional)", chave, "set" if chave else "no key: miles only for flights within 60 days",
         "Optional (Seats.aero Pro, US$ 9.99/month): https://seats.aero/pro → Settings → API. "
         "Depois rode no seu terminal o comando que a skill /farehunter:setup mostrar.")
    bruto = perfil_io.carregar_bruto()
    item("perfil", bool(bruto.get("configurado")), "configured" if bruto.get("configurado") else "not configured",
         "Run /farehunter:profile")
    avisos = carregar_milheiro().avisos_validade(date.today())
    item("milheiro (CPM)", not avisos, "up to date" if not avisos else "; ".join(avisos[:2]), "Run /farehunter:miles")
    _json_out({"ok_essencial": all(i["ok"] for i in itens if "opcional" not in i["item"] and i["item"] not in ("perfil", "milheiro (CPM)")),
               "itens": itens})
    return 0


def cmd_chave(a) -> int:
    """Save a key into the data folder's .env, read from the terminal without echo (never passes through the chat)."""
    import getpass

    from infra.config import DADOS

    nomes = {"seats": "SEATS_AERO_API_KEY"}
    var = nomes[a.servico]
    valor = (sys.stdin.readline() if a.stdin else getpass.getpass(f"Paste your {var} and press Enter (it will not be shown): ")).strip()
    if not valor:
        print("nothing saved", file=sys.stderr)
        return 1
    env = DADOS / ".env"
    DADOS.mkdir(parents=True, exist_ok=True)
    linhas = [l for l in (env.read_text(encoding="utf-8").splitlines() if env.exists() else []) if not l.startswith(f"{var}=")]
    env.write_text("\n".join([*linhas, f"{var}={valor}"]) + "\n", encoding="utf-8")
    try:
        env.chmod(0o600)
    except OSError:
        pass
    print(f"✓ {var} saved to {env}")
    return 0


def cmd_programas(a) -> int:
    """List the program registry: miles programs (award search coverage, link type) and points programs."""
    from infra.programas import carregar

    reg = carregar()
    _json_out({
        "milhas": [{"id": p.id, "nome": p.nome, "cias": list(p.cias), "busca_de_resgates": bool(p.seats),
                    "deep_link": p.link in ("smiles", "latam_pass", "azul")} for p in reg.milhas.values()],
        "pontos": [{"id": p.id, "nome": p.nome, "moeda": p.moeda,
                    "parceiros": {x.destino: x.proporcao for x in reg.parceiros_de(p.id)}} for p in reg.pontos.values()],
    })
    return 0


def cmd_link(a) -> int:
    from normalizacao import links

    if a.programa == "google":
        from fontes.google_flights import link_google

        print(link_google(a.origem, a.destino, a.ida, a.volta))
    else:
        print(links.programa(a.programa, a.origem, a.destino, a.ida, a.volta, a.pax))
    return 0


def cmd_normalizar(a) -> int:
    from normalizacao import adaptadores

    bruto = _ler_json(a.entrada)
    opcoes = adaptadores.normalizar(a.fonte, bruto, trecho=a.trecho, passageiros=a.pax)
    saida = [o.to_dict() for o in opcoes]
    if a.saida:
        Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
        _json_out({"opcoes": len(saida), "saida": a.saida})
    else:
        _json_out(saida)
    return 0


def main(argv: list[str] | None = None) -> int:
    preparar_dados()
    carregar_env()
    p = argparse.ArgumentParser(prog="farehunter")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run").add_subparsers(dest="acao", required=True)
    novo = run.add_parser("novo")
    novo.add_argument("--origem", nargs="*")
    novo.add_argument("--destino", nargs="+", required=True)
    novo.add_argument("--ida", help="exact outbound date (or use --ida-de/--ida-ate for a window)")
    novo.add_argument("--ida-de", help="outbound window start (YYYY-MM-DD)")
    novo.add_argument("--ida-ate", help="outbound window end (YYYY-MM-DD)")
    novo.add_argument("--noites", help="trip length in nights, e.g. 5-7 or 7 (round trip without a fixed return date)")
    novo.add_argument("--hubs", nargs="*", help="connection airports allowed for separate tickets (default: config/hubs.yaml for the country)")
    novo.add_argument("--volta")
    novo.add_argument("--flex", type=int)
    novo.add_argument("--pax", type=int)
    novo.add_argument("--cabine", default="economy")
    novo.add_argument("--idioma", help="pt | en | es (report language; default: the profile's)")
    novo.add_argument("--moeda", help="ISO 4217 currency for every price (default: the profile's)")
    novo.add_argument("--pais", help="ISO 3166 country, point of sale for cash fares (default: the profile's)")
    novo.add_argument("--saldo", nargs="*", help="TODAY's balances: smiles=45000 livelo=12000 (never stored in the profile)")
    novo.set_defaults(f=cmd_run_novo)
    reg = run.add_parser("registrar")
    reg.add_argument("--run", required=True)
    reg.add_argument("--fonte", required=True)
    reg.add_argument("--arquivo", required=True, help="JSON with a list of normalized options ('-' = stdin)")
    reg.set_defaults(f=cmd_run_registrar)
    fal = run.add_parser("falha")
    fal.add_argument("--run", required=True)
    fal.add_argument("--fonte", required=True)
    fal.add_argument("--motivo", required=True)
    fal.set_defaults(f=cmd_run_falha)

    sa = run.add_parser("saldos", help="save the given balances for this run")
    sa.add_argument("--run", required=True)
    sa.add_argument("--saldo", nargs="*", default=[])
    sa.set_defaults(f=cmd_run_saldos)
    op = run.add_parser("opcao", help="show one option by id")
    op.add_argument("--run", required=True)
    op.add_argument("--id", required=True)
    op.set_defaults(f=cmd_run_opcao)
    cf = run.add_parser("confirmar", help="record the live-confirmation result of an option")
    cf.add_argument("--run", required=True)
    cf.add_argument("--id", required=True)
    cf.add_argument("--via", required=True, help="e.g. playwright_smiles")
    cf.add_argument("--milhas", type=int)
    cf.add_argument("--taxas", type=float)
    cf.add_argument("--preco", type=float)
    cf.add_argument("--link")
    cf.add_argument("--indisponivel", action="store_true")
    cf.add_argument("--obs", help="free-text note (e.g. price read on the card, no tax)")
    cf.set_defaults(f=cmd_run_confirmar)

    an = sub.add_parser("analisar")
    an.add_argument("--run", required=True)
    an.add_argument("--top", type=int, default=5)
    an.add_argument("--json", action="store_true")
    an.add_argument("--sem-historico", action="store_true")
    an.add_argument("--exploratorio", action="store_true",
                    help="include unvalidated options (cache, calendar hints). Never use for the final recommendation")
    an.set_defaults(f=cmd_analisar)

    ca = sub.add_parser("cache")
    ca.add_argument("acao", choices=["get", "set", "limpar"])
    ca.add_argument("--fonte", default="")
    ca.add_argument("--chave", nargs="*", default=[])
    ca.add_argument("--arquivo")
    ca.add_argument("--ttl", type=float)
    ca.set_defaults(f=cmd_cache)

    li = sub.add_parser("limite")
    li.add_argument("acao", choices=["consumir", "status"])
    li.add_argument("--nome", default="seats_aero_chamadas_dia")
    li.add_argument("--qtd", type=int, default=1)
    li.add_argument("--run")
    li.set_defaults(f=cmd_limite)

    pe = sub.add_parser("perfil", help="profile status, or save the interview answers")
    pe.add_argument("acao", choices=["status", "salvar"])
    pe.add_argument("--arquivo", default="-", help="JSON with the answers (partial; '-' = stdin)")
    pe.add_argument("--simular", action="store_true", help="only show the diff, do not save")
    pe.set_defaults(f=cmd_perfil)

    mi = sub.add_parser("milheiro")
    mi.add_argument("acao", choices=["checar", "mostrar", "propor", "salvar"])
    mi.add_argument("--arquivo", default="-", help="full proposed YAML (propor/salvar); '-' = stdin")
    mi.set_defaults(f=cmd_milheiro)

    dg = sub.add_parser("diagnostico", help="check the environment and explain how to fix what is missing")
    dg.set_defaults(f=cmd_diagnostico)

    ch = sub.add_parser("chave", help="save an API key into the data folder's .env (run it in your own terminal)")
    ch.add_argument("servico", choices=["seats"])
    ch.add_argument("--stdin", action="store_true", help="read the key from standard input")
    ch.set_defaults(f=cmd_chave)

    da = sub.add_parser("dados", help="show where the user's data lives")
    da.set_defaults(f=cmd_dados)

    pg = sub.add_parser("programas", help="list supported miles and points programs")
    pg.set_defaults(f=cmd_programas)

    lk = sub.add_parser("link", help="deep link to book/search on the site")
    lk.add_argument("programa", help="miles program id from config/programas.yaml, or 'google'")
    lk.add_argument("--origem", required=True)
    lk.add_argument("--destino", required=True)
    lk.add_argument("--ida", required=True)
    lk.add_argument("--volta")
    lk.add_argument("--pax", type=int, default=1)
    lk.set_defaults(f=cmd_link)

    no = sub.add_parser("normalizar")
    no.add_argument("--fonte", required=True)
    no.add_argument("--entrada", required=True)
    no.add_argument("--saida")
    no.add_argument("--trecho", default=None, help="ida | volta | ida_volta (when the source does not say)")
    no.add_argument("--pax", type=int, default=1, help="passengers in the search, to convert the total price to per person")
    no.set_defaults(f=cmd_normalizar)

    from fontes import registrar_comandos

    registrar_comandos(sub)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
