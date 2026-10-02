"""Kiwi.com MCP (https://mcp.kiwi.com), called directly via JSON-RPC over HTTP.

The server is also in .mcp.json for interactive use. For the agent flow, calling it from here is cheaper:
the response (~20 KB per search) goes straight to the normalizer without passing through the model's context.
Validated 2026-10-02: tool `search-flight`, dates dd/mm/yyyy, any `currency`, no session needed (docs/research.md).
"""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx

from fontes.mcp_http import ErroMCP, chamar_tool, json_do_resultado

from infra.cache import Cache, chave_busca
from normalizacao.schema import Opcao, Perna

URL = "https://mcp.kiwi.com"
FONTE = "kiwi"
CABINES = {"economy": "M", "premium": "W", "business": "C", "first": "F"}


class FonteIndisponivel(RuntimeError):
    pass


def _dmy(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def chamar_search_flight(argumentos: dict, http: httpx.Client | None = None) -> dict:
    return json_do_resultado(chamar_tool(URL, "search-flight", argumentos, http))


def buscar(
    origem: str, destino: str, ida: str, volta: str | None = None, passageiros: int = 1, flex_dias: int = 0,
    cabine: str = "economy", bagagem_despachada: bool = False, cache: Cache | None = None,
    http: httpx.Client | None = None, moeda: str = "BRL", idioma: str = "en",
) -> list[Opcao]:
    cache = cache or Cache()
    chave = chave_busca(origem, destino, ida, volta, passageiros, flex_dias, cabine, bagagem_despachada, moeda)
    if (hit := cache.get(FONTE, chave)) is not None:
        return normalizar(hit, passageiros)

    args = {
        "flyFrom": origem, "flyTo": destino, "departureDate": _dmy(ida),
        "adults": passageiros, "cabinClass": CABINES[cabine], "currency": moeda.upper(), "locale": idioma,
    }
    if flex_dias:
        args["departureDateFlexDays"] = flex_dias
    if volta:
        args["returnDate"] = _dmy(volta)
        if flex_dias:
            args["returnDateFlexDays"] = flex_dias
    if bagagem_despachada:
        args["adults_hold_bags"] = [1] * passageiros
    try:
        bruto = chamar_search_flight(args, http)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ErroMCP) as e:
        raise FonteIndisponivel(f"kiwi: {type(e).__name__}: {e}") from e
    if bruto.get("error"):
        raise FonteIndisponivel(f"kiwi: {bruto['error']}")
    cache.set(FONTE, chave, bruto)
    return normalizar(bruto, passageiros)


def _perna(trecho: dict) -> Perna:
    segs = trecho.get("segments") or []
    partida = datetime.fromisoformat(trecho["departureTime"])
    chegada = datetime.fromisoformat(trecho["arrivalTime"])
    escalas = [
        int((datetime.fromisoformat(b["departureTime"]) - datetime.fromisoformat(a["arrivalTime"])).total_seconds() // 60)
        for a, b in zip(segs, segs[1:])
    ]
    return Perna(
        origem=trecho["from"], destino=trecho["to"], data=partida.date().isoformat(),
        partida=partida.strftime("%H:%M"), chegada=chegada.strftime("%H:%M"),
        cia=(segs[0].get("carrier") if segs else None),
        voos=[s["flightNumber"] for s in segs if s.get("flightNumber")],
        conexoes=int(trecho.get("stops") or max(len(segs) - 1, 0)),
        duracao_min=int(trecho.get("durationSeconds", 0) // 60) or None,
        escalas_min=escalas,
    )


def normalizar(bruto: dict, passageiros: int | None = None) -> list[Opcao]:
    """Convert the `search-flight` response (total price for the search) into options with per-passenger prices."""
    pax = passageiros or sum((bruto.get("passengers") or {}).get(k, 0) for k in ("adults", "children")) or 1
    opcoes = []
    for it in bruto.get("itineraries") or []:
        pernas = [_perna(it["outbound"])]
        if it.get("inbound"):
            pernas.append(_perna(it["inbound"]))
        obs = []
        cias_ida = {s.get("carrier") for s in it["outbound"].get("segments", [])}
        if len(cias_ida) > 1:
            obs.append("Kiwi combina cias diferentes (pode ser bilhete separado / self-transfer)")
        opcoes.append(Opcao(
            fonte=FONTE, tipo="dinheiro", trecho="ida_volta" if len(pernas) == 2 else "ida", pernas=pernas,
            preco=round(float(it["price"]) / pax, 2),
            bagagem_inclusa=bool((it.get("baggage") or {}).get("checkedBag")),
            link=it.get("bookingUrl"), observacoes=obs,
        ))
    return opcoes
