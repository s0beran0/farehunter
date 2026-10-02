"""Google Flights via `fli` (PyPI package `flights`, pinned version). Validated 2026-10-02 (docs/research.md).

- `buscar_data`: flights on one date (one way or round trip), with airline, flight number and times.
- `grade`: lowest price per date (calendar). One way, or round trip with a fixed number of nights.

fli's price is the TOTAL for all passengers; here it becomes a per-passenger price.
The endpoints are fragile (Google changed request signing in Aug 2026). Failures raise `FonteIndisponivel`
and the subagent records the source as unavailable.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from infra.cache import Cache, chave_busca
from normalizacao.schema import Opcao, Perna

IDIOMA_GOOGLE = {"pt": "pt-BR", "en": "en", "es": "es"}


def _loc(moeda: str, pais: str, idioma: str = "en") -> dict:
    """Locale for Google: currency of the prices and point of sale (country)."""
    return dict(currency=moeda.upper(), language=IDIOMA_GOOGLE.get(idioma, "en"), country=pais.upper())
FONTE = "google_flights"


class FonteIndisponivel(RuntimeError):
    pass


def link_google(origem: str, destino: str, ida: str, volta: str | None = None, moeda: str = "BRL",
                pais: str = "BR") -> str:
    q = f"Flights to {destino} from {origem} on {ida}" + (f" through {volta}" if volta else " oneway")
    return f"https://www.google.com/travel/flights?q={quote(q)}&curr={moeda.upper()}&gl={pais.upper()}"


def _fli():
    try:
        from fli import models, search
    except ImportError as e:  # pragma: no cover
        raise FonteIndisponivel(f"fli not installed: {e}") from e
    return models, search


def _aeroporto(models, iata: str):
    try:
        return models.Airport[iata.upper()]
    except KeyError as e:
        raise FonteIndisponivel(f"aeroporto {iata} desconhecido pelo fli") from e


def _cabine(models, cabine: str):
    return {
        "economy": models.SeatType.ECONOMY,
        "premium": models.SeatType.PREMIUM_ECONOMY,
        "business": models.SeatType.BUSINESS,
        "first": models.SeatType.FIRST,
    }[cabine]


def _perna(resultado) -> Perna:
    legs = resultado.legs
    escalas = []
    for a, b in zip(legs, legs[1:]):
        escalas.append(int((b.departure_datetime - a.arrival_datetime).total_seconds() // 60))
    return Perna(
        origem=legs[0].departure_airport.name,
        destino=legs[-1].arrival_airport.name,
        data=legs[0].departure_datetime.date().isoformat(),
        partida=legs[0].departure_datetime.strftime("%H:%M"),
        chegada=legs[-1].arrival_datetime.strftime("%H:%M"),
        cia=legs[0].airline.name,
        voos=[f"{l.airline.name} {l.flight_number}" for l in legs],
        conexoes=len(legs) - 1,
        duracao_min=resultado.duration,
        escalas_min=escalas,
    )


def buscar_data(
    origem: str, destino: str, ida: str, volta: str | None = None, passageiros: int = 1,
    cabine: str = "economy", max_resultados: int = 40, cache: Cache | None = None,
    moeda: str = "BRL", pais: str = "BR",
) -> list[Opcao]:
    cache = cache or Cache()
    chave = chave_busca("data", origem, destino, ida, volta, passageiros, cabine, moeda, pais)
    loc = _loc(moeda, pais)
    if (hit := cache.get(FONTE, chave)) is not None:
        return [Opcao.from_dict(d) for d in hit]

    models, search = _fli()
    seg_ida = models.FlightSegment(
        departure_airport=[[_aeroporto(models, origem), 0]], arrival_airport=[[_aeroporto(models, destino), 0]],
        travel_date=ida,
    )
    segs = [seg_ida]
    if volta:
        segs.append(models.FlightSegment(
            departure_airport=[[_aeroporto(models, destino), 0]], arrival_airport=[[_aeroporto(models, origem), 0]],
            travel_date=volta,
        ))
    filtros = models.FlightSearchFilters(
        trip_type=models.TripType.ROUND_TRIP if volta else models.TripType.ONE_WAY,
        passenger_info=models.PassengerInfo(adults=passageiros),
        flight_segments=segs,
        seat_type=_cabine(models, cabine),
        stops=models.MaxStops.ANY,
        sort_by=models.SortBy.CHEAPEST,
    )
    try:
        if volta:
            brutos = search.SearchFlights().search(filtros, top_n=5, **loc) or []
        else:
            brutos = search.SearchFlights().search(filtros, **loc) or []
    except Exception as e:  # fli raises several exception types when it breaks
        raise FonteIndisponivel(f"fli falhou na busca por data: {type(e).__name__}: {e}") from e
    if not brutos:
        raise FonteIndisponivel("fli returned an empty list (Google may be blocking)")

    link = link_google(origem, destino, ida, volta, moeda, pais)
    opcoes = []
    for r in brutos[: max_resultados]:
        if volta:
            ida_r, volta_r = r
            pernas, preco, trecho = [_perna(ida_r), _perna(volta_r)], ida_r.price, "ida_volta"
        else:
            pernas, preco, trecho = [_perna(r)], r.price, "ida"
        opcoes.append(Opcao(
            fonte=FONTE, tipo="dinheiro", trecho=trecho, pernas=pernas,
            preco=round(preco / passageiros, 2), link=link,
        ))
    cache.set(FONTE, chave, [o.to_dict() for o in opcoes])
    return opcoes


def grade(
    origem: str, destino: str, inicio: str, fim: str, passageiros: int = 1, noites: int | None = None,
    cabine: str = "economy", trecho: str = "ida", cache: Cache | None = None,
    moeda: str = "BRL", pais: str = "BR",
) -> list[Opcao]:
    """Lowest price per departure date in [inicio, fim]. With `noites`, a round trip of that length."""
    cache = cache or Cache()
    chave = chave_busca("grade", origem, destino, inicio, fim, passageiros, noites, cabine, trecho, moeda, pais)
    if (hit := cache.get(FONTE, chave)) is not None:
        return [Opcao.from_dict(d) for d in hit]

    models, search = _fli()
    segs = [models.FlightSegment(
        departure_airport=[[_aeroporto(models, origem), 0]], arrival_airport=[[_aeroporto(models, destino), 0]],
        travel_date=inicio,
    )]
    if noites is not None:
        volta0 = (date.fromisoformat(inicio) + timedelta(days=noites)).isoformat()
        segs.append(models.FlightSegment(
            departure_airport=[[_aeroporto(models, destino), 0]], arrival_airport=[[_aeroporto(models, origem), 0]],
            travel_date=volta0,
        ))
    kwargs = dict(
        trip_type=models.TripType.ROUND_TRIP if noites is not None else models.TripType.ONE_WAY,
        passenger_info=models.PassengerInfo(adults=passageiros),
        flight_segments=segs,
        seat_type=_cabine(models, cabine),
        from_date=inicio,
        to_date=fim,
    )
    if noites is not None:
        kwargs["duration"] = noites
    try:
        dias = search.SearchDates().search(models.DateSearchFilters(**kwargs), **_loc(moeda, pais)) or []
    except Exception as e:
        raise FonteIndisponivel(f"fli falhou na grade de datas: {type(e).__name__}: {e}") from e
    if not dias:
        raise FonteIndisponivel("empty date grid (Google may be blocking the calendar)")

    opcoes = []
    for d in dias:
        datas = [x.date().isoformat() if hasattr(x, "date") else str(x) for x in d.date]
        if noites is not None:
            pernas = [Perna(origem, destino, datas[0]), Perna(destino, origem, datas[1])]
            t, link = "ida_volta", link_google(origem, destino, datas[0], datas[1], moeda, pais)
        else:
            pernas = [Perna(origem, destino, datas[0])]
            t, link = trecho, link_google(origem, destino, datas[0], moeda=moeda, pais=pais)
        opcoes.append(Opcao(
            fonte=FONTE, tipo="dinheiro", trecho=t, pernas=pernas, preco=round(d.price / passageiros, 2),
            link=link, observacoes=["date-grid price (no flight details)"],
        ))
    cache.set(FONTE, chave, [o.to_dict() for o in opcoes])
    return opcoes
