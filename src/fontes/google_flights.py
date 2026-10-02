"""Google Flights via `fli` (pacote PyPI `flights`, versão fixada). Validado em 2026-10-02 (docs/research.md).

- `buscar_data`: voos de uma data (só ida ou ida e volta), com cia, número de voo e horários.
- `grade`: menor preço por data (calendário). Só ida, ou ida e volta com duração fixa em noites.

O preço do fli é o TOTAL para todos os passageiros; aqui vira preço por passageiro.
Os endpoints são frágeis (Google mudou a assinatura em ago/2026). Falhas viram exceção `FonteIndisponivel`
e o subagente registra a fonte como indisponível.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from infra.cache import Cache, chave_busca
from normalizacao.schema import Opcao, Perna

LOC = dict(currency="BRL", language="pt-BR", country="BR")
FONTE = "google_flights"


class FonteIndisponivel(RuntimeError):
    pass


def link_google(origem: str, destino: str, ida: str, volta: str | None = None) -> str:
    q = f"Flights to {destino} from {origem} on {ida}" + (f" through {volta}" if volta else " oneway")
    return f"https://www.google.com/travel/flights?q={quote(q)}&curr=BRL&hl=pt-BR&gl=BR"


def _fli():
    try:
        from fli import models, search
    except ImportError as e:  # pragma: no cover
        raise FonteIndisponivel(f"fli não instalado: {e}") from e
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
) -> list[Opcao]:
    cache = cache or Cache()
    chave = chave_busca("data", origem, destino, ida, volta, passageiros, cabine)
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
            brutos = search.SearchFlights().search(filtros, top_n=5, **LOC) or []
        else:
            brutos = search.SearchFlights().search(filtros, **LOC) or []
    except Exception as e:  # o fli levanta vários tipos ao quebrar
        raise FonteIndisponivel(f"fli falhou na busca por data: {type(e).__name__}: {e}") from e
    if not brutos:
        raise FonteIndisponivel("fli devolveu lista vazia (possível bloqueio do Google)")

    link = link_google(origem, destino, ida, volta)
    opcoes = []
    for r in brutos[: max_resultados]:
        if volta:
            ida_r, volta_r = r
            pernas, preco, trecho = [_perna(ida_r), _perna(volta_r)], ida_r.price, "ida_volta"
        else:
            pernas, preco, trecho = [_perna(r)], r.price, "ida"
        opcoes.append(Opcao(
            fonte=FONTE, tipo="dinheiro", trecho=trecho, pernas=pernas,
            preco_brl=round(preco / passageiros, 2), link=link,
        ))
    cache.set(FONTE, chave, [o.to_dict() for o in opcoes])
    return opcoes


def grade(
    origem: str, destino: str, inicio: str, fim: str, passageiros: int = 1, noites: int | None = None,
    cabine: str = "economy", trecho: str = "ida", cache: Cache | None = None,
) -> list[Opcao]:
    """Menor preço por data de partida em [inicio, fim]. Com `noites`, é ida e volta com essa duração."""
    cache = cache or Cache()
    chave = chave_busca("grade", origem, destino, inicio, fim, passageiros, noites, cabine, trecho)
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
        dias = search.SearchDates().search(models.DateSearchFilters(**kwargs), **LOC) or []
    except Exception as e:
        raise FonteIndisponivel(f"fli falhou na grade de datas: {type(e).__name__}: {e}") from e
    if not dias:
        raise FonteIndisponivel("grade de datas vazia (possível bloqueio do calendário do Google)")

    opcoes = []
    for d in dias:
        datas = [x.date().isoformat() if hasattr(x, "date") else str(x) for x in d.date]
        if noites is not None:
            pernas = [Perna(origem, destino, datas[0]), Perna(destino, origem, datas[1])]
            t, link = "ida_volta", link_google(origem, destino, datas[0], datas[1])
        else:
            pernas = [Perna(origem, destino, datas[0])]
            t, link = trecho, link_google(origem, destino, datas[0])
        opcoes.append(Opcao(
            fonte=FONTE, tipo="dinheiro", trecho=t, pernas=pernas, preco_brl=round(d.price / passageiros, 2),
            link=link, observacoes=["preço da grade de datas (sem detalhe do voo)"],
        ))
    cache.set(FONTE, chave, [o.to_dict() for o in opcoes])
    return opcoes
