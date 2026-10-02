"""Clientes das fontes externas e coletas usadas pelos subagentes."""

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
    """Busca avulsa (debug/teste de fonte), imprime opções normalizadas resumidas."""
    if a.fonte == "kiwi":
        from fontes import kiwi

        ops = kiwi.buscar(a.origem, a.destino, a.ida, a.volta, a.pax)
    elif a.fonte == "google":
        from fontes import google_flights

        ops = google_flights.buscar_data(a.origem, a.destino, a.ida, a.volta, a.pax)
    elif a.fonte == "google-grade":
        from fontes import google_flights

        ops = google_flights.grade(a.origem, a.destino, a.ida, a.ate or a.ida, a.pax, noites=a.noites)
    else:
        from fontes import seats

        ops, avisos = seats.buscar([a.origem], [a.destino], a.ida, a.ate or a.ida, a.pax)
    ops.sort(key=lambda o: o.preco_brl if o.tipo == "dinheiro" else o.milhas)
    _imprimir([
        {"data": [p.data for p in o.pernas], "voos": [p.voos for p in o.pernas], "partida": o.pernas[0].partida,
         "preco_brl": o.preco_brl, "milhas": o.milhas, "taxas_brl": o.taxas_brl, "programa": o.programa}
        for o in ops[: a.limite]
    ])
    return 0


def registrar_comandos(sub) -> None:
    co = sub.add_parser("coletar", help="roda as buscas de um tipo e grava no diretório da execução")
    co.add_argument("tipo", choices=["dinheiro", "datas", "milhas"])
    co.add_argument("--run", required=True)
    co.add_argument("--fontes", nargs="*", help="google_flights kiwi (padrão: ambas)")
    co.set_defaults(f=_cmd_coletar)

    bu = sub.add_parser("buscar", help="busca avulsa numa fonte, para testar")
    bu.add_argument("fonte", choices=["kiwi", "google", "google-grade", "seats"])
    bu.add_argument("--origem", required=True)
    bu.add_argument("--destino", required=True)
    bu.add_argument("--ida", required=True)
    bu.add_argument("--volta")
    bu.add_argument("--ate", help="fim da janela (grade/seats)")
    bu.add_argument("--noites", type=int)
    bu.add_argument("--pax", type=int, default=1)
    bu.add_argument("--limite", type=int, default=10)
    bu.set_defaults(f=_cmd_buscar)

    _registrar_promos(sub)


def _cmd_promos(a) -> int:
    from fontes.promos import ler_feeds

    itens, falhas = ler_feeds()
    if a.programa:
        itens = [i for i in itens if a.programa in i["programas"]]
    _imprimir({"itens": itens[: a.limite], "falhas": falhas})
    return 0


def _registrar_promos(sub) -> None:
    pr = sub.add_parser("promos", help="promoções recentes de milhas lidas dos feeds RSS (cache 24h)")
    pr.add_argument("--programa")
    pr.add_argument("--limite", type=int, default=30)
    pr.set_defaults(f=_cmd_promos)
