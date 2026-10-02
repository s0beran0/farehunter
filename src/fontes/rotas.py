"""Which airports actually serve a destination, so the hub search never wastes calls on airports without flights.

1. Airports of a country, busiest first: Seats.aero MCP `search_airports` (country + order_by=traffic, no key).
   Falls back to config/hubs.yaml when offline.
2. Nonstop service hub→destination: one Kiwi search per airport with `max_sector_stopovers=0`, in parallel.
   The results are real flights with prices, so they are also stored as cash options.
3. Kiwi doesn't sell every airline (e.g. LATAM), so Seats.aero `list_routes(origin, destination)` is used as a
   second signal: a tracked award route keeps the airport as a candidate (it may involve a connection).
Results are cached (airports 30 days, routes 7 days): routes change slowly.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from fontes import kiwi
from fontes.mcp_http import chamar_tool, json_do_resultado
from infra.cache import Cache, chave_busca
from infra.config import MODELOS_DIR, carregar_yaml
from normalizacao.schema import Opcao

URL_SEATS = "https://seats.aero/mcp"
TTL_AEROPORTOS_H = 30 * 24
TTL_ROTAS_H = 7 * 24
MIN_VOOS_SEMANAIS = 50  # ignore small airports when picking gateway candidates


def aeroportos_do_pais(pais: str, limite: int = 15, cache: Cache | None = None) -> list[dict]:
    """[{iata, nome, voos_semanais}] for the country's busiest airports."""
    cache = cache or Cache()
    chave = chave_busca("aeroportos", pais, limite)
    if (hit := cache.get("rotas", chave, ttl_horas=TTL_AEROPORTOS_H)) is not None:
        return hit
    try:
        dados = json_do_resultado(chamar_tool(URL_SEATS, "search_airports",
                                              {"country": pais, "order_by": "traffic", "limit": limite}))
        lista = [{"iata": a["iata"], "nome": a.get("name", ""), "voos_semanais": a.get("avg_weekly_flights") or 0}
                 for a in dados.get("airports") or [] if a.get("iata")]
    except Exception:
        lista = []
    if not lista:  # offline / tool changed: static list
        lista = [{"iata": h, "nome": "", "voos_semanais": None}
                 for h in (carregar_yaml(MODELOS_DIR / "hubs.yaml").get(pais.upper()) or [])]
    else:
        cache.set("rotas", chave, lista)
    return lista


def _direto_kiwi(hub: str, destino: str, data: str, moeda: str, pax: int, trecho: str) -> tuple[list[Opcao], str | None]:
    origem, chegada = (hub, destino) if trecho == "ida" else (destino, hub)
    try:
        ops = kiwi.buscar(origem, chegada, data, None, pax, 3, moeda=moeda, idioma="en", sem_escalas=True)
    except Exception as e:
        return [], str(e)
    for o in ops:
        o.trecho = trecho
        o.id = o.gerar_id()
    return ops, None


def _rota_seats(hub: str, destino: str, cache: Cache) -> list[str]:
    chave = chave_busca("list_routes", hub, destino)
    if (hit := cache.get("rotas", chave, ttl_horas=TTL_ROTAS_H)) is not None:
        return hit
    try:
        dados = json_do_resultado(chamar_tool(URL_SEATS, "list_routes", {"origin": hub, "destination": destino}))
        progs = sorted({r.get("mileage_program") for r in dados.get("routes") or [] if r.get("mileage_program")})
    except Exception:
        return []
    cache.set("rotas", chave, progs)
    return progs


def hubs_servidos(destino: str, pais: str, data: str, excluir: set[str], moeda: str = "BRL", pax: int = 1,
                  data_volta: str | None = None, candidatos: list[str] | None = None,
                  cache: Cache | None = None) -> tuple[list[dict], list[Opcao]]:
    """Gateway airports with service to `destino`, cheapest first, plus the nonstop flights found (cash options).
    Each hub: {iata, direto, cias, preco_min, programas_resgate, voos_semanais}."""
    cache = cache or Cache()
    if candidatos is None:
        aeroportos = [a for a in aeroportos_do_pais(pais) if a["iata"] not in excluir
                      and (a["voos_semanais"] is None or a["voos_semanais"] >= MIN_VOOS_SEMANAIS)]
    else:
        aeroportos = [{"iata": h, "nome": "", "voos_semanais": None} for h in candidatos if h not in excluir]

    def checar(a: dict):
        ida, erro = _direto_kiwi(a["iata"], destino, data, moeda, pax, "ida")
        volta = _direto_kiwi(a["iata"], destino, data_volta, moeda, pax, "volta")[0] if (data_volta and ida) else []
        return a, ida, volta, erro, _rota_seats(a["iata"], destino, cache)

    hubs, opcoes = [], []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for a, ida, volta, erro, progs in ex.map(checar, aeroportos):
            if not ida and not progs:
                continue
            opcoes += ida + volta
            hubs.append({
                "iata": a["iata"], "direto": bool(ida),
                "cias": sorted({p.cia for o in ida for p in o.pernas if p.cia}),
                "preco_min": min((o.preco for o in ida if o.preco is not None), default=None),
                "programas_resgate": progs, "voos_semanais": a["voos_semanais"],
                "obs": erro or ("" if ida else "no nonstop found on Kiwi; award route tracked (may connect)"),
            })
    hubs.sort(key=lambda h: (not h["direto"], h["preco_min"] if h["preco_min"] is not None else float("inf")))
    return hubs, opcoes

