"""CLI `farehunter`: o que o orquestrador e os subagentes chamam via `uv run --project <plugin> farehunter ...`.

Fluxo de uma execução:
  farehunter run novo --origem GRU --destino REC --ida 2026-12-10 --volta 2026-12-17 [--flex 3] [--pax 2]
      → cria data/runs/<id>/pedido.json e imprime o diretório
  farehunter run registrar --run <dir> --fonte kiwi --arquivo opcoes.json     (opções já normalizadas)
  farehunter run falha     --run <dir> --fonte google_flights --motivo "..."
  farehunter analisar --run <dir>
      → relatorio.md, ranking.json e linhas novas em data/historico.csv
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
    """['smiles=45000', 'livelo=12.000', 'azul=0'] → dict. None se algum item for inválido."""
    saldos = {}
    for item in itens:
        nome, _, valor = item.partition("=")
        try:
            saldos[nome.strip().lower()] = int(valor.replace(".", "").replace("_", "").strip())
        except ValueError:
            print(f"erro: saldo inválido '{item}' (use programa=numero, ex. smiles=45000)", file=sys.stderr)
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
    pedido = {
        "origens": origens,
        "destinos": [s.upper() for s in a.destino],
        "data_ida": a.ida,
        "data_volta": a.volta,
        "flex_dias": a.flex if a.flex is not None else perfil.flex_dias_padrao,
        "passageiros": a.pax or perfil.passageiros_padrao,
        "cabine": a.cabine,
    }
    Pedido(**pedido)  # valida
    from infra import perfil_io

    pedido["idioma"] = i18n.normalizar(a.idioma or perfil_io.carregar_bruto().get("idioma"))
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
        print(f"opção {a.id} não encontrada", file=sys.stderr)
        return 1
    _json_out(achado[1])
    return 0


def cmd_run_confirmar(a) -> int:
    _json_out(runs.confirmar(Path(a.run), a.id, a.via, milhas=a.milhas, taxas_brl=a.taxas, preco_brl=a.preco,
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
    run = Path(a.run)
    dados_pedido = _ler_json(run / "pedido.json")
    i18n.definir(dados_pedido.pop("idioma", None))
    pedido = Pedido(**dados_pedido)
    perfil = carregar_perfil()
    milheiro = carregar_milheiro()
    saldos = runs.ler_saldos(run)
    aviso_saldos = runs.aplicar_saldos(perfil, saldos)
    brutos = []
    for arq in sorted((run / "opcoes").glob("*.json")):
        brutos.extend(_ler_json(arq))
    opcoes, avisos_carga = carregar_opcoes(brutos)

    resultado = analisar(opcoes, pedido, perfil, milheiro, hoje=date.today())
    resultado.avisos.extend(avisos_carga[:5])
    if aviso_saldos:
        resultado.avisos.insert(0, aviso_saldos)
    st = runs.status(run)
    fontes_ok = [f for f, s in st.items() if s.get("ok")]
    falhas = {f: s.get("motivo") or "sem detalhe" for f, s in st.items() if not s.get("ok")}
    for f, s in st.items():
        if s.get("ok") and s.get("motivo"):
            resultado.avisos.append(f"{f}: {s['motivo']}")

    comparacao = historico.comparar_com_anterior(opcoes) if not a.sem_historico else []
    texto = gerar_relatorio(resultado, fontes_ok, falhas, top=a.top, milheiro=milheiro, saldos=saldos)
    if comparacao:
        texto += f"\n\n{i18n.t('rel.desde_ultima')}\n\n" + "\n".join(f"- {m}" for m in comparacao[:15])
    (run / "relatorio.md").write_text(texto, encoding="utf-8")

    ranking = [
        {
            "posicao": i,
            "descricao": c.descricao(),
            "custo_brl": c.custo_brl,
            "economia_brl": resultado.economia(c),
            "data_ida": c.data_ida,
            "data_volta": c.data_volta,
            "estrategias": sorted(c.estrategias),
            "riscos": c.riscos,
            "opcoes": [
                {"id": o.id, "fonte": o.fonte, "tipo": o.tipo, "programa": o.programa, "trecho": o.trecho,
                 "pernas": [{"origem": p.origem, "destino": p.destino, "data": p.data, "partida": p.partida,
                             "voos": p.voos} for p in o.pernas],
                 "preco_brl": o.preco_brl, "milhas": o.milhas, "taxas_brl": o.taxas_brl,
                 "confirmado_ao_vivo": o.confirmado_ao_vivo, "link": o.link}
                for o in c.opcoes
            ],
            "programas_milhas_cache": [o.programa for o in c.opcoes if o.tipo == "milhas" and not o.confirmado_ao_vivo],
        }
        for i, c in enumerate(resultado.principais[:20], 1)
    ]
    (run / "ranking.json").write_text(json.dumps(ranking, ensure_ascii=False, indent=1), encoding="utf-8")
    if not a.sem_historico:
        historico.gravar(opcoes)
    if a.json:
        _json_out({"relatorio": str(run / "relatorio.md"), "top": ranking[: a.top]})
    else:
        print(texto)
    return 0


# --- utilitários para subagentes ------------------------------------------------------------------

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
    # propor / salvar: YAML completo vindo de --arquivo ou stdin
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
    """Confere o ambiente e diz, para cada item, se está ok e como resolver."""
    import platform
    import shutil

    import httpx

    from infra import perfil_io
    from infra.config import DADOS

    itens = []

    def item(nome, ok, detalhe, como_resolver=""):
        itens.append({"item": nome, "ok": ok, "detalhe": detalhe, "como_resolver": "" if ok else como_resolver})

    item("sistema", True, f"{platform.system()} {platform.release()} · Python {platform.python_version()}")
    item("pasta de dados", DADOS.exists(), str(DADOS), "será criada no primeiro uso")
    node = shutil.which("npx")
    item("node/npx (opcional)", bool(node), node or "não encontrado",
         "Necessário só para LATAM Pass e confirmação ao vivo. Baixe a versão LTS: https://nodejs.org/pt/download")
    from fontes.mcp_http import HEADERS

    http = httpx.Client(timeout=15)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "diagnostico", "version": "0"}}}
    for nome, url, mcp in [("internet: Kiwi", "https://mcp.kiwi.com", True),
                           ("internet: Seats.aero", "https://seats.aero/mcp", True),
                           ("internet: Google Flights", "https://www.google.com/travel/flights", False)]:
        try:
            r = http.post(url, headers=HEADERS, json=init) if mcp else http.get(url)
            item(nome, r.status_code < 400, f"HTTP {r.status_code}", "Serviço respondeu com erro; tente mais tarde.")
        except httpx.HTTPError as e:
            item(nome, False, type(e).__name__, "Verifique a conexão, VPN ou firewall da empresa.")
    chave = bool(os.environ.get("SEATS_AERO_API_KEY"))
    item("chave Seats.aero (opcional)", chave, "definida" if chave else "sem chave: milhas só para voos em até 60 dias",
         "Opcional (Seats.aero Pro, US$ 9,99/mês): https://seats.aero/pro → Settings → API. "
         "Depois rode no seu terminal o comando que a skill /farehunter:setup mostrar.")
    bruto = perfil_io.carregar_bruto()
    item("perfil", bool(bruto.get("configurado")), "configurado" if bruto.get("configurado") else "não configurado",
         "Rode /farehunter:profile")
    avisos = carregar_milheiro().avisos_validade(date.today())
    item("milheiro (CPM)", not avisos, "atualizado" if not avisos else "; ".join(avisos[:2]), "Rode /farehunter:miles")
    _json_out({"ok_essencial": all(i["ok"] for i in itens if "opcional" not in i["item"] and i["item"] not in ("perfil", "milheiro (CPM)")),
               "itens": itens})
    return 0


def cmd_chave(a) -> int:
    """Grava uma chave no .env da pasta de dados, lendo do terminal sem mostrar (não passa pela conversa)."""
    import getpass

    from infra.config import DADOS

    nomes = {"seats": "SEATS_AERO_API_KEY"}
    var = nomes[a.servico]
    valor = (sys.stdin.readline() if a.stdin else getpass.getpass(f"Cole a chave {var} e tecle Enter: ")).strip()
    if not valor:
        print("nada gravado", file=sys.stderr)
        return 1
    env = DADOS / ".env"
    DADOS.mkdir(parents=True, exist_ok=True)
    linhas = [l for l in (env.read_text(encoding="utf-8").splitlines() if env.exists() else []) if not l.startswith(f"{var}=")]
    env.write_text("\n".join([*linhas, f"{var}={valor}"]) + "\n", encoding="utf-8")
    try:
        env.chmod(0o600)
    except OSError:
        pass
    print(f"✓ {var} gravada em {env}")
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
    novo.add_argument("--ida", required=True)
    novo.add_argument("--volta")
    novo.add_argument("--flex", type=int)
    novo.add_argument("--pax", type=int)
    novo.add_argument("--cabine", default="economy")
    novo.add_argument("--idioma", help="pt | en | es (idioma do relatório; padrão: o do perfil)")
    novo.add_argument("--saldo", nargs="*", help="saldos de HOJE: smiles=45000 livelo=12000 (não ficam no perfil)")
    novo.set_defaults(f=cmd_run_novo)
    reg = run.add_parser("registrar")
    reg.add_argument("--run", required=True)
    reg.add_argument("--fonte", required=True)
    reg.add_argument("--arquivo", required=True, help="JSON com lista de opções normalizadas ('-' = stdin)")
    reg.set_defaults(f=cmd_run_registrar)
    fal = run.add_parser("falha")
    fal.add_argument("--run", required=True)
    fal.add_argument("--fonte", required=True)
    fal.add_argument("--motivo", required=True)
    fal.set_defaults(f=cmd_run_falha)

    sa = run.add_parser("saldos", help="grava os saldos informados para esta execução")
    sa.add_argument("--run", required=True)
    sa.add_argument("--saldo", nargs="*", default=[])
    sa.set_defaults(f=cmd_run_saldos)
    op = run.add_parser("opcao", help="mostra uma opção pelo id")
    op.add_argument("--run", required=True)
    op.add_argument("--id", required=True)
    op.set_defaults(f=cmd_run_opcao)
    cf = run.add_parser("confirmar", help="grava o resultado da confirmação ao vivo de uma opção")
    cf.add_argument("--run", required=True)
    cf.add_argument("--id", required=True)
    cf.add_argument("--via", required=True, help="ex.: playwright_smiles")
    cf.add_argument("--milhas", type=int)
    cf.add_argument("--taxas", type=float)
    cf.add_argument("--preco", type=float)
    cf.add_argument("--link")
    cf.add_argument("--indisponivel", action="store_true")
    cf.add_argument("--obs", help="observação livre (ex.: preço lido no card, sem taxa)")
    cf.set_defaults(f=cmd_run_confirmar)

    an = sub.add_parser("analisar")
    an.add_argument("--run", required=True)
    an.add_argument("--top", type=int, default=5)
    an.add_argument("--json", action="store_true")
    an.add_argument("--sem-historico", action="store_true")
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

    pe = sub.add_parser("perfil", help="status do perfil ou gravação das respostas da entrevista")
    pe.add_argument("acao", choices=["status", "salvar"])
    pe.add_argument("--arquivo", default="-", help="JSON com as respostas (parcial; '-' = stdin)")
    pe.add_argument("--simular", action="store_true", help="só mostra o diff, não grava")
    pe.set_defaults(f=cmd_perfil)

    mi = sub.add_parser("milheiro")
    mi.add_argument("acao", choices=["checar", "mostrar", "propor", "salvar"])
    mi.add_argument("--arquivo", default="-", help="YAML completo proposto (propor/salvar); '-' = stdin")
    mi.set_defaults(f=cmd_milheiro)

    dg = sub.add_parser("diagnostico", help="confere o ambiente e diz como resolver o que faltar")
    dg.set_defaults(f=cmd_diagnostico)

    ch = sub.add_parser("chave", help="grava uma chave de API no .env da pasta de dados (rode no seu terminal)")
    ch.add_argument("servico", choices=["seats"])
    ch.add_argument("--stdin", action="store_true", help="lê a chave da entrada padrão")
    ch.set_defaults(f=cmd_chave)

    da = sub.add_parser("dados", help="mostra onde ficam os dados do usuário")
    da.set_defaults(f=cmd_dados)

    lk = sub.add_parser("link", help="deep link para emitir/buscar no site")
    lk.add_argument("programa", choices=["smiles", "latam_pass", "azul", "google"])
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
    no.add_argument("--trecho", default=None, help="ida | volta | ida_volta (quando a fonte não diz)")
    no.add_argument("--pax", type=int, default=1, help="passageiros da busca, para converter preço total em por pessoa")
    no.set_defaults(f=cmd_normalizar)

    from fontes import registrar_comandos

    registrar_comandos(sub)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
