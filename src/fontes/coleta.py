"""Coletas determinísticas usadas pelos subagentes: rodam as buscas e gravam no diretório da execução.

Cada coleta captura falhas por fonte/chamada e registra no status.json (degradação graciosa):
uma fonte quebrada não impede as outras.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fontes import google_flights, kiwi
from infra.config import carregar_perfil
from infra.runs import ler_pedido, registrar_falha, registrar_opcoes
from normalizacao.schema import Opcao


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
    except Exception as e:  # cada fonte levanta seus erros; aqui só registramos
        registrar_falha(run, fonte, f"{rotulo}: {e}")
        return 0
    if trecho:
        ops = _como(ops, trecho)
    return registrar_opcoes(run, fonte, ops)


def coletar_dinheiro(run: Path, fontes: tuple[str, ...] = ("google_flights", "kiwi")) -> dict:
    """Data exata: ida, volta e ida+volta, para cada rota (incluindo aeroportos alternativos do perfil)."""
    p = ler_pedido(run)
    perfil = carregar_perfil()
    pax, cab, ida, volta = p["passageiros"], p.get("cabine", "economy"), p["data_ida"], p.get("data_volta")
    resumo: dict[str, int] = {}
    for origem, destino in _rotas(p):
        r = f"{origem}-{destino}"
        if "google_flights" in fontes:
            n = _tentar(run, "google_flights", f"{r} ida {ida}",
                        lambda: google_flights.buscar_data(origem, destino, ida, None, pax, cab))
            if volta:
                n += _tentar(run, "google_flights", f"{r} volta {volta}",
                             lambda: google_flights.buscar_data(destino, origem, volta, None, pax, cab), trecho="volta")
                n += _tentar(run, "google_flights", f"{r} ida+volta",
                             lambda: google_flights.buscar_data(origem, destino, ida, volta, pax, cab))
            resumo[f"google_flights {r}"] = n
        if "kiwi" in fontes:
            bag = perfil.bagagem_despachada
            n = _tentar(run, "kiwi", f"{r} ida {ida}",
                        lambda: kiwi.buscar(origem, destino, ida, None, pax, 0, cab, bag))
            if volta:
                n += _tentar(run, "kiwi", f"{r} volta {volta}",
                             lambda: kiwi.buscar(destino, origem, volta, None, pax, 0, cab, bag), trecho="volta")
                n += _tentar(run, "kiwi", f"{r} ida+volta",
                             lambda: kiwi.buscar(origem, destino, ida, volta, pax, 0, cab, bag))
            resumo[f"kiwi {r}"] = n
    return resumo


def _grade_ou_sweep(run: Path, origem: str, destino: str, centro: date, flex: int, pax: int, cab: str, trecho: str) -> int:
    """Calendário do Google; se falhar, varre data a data (mais lento, mas usa o endpoint de busca por data)."""
    ini, fim = _iso(centro - timedelta(flex)), _iso(centro + timedelta(flex))
    try:
        ops = google_flights.grade(origem, destino, ini, fim, pax, cabine=cab, trecho=trecho)
        return registrar_opcoes(run, "google_flights", ops)
    except Exception as e:
        registrar_falha(run, "google_flights", f"grade {origem}-{destino} {trecho}: {e}; usando sweep")
    n = 0
    for i in range(-flex, flex + 1):
        d = _iso(centro + timedelta(i))
        n += _tentar(run, "google_flights", f"sweep {origem}-{destino} {d}",
                     lambda d=d: google_flights.buscar_data(origem, destino, d, None, pax, cab), trecho=trecho)
    return n


def coletar_datas(run: Path, fontes: tuple[str, ...] = ("google_flights", "kiwi")) -> dict:
    """Grade ±N dias: calendário só ida (ida e volta separados) e ida+volta para cada duração possível."""
    p = ler_pedido(run)
    pax, cab, flex = p["passageiros"], p.get("cabine", "economy"), p["flex_dias"]
    ida = date.fromisoformat(p["data_ida"])
    volta = date.fromisoformat(p["data_volta"]) if p.get("data_volta") else None
    resumo: dict[str, int] = {}
    for origem, destino in _rotas(p, com_alternativos=False):
        r = f"{origem}-{destino}"
        if "google_flights" in fontes:
            n = _grade_ou_sweep(run, origem, destino, ida, flex, pax, cab, "ida")
            if volta:
                n += _grade_ou_sweep(run, destino, origem, volta, flex, pax, cab, "volta")
                base = (volta - ida).days
                for noites in range(max(base - 2 * flex, 1), base + 2 * flex + 1):
                    n += _tentar(run, "google_flights", f"grade {r} ida+volta {noites} noites",
                                 lambda noites=noites: google_flights.grade(
                                     origem, destino, _iso(ida - timedelta(flex)), _iso(ida + timedelta(flex)), pax,
                                     noites=noites, cabine=cab))
            resumo[f"google_flights grade {r}"] = n
        if "kiwi" in fontes:
            # Kiwi aceita flex de até ±10 dias e devolve um conjunto curado (15 itinerários) da janela inteira.
            n = _tentar(run, "kiwi", f"flex {r}",
                        lambda: kiwi.buscar(origem, destino, p["data_ida"], p.get("data_volta"), pax, min(flex, 10), cab))
            resumo[f"kiwi flex {r}"] = n
    return resumo


def coletar_milhas(run: Path) -> dict:
    """Smiles e Azul via Seats.aero (Partner API se houver chave; senão MCP anônimo), janela ±N na ida e na volta."""
    from fontes import seats

    p = ler_pedido(run)
    pax, cab, flex = p["passageiros"], p.get("cabine", "economy"), p["flex_dias"]
    perfil = carregar_perfil()
    origens = list(dict.fromkeys(p["origens"] + [a.iata for a in perfil.aeroportos_alternativos_origem]))
    destinos = list(dict.fromkeys(p["destinos"] + [a.iata for a in perfil.aeroportos_alternativos_destino]))
    janelas = [("ida", origens, destinos, date.fromisoformat(p["data_ida"]))]
    if p.get("data_volta"):
        janelas.append(("volta", destinos, origens, date.fromisoformat(p["data_volta"])))
    resumo = {}
    for trecho, de, para, centro in janelas:
        try:
            ops, avisos = seats.buscar(de, para, _iso(centro - timedelta(flex)), _iso(centro + timedelta(flex)),
                                       passageiros=pax, cabine=cab, trecho=trecho)
        except Exception as e:
            registrar_falha(run, "seats_aero", f"{trecho}: {e}")
            resumo[f"seats_aero {trecho}"] = 0
            continue
        resumo[f"seats_aero {trecho}"] = registrar_opcoes(run, "seats_aero", ops, aviso="; ".join(avisos))
    return resumo
