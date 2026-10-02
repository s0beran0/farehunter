"""Deterministic collectors used by the subagents: they run the searches and write into the run directory.

Each collector catches failures per source/call and records them in status.json (graceful degradation):
a broken source never blocks the others.

Stages of a search:
1. `coletar_dinheiro` / `coletar_datas` / `coletar_milhas`: broad collection (calendars are only hints).
2. `coletar_posicionamento`: gateway airports for separate tickets (origin→hub + hub→destination).
3. `pendencias` → `coletar_detalhes` / live confirmation: validate whatever could win, until the best
   combination is made only of validated options.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fontes import google_flights, kiwi
from infra.config import carregar_perfil
from infra.runs import ler_pedido, registrar_falha, registrar_opcoes
from normalizacao.schema import Opcao

MAX_DETALHES = 8  # per-date searches per `coletar_detalhes` call
MAX_HUBS = 3


def _locais(p: dict) -> tuple[dict, dict]:
    """Currency/point-of-sale kwargs for Google Flights and Kiwi, taken from the request."""
    moeda, pais = p.get("moeda", "BRL"), p.get("pais", "BR")
    return {"moeda": moeda, "pais": pais}, {"moeda": moeda, "idioma": p.get("idioma", "en")}


def _iso(d: date) -> str:
    return d.isoformat()


def pedido_de(p: dict):
    """Pedido object (windows, trip length) from pedido.json."""
    from calculo.ranking import Pedido

    campos = {k: v for k, v in p.items() if k in Pedido.__dataclass_fields__}
    return Pedido(**campos)


def _rotas(pedido: dict, com_alternativos: bool = True) -> list[tuple[str, str]]:
    perfil = carregar_perfil()
    origens = list(pedido["origens"])
    destinos = list(pedido["destinos"])
    if com_alternativos:
        origens += [a.iata for a in perfil.aeroportos_alternativos_origem if a.iata not in origens]
        destinos += [a.iata for a in perfil.aeroportos_alternativos_destino if a.iata not in destinos]
    return [(o, d) for o in origens for d in destinos]


def _como(opcoes: list[Opcao], trecho: str) -> list[Opcao]:
    for o in opcoes:
        o.trecho = trecho
        o.id = o.gerar_id()
    return opcoes


def _tentar(run: Path, fonte: str, rotulo: str, fn, trecho: str | None = None) -> int:
    try:
        ops = fn()
    except Exception as e:  # each source raises its own errors; here we only record them
        registrar_falha(run, fonte, f"{rotulo}: {e}")
        return 0
    if trecho:
        ops = _como(ops, trecho)
    return registrar_opcoes(run, fonte, ops)


def coletar_dinheiro(run: Path, fontes: tuple[str, ...] = ("google_flights", "kiwi")) -> dict:
    """Exact dates: outbound, return and round trip, for every route (including the profile's alternative airports).
    With a date window instead of exact dates there is nothing to do here: `coletar_datas` + `coletar_detalhes`
    cover it."""
    p = ler_pedido(run)
    if not pedido_de(p).datas_exatas():
        return {"skipped": "date window: use coletar datas + detalhes"}
    perfil = carregar_perfil()
    pax, cab, ida, volta = p["passageiros"], p.get("cabine", "economy"), p["data_ida"], p.get("data_volta")
    loc, kloc = _locais(p)
    resumo: dict[str, int] = {}
    for origem, destino in _rotas(p):
        r = f"{origem}-{destino}"
        if "google_flights" in fontes:
            n = _tentar(run, "google_flights", f"{r} ida {ida}",
                        lambda: google_flights.buscar_data(origem, destino, ida, None, pax, cab, **loc))
            if volta:
                n += _tentar(run, "google_flights", f"{r} volta {volta}",
                             lambda: google_flights.buscar_data(destino, origem, volta, None, pax, cab, **loc), trecho="volta")
                n += _tentar(run, "google_flights", f"{r} ida+volta",
                             lambda: google_flights.buscar_data(origem, destino, ida, volta, pax, cab, **loc))
            resumo[f"google_flights {r}"] = n
        if "kiwi" in fontes:
            bag = perfil.bagagem_despachada
            n = _tentar(run, "kiwi", f"{r} ida {ida}",
                        lambda: kiwi.buscar(origem, destino, ida, None, pax, 0, cab, bag, **kloc))
            if volta:
                n += _tentar(run, "kiwi", f"{r} volta {volta}",
                             lambda: kiwi.buscar(destino, origem, volta, None, pax, 0, cab, bag, **kloc), trecho="volta")
                n += _tentar(run, "kiwi", f"{r} ida+volta",
                             lambda: kiwi.buscar(origem, destino, ida, volta, pax, 0, cab, bag, **kloc))
            resumo[f"kiwi {r}"] = n
    return resumo


def _grade_ou_sweep(run: Path, origem: str, destino: str, ini: date, fim: date, pax: int, cab: str, trecho: str,
                    loc: dict, fonte: str = "google_flights") -> int:
    """Google calendar; if it fails, sweep date by date (slower, but uses the per-date search endpoint)."""
    try:
        ops = google_flights.grade(origem, destino, _iso(ini), _iso(fim), pax, cabine=cab, trecho=trecho, **loc)
        return registrar_opcoes(run, fonte, ops)
    except google_flights.LimiteGoogle as e:
        registrar_falha(run, fonte, str(e))  # a sweep would only make the rate limit worse
        return 0
    except Exception as e:
        registrar_falha(run, fonte, f"grade {origem}-{destino} {trecho}: {e}; usando sweep")
    n, d = 0, ini
    while d <= fim:
        n += _tentar(run, fonte, f"sweep {origem}-{destino} {d}",
                     lambda d=d: google_flights.buscar_data(origem, destino, _iso(d), None, pax, cab, **loc), trecho=trecho)
        d += timedelta(days=1)
    return n


def coletar_datas(run: Path, fontes: tuple[str, ...] = ("google_flights", "kiwi")) -> dict:
    """Date grid: one-way calendars for the outbound and return windows, and round-trip calendars for every
    allowed trip length. These prices have no specific flight: they only point at the dates worth detailing."""
    p = ler_pedido(run)
    pd = pedido_de(p)
    pax, cab, flex = p["passageiros"], p.get("cabine", "economy"), p["flex_dias"]
    loc, kloc = _locais(p)
    ida_ini, ida_fim = pd.janela_ida()
    janela_volta = pd.janela_volta()
    if pd.noites_min is not None:
        duracoes = list(range(pd.noites_min, (pd.noites_max or pd.noites_min) + 1))
    elif janela_volta:
        base = (date.fromisoformat(p["data_volta"]) - date.fromisoformat(p["data_ida"])).days
        duracoes = list(range(max(base - 2 * flex, 1), base + 2 * flex + 1))
    else:
        duracoes = []
    resumo: dict[str, int] = {}
    for origem, destino in _rotas(p, com_alternativos=False):
        r = f"{origem}-{destino}"
        if "google_flights" in fontes:
            n = _grade_ou_sweep(run, origem, destino, ida_ini, ida_fim, pax, cab, "ida", loc)
            if janela_volta:
                n += _grade_ou_sweep(run, destino, origem, *janela_volta, pax, cab, "volta", loc)
                for noites in duracoes:
                    n += _tentar(run, "google_flights", f"grade {r} ida+volta {noites} noites",
                                 lambda noites=noites: google_flights.grade(
                                     origem, destino, _iso(ida_ini), _iso(ida_fim), pax, noites=noites, cabine=cab, **loc))
            resumo[f"google_flights grade {r}"] = n
        if "kiwi" in fontes:
            # Kiwi returns a curated set (15 itineraries) for the whole window, with specific flights.
            if pd.datas_exatas():
                fn = lambda: kiwi.buscar(origem, destino, p["data_ida"], p.get("data_volta"), pax, min(flex, 10), cab, **kloc)  # noqa: E731
            else:
                noites = (min(duracoes), max(duracoes)) if duracoes else None
                fn = lambda: kiwi.buscar(origem, destino, _iso(ida_ini), None, pax, 0, cab, ida_ate=_iso(ida_fim),  # noqa: E731
                                         noites=noites, **kloc)
            resumo[f"kiwi flex {r}"] = _tentar(run, "kiwi", f"flex {r}", fn)
    return resumo


def programas_para_busca(perfil_bruto: dict) -> list[str] | None:
    """Miles programs worth querying for this user: those they have an account with, plus every transfer partner
    of their points programs. None = no preference, query every program."""
    from infra.programas import carregar

    reg = carregar()
    progs = [p for p, v in (perfil_bruto.get("programas") or {}).items() if (v or {}).get("tem_conta")]
    for pontos in perfil_bruto.get("pontos_programas") or []:
        progs += [par.destino for par in reg.parceiros_de(pontos)]
    progs = [p for p in dict.fromkeys(progs) if p in reg.milhas]
    return progs or None


def _milhas_janela(run: Path, p: dict, trecho: str, de: list[str], para: list[str], ini: date, fim: date,
                   programas: list[str] | None, rotulo: str) -> int:
    from fontes import seats

    try:
        ops, avisos = seats.buscar(de, para, _iso(ini), _iso(fim), passageiros=p["passageiros"],
                                   cabine=p.get("cabine", "economy"), trecho=trecho, programas=programas,
                                   moeda=p.get("moeda", "BRL"))
    except Exception as e:
        registrar_falha(run, "seats_aero", f"{rotulo}: {e}")
        return 0
    consultados = ", ".join(programas) if programas else "all programs (no filter)"
    com_resultado = ", ".join(sorted({o.programa for o in ops})) or "none"
    avisos.append(f"{rotulo}: programs queried: {consultados}; with award space: {com_resultado}")
    return registrar_opcoes(run, "seats_aero", ops, aviso="; ".join(avisos))


def coletar_milhas(run: Path) -> dict:
    """Awards via Seats.aero (Partner API with a key; otherwise the anonymous MCP) over the outbound and return windows."""
    from infra import perfil_io

    p = ler_pedido(run)
    pd = pedido_de(p)
    perfil = carregar_perfil()
    origens = list(dict.fromkeys(p["origens"] + [a.iata for a in perfil.aeroportos_alternativos_origem]))
    destinos = list(dict.fromkeys(p["destinos"] + [a.iata for a in perfil.aeroportos_alternativos_destino]))
    programas = programas_para_busca(perfil_io.carregar_bruto())
    resumo = {"seats_aero ida": _milhas_janela(run, p, "ida", origens, destinos, *pd.janela_ida(), programas, "ida")}
    if pd.janela_volta():
        resumo["seats_aero volta"] = _milhas_janela(run, p, "volta", destinos, origens, *pd.janela_volta(), programas, "volta")
    return resumo


def coletar_posicionamento(run: Path, max_hubs: int = MAX_HUBS) -> dict:
    """Separate tickets through a hub.
    1) Which airports of the country fly nonstop to the destination (fontes/rotas.py: busiest airports of the
       country × Kiwi nonstop check, plus Seats.aero tracked award routes). Those nonstop flights are stored as
       validated cash options, so the hub→destination legs don't need Google.
    2) For the cheapest hubs: positioning flights origin→hub (same day and the day before) and hub→origin on the
       way back (same day and the day after), from Kiwi and, when available, Google.
    3) Awards on those legs via Seats.aero."""
    from fontes import rotas
    from infra import perfil_io

    p = ler_pedido(run)
    pd = pedido_de(p)
    pax, cab = p["passageiros"], p.get("cabine", "economy")
    loc, kloc = _locais(p)
    origem, destino = p["origens"][0], p["destinos"][0]
    ida_ini, ida_fim = pd.janela_ida()
    volta = pd.janela_volta()
    centro_ida = _iso(ida_ini + (ida_fim - ida_ini) / 2)
    centro_volta = _iso(volta[0] + (volta[1] - volta[0]) / 2) if volta else None

    hubs, diretos = rotas.hubs_servidos(destino, p.get("pais", "BR"), centro_ida,
                                        excluir=set(p["origens"]) | set(p["destinos"]), moeda=p.get("moeda", "BRL"),
                                        pax=pax, data_volta=centro_volta, candidatos=p.get("hubs") or None)
    n = registrar_opcoes(run, "kiwi", diretos) if diretos else 0
    escolhidos = [h["iata"] for h in hubs if h["direto"]][:max_hubs]
    # The origin itself is not a hub, but say whether it has nonstop service too (so nobody reads "only GRU/GIG").
    origem_info, origem_ops = rotas.hubs_servidos(destino, p.get("pais", "BR"), centro_ida, excluir=set(),
                                                  moeda=p.get("moeda", "BRL"), pax=pax, data_volta=centro_volta,
                                                  candidatos=[origem])
    if origem_ops:
        n += registrar_opcoes(run, "kiwi", origem_ops)

    def datas_do_hub(trecho: str) -> list[str]:
        precos: dict[str, float] = {}
        for o in diretos:
            if o.trecho == trecho and (o.pernas[0].origem in escolhidos or o.pernas[-1].destino in escolhidos):
                precos[o.data_ida] = min(o.preco or 1e18, precos.get(o.data_ida, 1e18))
        return [d for d, _ in sorted(precos.items(), key=lambda x: x[1])[:2]]

    for d in datas_do_hub("ida"):
        for h in escolhidos:
            for dp in (d, _iso(date.fromisoformat(d) - timedelta(days=1))):
                n += _tentar(run, "kiwi", f"posicionamento {origem}-{h} {dp}",
                             lambda dp=dp, h=h: kiwi.buscar(origem, h, dp, None, pax, 0, cab, **kloc))
                n += _tentar(run, "posicionamento", f"{origem}-{h} {dp}",
                             lambda dp=dp, h=h: google_flights.buscar_data(origem, h, dp, None, pax, cab, **loc))
    for d in datas_do_hub("volta") if volta else []:
        for h in escolhidos:
            for dp in (d, _iso(date.fromisoformat(d) + timedelta(days=1))):
                n += _tentar(run, "kiwi", f"posicionamento {h}-{origem} {dp}",
                             lambda dp=dp, h=h: kiwi.buscar(h, origem, dp, None, pax, 0, cab, **kloc), trecho="volta")
                n += _tentar(run, "posicionamento", f"{h}-{origem} {dp}",
                             lambda dp=dp, h=h: google_flights.buscar_data(h, origem, dp, None, pax, cab, **loc),
                             trecho="volta")

    programas = programas_para_busca(perfil_io.carregar_bruto())
    if escolhidos:
        n += _milhas_janela(run, p, "ida", escolhidos, [destino], ida_ini, ida_fim, programas, "hubs→destino")
        n += _milhas_janela(run, p, "ida", [origem], escolhidos, ida_ini - timedelta(days=1), ida_fim, programas,
                            "origem→hubs")
        if volta:
            n += _milhas_janela(run, p, "volta", [destino], escolhidos, *volta, programas, "destino→hubs")
            n += _milhas_janela(run, p, "volta", escolhidos, [origem], volta[0], volta[1] + timedelta(days=1),
                                programas, "hubs→origem")
    return {"origem": origem_info[0] if origem_info else {"iata": origem, "direto": False},
            "hubs": hubs, "hubs_detalhados": escolhidos, "opcoes": n}


def _analisar_run(run: Path, somente_validadas: bool):
    import i18n
    from calculo.ranking import analisar
    from infra.cambio import padrao as cambio_padrao
    from infra.config import carregar_milheiro
    from infra.runs import aplicar_saldos, ler_saldos
    from normalizacao.schema import carregar_opcoes
    import json

    p = ler_pedido(run)
    pd = pedido_de(p)
    i18n.definir_moeda(pd.moeda)
    perfil = carregar_perfil()
    aplicar_saldos(perfil, ler_saldos(run))
    milheiro, _ = carregar_milheiro().na_moeda(pd.moeda, cambio_padrao())
    brutos = []
    for arq in sorted((run / "opcoes").glob("*.json")):
        brutos.extend(json.loads(arq.read_text(encoding="utf-8")))
    opcoes, _ = carregar_opcoes(brutos)
    return analisar(opcoes, pd, perfil, milheiro, hoje=date.today(), somente_validadas=somente_validadas)


def pendencias(run: Path, maximo: int = 4) -> dict:
    """What must be validated before recommending: unvalidated options that appear in combinations cheaper than
    the best fully validated one. `confirmar_milhas` → live check on the program's site; `detalhar` → per-date
    search for a specific flight."""
    validada = _analisar_run(run, somente_validadas=True)
    melhor = validada.ranking[0] if validada.ranking else None
    teto = melhor.custo if melhor else float("inf")
    tudo = _analisar_run(run, somente_validadas=False)
    confirmar, detalhar = [], []
    for c in tudo.ranking:
        if c.custo >= teto:
            break
        for o in c.opcoes:
            if o.validada:
                continue
            if o.tipo == "milhas" and o.id not in confirmar and len(confirmar) < maximo:
                confirmar.append(o.id)
            if o.tipo == "dinheiro":
                chave = {"origem": o.pernas[0].origem, "destino": o.pernas[-1].destino, "data": o.data_ida,
                         "volta": o.data_volta, "trecho": o.trecho}
                if chave not in detalhar and len(detalhar) < maximo:
                    detalhar.append(chave)
        if len(confirmar) >= maximo and len(detalhar) >= maximo:
            break
    return {
        "melhor_validada": None if melhor is None else {
            "custo": melhor.custo, "descricao": melhor.descricao(), "data_ida": melhor.data_ida,
            "data_volta": melhor.data_volta},
        "confirmar_milhas": confirmar,
        "detalhar": detalhar,
        "pronto": not confirmar and not detalhar,
    }


def coletar_detalhes(run: Path, itens: list[dict] | None = None) -> dict:
    """Per-date searches (specific flights) for the dates that `pendencias` says could win."""
    p = ler_pedido(run)
    pax, cab = p["passageiros"], p.get("cabine", "economy")
    loc, _ = _locais(p)
    itens = itens if itens is not None else pendencias(run, MAX_DETALHES)["detalhar"]
    n = 0
    for it in itens[:MAX_DETALHES]:
        if it["trecho"] == "ida_volta":
            n += _tentar(run, "google_flights", f"detalhe {it['origem']}-{it['destino']} {it['data']}→{it['volta']}",
                         lambda it=it: google_flights.buscar_data(it["origem"], it["destino"], it["data"], it["volta"],
                                                                  pax, cab, **loc))
        else:
            n += _tentar(run, "google_flights", f"detalhe {it['origem']}-{it['destino']} {it['data']}",
                         lambda it=it: google_flights.buscar_data(it["origem"], it["destino"], it["data"], None,
                                                                  pax, cab, **loc), trecho=it["trecho"])
    return {"detalhados": len(itens[:MAX_DETALHES]), "opcoes": n}
