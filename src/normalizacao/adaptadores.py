"""Adaptadores fonte → schema, para respostas brutas salvas em arquivo (ex.: saída de uma tool MCP chamada pelo modelo).

As coletas automáticas (fontes/coleta.py) já normalizam; isto serve para o caminho manual/interativo.
"""

from __future__ import annotations

from normalizacao.schema import Opcao


def _kiwi(bruto, trecho, passageiros):
    from fontes.kiwi import normalizar

    return normalizar(bruto, passageiros)


def _seats_mcp(bruto, trecho, passageiros):
    from fontes.seats import normalizar_mcp

    return normalizar_mcp(bruto, trecho or "ida")


def _seats_api(bruto, trecho, passageiros):
    from mcp_seats.cliente import normalizar_search

    registros = bruto.get("data", bruto) if isinstance(bruto, dict) else bruto
    return normalizar_search(registros, trecho=trecho or "ida", passageiros=passageiros)


ADAPTADORES = {"kiwi": _kiwi, "seats_aero_mcp": _seats_mcp, "seats_aero_api": _seats_api}


def normalizar(fonte: str, bruto, trecho: str | None = None, passageiros: int = 1) -> list[Opcao]:
    if fonte not in ADAPTADORES:
        raise SystemExit(f"fonte sem adaptador: {fonte}. Opções: {', '.join(ADAPTADORES)}")
    if isinstance(bruto, dict) and "result" in bruto:  # resposta JSON-RPC completa
        from fontes.mcp_http import json_do_resultado

        bruto = json_do_resultado(bruto["result"])
    opcoes = ADAPTADORES[fonte](bruto, trecho, passageiros)
    if trecho:
        for o in opcoes:
            if o.trecho != "ida_volta":
                o.trecho = trecho
                o.id = o.gerar_id()
    return opcoes
