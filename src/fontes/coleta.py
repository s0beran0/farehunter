"""Deterministic collectors used by the subagents: they run the searches and write into the run directory.

Each collector catches failures per source/call and records them in status.json (graceful degradation):
a broken source never blocks the others.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fontes import google_flights, kiwi
from infra.config import carregar_perfil
from infra.runs import ler_pedido, registrar_falha, registrar_opcoes
from normalizacao.schema import Opcao


def _locais(p: dict) -> tuple[dict, dict]:
    """Currency/point-of-sale kwargs for Google Flights and Kiwi, taken from the request."""
    moeda, pais = p.get("moeda", "BRL"), p.get("pais", "BR")
    return {"moeda": moeda, "pais": pais}, {"moeda": moeda, "idioma": p.get("idioma", "en")}


def _iso(d: date) -> str:
    return d.isoformat()


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
    """Exact dates: outbound, return and round trip, for every route (including the profile's alternative airports)."""
    p = ler_pedido(run)
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


def _grade_ou_sweep(run: Path, origem: str, destino: str, centro: date, flex: int, pax: int, cab: str, trecho: str,
                    loc: dict) -> int:
    """Google calendar; if it fails, sweep date by date (slower, but uses the per-date search endpoint)."""
    ini, fim = _iso(centro - timedelta(flex)), _iso(centro + timedelta(flex))
    try:
        ops = google_flights.grade(origem, destino, ini, fim, pax, cabine=cab, trecho=trecho, **loc)
        return registrar_opcoes(run, "google_flights", ops)
    except Exception as e:
        registrar_falha(run, "google_flights", f"grade {origem}-{destino} {trecho}: {e}; usando sweep")
    n = 0
    for i in range(-flex, flex + 1):
        d = _iso(centro + timedelta(i))
        n += _tentar(run, "google_flights", f"sweep {origem}-{destino} {d}",
                     lambda d=d: google_flights.buscar_data(origem, destino, d, None, pax, cab, **loc), trecho=trecho)
    return n


def coletar_datas(run: Path, fontes: tuple[str, ...] = ("google_flights", "kiwi")) -> dict:
    """±N-day grid: one-way calendar (outbound and return separately) and round trip for every possible trip length."""
    p = ler_pedido(run)
    pax, cab, flex = p["passageiros"], p.get("cabine", "economy"), p["flex_dias"]
    loc, kloc = _locais(p)
    ida = date.fromisoformat(p["data_ida"])
    volta = date.fromisoformat(p["data_volta"]) if p.get("data_volta") else None
    resumo: dict[str, int] = {}
    for origem, destino in _rotas(p, com_alternativos=False):
        r = f"{origem}-{destino}"
        if "google_flights" in fontes:
            n = _grade_ou_sweep(run, origem, destino, ida, flex, pax, cab, "ida", loc)
            if volta:
                n += _grade_ou_sweep(run, destino, origem, volta, flex, pax, cab, "volta", loc)
                base = (volta - ida).days
                for noites in range(max(base - 2 * flex, 1), base + 2 * flex + 1):
                    n += _tentar(run, "google_flights", f"grade {r} ida+volta {noites} noites",
                                 lambda noites=noites: google_flights.grade(
                                     origem, destino, _iso(ida - timedelta(flex)), _iso(ida + timedelta(flex)), pax,
                                     noites=noites, cabine=cab, **loc))
            resumo[f"google_flights grade {r}"] = n
        if "kiwi" in fontes:
            # Kiwi accepts up to ±10 flex days and returns a curated set (15 itineraries) for the whole window.
            n = _tentar(run, "kiwi", f"flex {r}",
                        lambda: kiwi.buscar(origem, destino, p["data_ida"], p.get("data_volta"), pax, min(flex, 10), cab, **kloc))
            resumo[f"kiwi flex {r}"] = n
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


def coletar_milhas(run: Path) -> dict:
    """Awards via Seats.aero (Partner API with a key; otherwise the anonymous MCP), ±N window on outbound and return."""
    from fontes import seats

    p = ler_pedido(run)
    pax, cab, flex = p["passageiros"], p.get("cabine", "economy"), p["flex_dias"]
    perfil = carregar_perfil()
    origens = list(dict.fromkeys(p["origens"] + [a.iata for a in perfil.aeroportos_alternativos_origem]))
    destinos = list(dict.fromkeys(p["destinos"] + [a.iata for a in perfil.aeroportos_alternativos_destino]))
    from infra import perfil_io

    programas = programas_para_busca(perfil_io.carregar_bruto())
    janelas = [("ida", origens, destinos, date.fromisoformat(p["data_ida"]))]
    if p.get("data_volta"):
        janelas.append(("volta", destinos, origens, date.fromisoformat(p["data_volta"])))
    resumo = {}
    for trecho, de, para, centro in janelas:
        try:
            ops, avisos = seats.buscar(de, para, _iso(centro - timedelta(flex)), _iso(centro + timedelta(flex)),
                                       passageiros=pax, cabine=cab, trecho=trecho, programas=programas,
                                       moeda=p.get("moeda", "BRL"))
        except Exception as e:
            registrar_falha(run, "seats_aero", f"{trecho}: {e}")
            resumo[f"seats_aero {trecho}"] = 0
            continue
        consultados = ", ".join(programas) if programas else "all programs (no filter)"
        com_resultado = ", ".join(sorted({o.programa for o in ops})) or "none"
        avisos.append(f"{trecho}: programs queried: {consultados}; with award space: {com_resultado}")
        resumo[f"seats_aero {trecho}"] = registrar_opcoes(run, "seats_aero", ops, aviso="; ".join(avisos))
    return resumo
