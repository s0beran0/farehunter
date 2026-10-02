"""External source clients and the collectors used by the subagents."""

from __future__ import annotations

import json
from pathlib import Path


def _imprimir(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_coletar(a) -> int:
    from fontes import coleta

    run = Path(a.run)
    fontes = tuple(a.fontes) if a.fontes else ("google_flights", "kiwi")
    if a.tipo == "dinheiro":
        resumo = coleta.coletar_dinheiro(run, fontes)
    elif a.tipo == "datas":
        resumo = coleta.coletar_datas(run, fontes)
    else:
        resumo = coleta.coletar_milhas(run)
    from infra.runs import status

    _imprimir({"coletado": resumo, "status": status(run)})
    return 0


def _cmd_buscar(a) -> int:
    """Ad-hoc search (debugging/testing a source); prints summarized normalized options."""
    if a.fonte == "kiwi":
        from fontes import kiwi

        ops = kiwi.buscar(a.origem, a.destino, a.ida, a.volta, a.pax, moeda=a.moeda)
    elif a.fonte == "google":
        from fontes import google_flights

        ops = google_flights.buscar_data(a.origem, a.destino, a.ida, a.volta, a.pax, moeda=a.moeda, pais=a.pais)
    elif a.fonte == "google-grade":
        from fontes import google_flights

        ops = google_flights.grade(a.origem, a.destino, a.ida, a.ate or a.ida, a.pax, noites=a.noites, moeda=a.moeda,
                                   pais=a.pais)
    else:
        from fontes import seats

        ops, avisos = seats.buscar([a.origem], [a.destino], a.ida, a.ate or a.ida, a.pax, moeda=a.moeda,
                                   programas=a.programas)
    ops.sort(key=lambda o: o.preco if o.tipo == "dinheiro" else o.milhas)
    _imprimir([
        {"data": [p.data for p in o.pernas], "voos": [p.voos for p in o.pernas], "partida": o.pernas[0].partida,
         "preco": o.preco, "milhas": o.milhas, "taxas": o.taxas, "programa": o.programa}
        for o in ops[: a.limite]
    ])
    return 0


def registrar_comandos(sub) -> None:
    co = sub.add_parser("coletar", help="run the searches of one kind and write them into the run directory")
    co.add_argument("tipo", choices=["dinheiro", "datas", "milhas"])
    co.add_argument("--run", required=True)
    co.add_argument("--fontes", nargs="*", help="google_flights kiwi (default: both)")
    co.set_defaults(f=_cmd_coletar)

    bu = sub.add_parser("buscar", help="ad-hoc search in one source, for testing")
    bu.add_argument("fonte", choices=["kiwi", "google", "google-grade", "seats"])
    bu.add_argument("--origem", required=True)
    bu.add_argument("--destino", required=True)
    bu.add_argument("--ida", required=True)
    bu.add_argument("--volta")
    bu.add_argument("--ate", help="end of the window (grade/seats)")
    bu.add_argument("--noites", type=int)
    bu.add_argument("--pax", type=int, default=1)
    bu.add_argument("--limite", type=int, default=10)
    bu.add_argument("--moeda", default="BRL", help="ISO 4217 currency")
    bu.add_argument("--pais", default="BR", help="ISO 3166 country (point of sale)")
    bu.add_argument("--programas", nargs="*", help="miles program ids (seats only; default: all)")
    bu.set_defaults(f=_cmd_buscar)

    _registrar_promos(sub)


def _cmd_promos(a) -> int:
    from fontes.promos import RASTREADORES_BONUS, ler_feeds, regioes_para
    from infra import perfil_io

    regioes = a.regiao or regioes_para(perfil_io.carregar_bruto().get("pais"))
    itens, falhas = ler_feeds(regioes)
    if a.programa:
        itens = [i for i in itens if a.programa in i["programas"]]
    _imprimir({"regioes": regioes, "itens": itens[: a.limite], "falhas": falhas,
               "rastreadores_de_bonus": RASTREADORES_BONUS if set(regioes) - {"br"} else []})
    return 0


def _registrar_promos(sub) -> None:
    pr = sub.add_parser("promos", help="recent miles promotions read from RSS feeds (24h cache)")
    pr.add_argument("--programa")
    pr.add_argument("--limite", type=int, default=30)
    pr.add_argument("--regiao", nargs="*", choices=["br", "us", "uk", "au", "ca"],
                    help="feed regions (default: from the profile's country)")
    pr.set_defaults(f=_cmd_promos)
