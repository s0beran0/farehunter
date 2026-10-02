"""Deep links for the user to book/buy manually. Formats verified in a browser on 2026-10-02
(docs/research.md §5.1). If a site changes, fix it only here."""

from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import urlencode


def _epoch_ms_meio_dia(iso: str) -> int:
    d = date.fromisoformat(iso)
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp() * 1000)


def smiles(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1) -> str:
    """Smiles award search. Shows miles prices without login (Club/Diamond and regular)."""
    params = {
        "adults": adultos, "children": 0, "infants": 0, "cabin": "ALL",
        "tripType": 1 if volta else 2, "searchType": "both", "segments": 1, "isElegible": "false",
        "isFlexibleDateChecked": "false", "originAirport": origem, "originAirportIsAny": "false",
        "destinationAirport": destino, "destinAirportIsAny": "false",
        "departureDate": _epoch_ms_meio_dia(ida), "returnDate": _epoch_ms_meio_dia(volta) if volta else "",
    }
    return "https://www.smiles.com.br/mfe/emissao-passagem/?" + urlencode(params)


def latam(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1,
          milhas: bool = True) -> str:
    """LATAM search. With miles (`redemption=true`) the site requires login."""
    params = {
        "origin": origem, "destination": destino, "outbound": f"{ida}T12:00:00.000Z",
        "inbound": f"{volta}T12:00:00.000Z" if volta else "null", "adt": adultos, "chd": 0, "inf": 0,
        "trip": "RT" if volta else "OW", "cabin": "Economy", "redemption": "true" if milhas else "false",
        "sort": "RECOMMENDED",
    }
    return "https://www.latamairlines.com/br/pt/oferta-voos?" + urlencode(params)


def azul(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1,
         pontos: bool = True) -> str:
    """Azul flight selection (dates MM/dd/yyyy; cc=PTS for points). Results may require login."""
    def mdy(iso: str) -> str:
        return date.fromisoformat(iso).strftime("%m/%d/%Y")

    partes = [f"c[0].ds={origem}", f"c[0].std={mdy(ida)}", f"c[0].as={destino}"]
    if volta:
        partes += [f"c[1].ds={destino}", f"c[1].std={mdy(volta)}", f"c[1].as={origem}"]
    partes += [f"p[0].t=ADT", f"p[0].c={adultos}", "p[0].cp=false", "f.dl=3", "f.dr=3", f"cc={'PTS' if pontos else 'BRL'}"]
    return "https://www.voeazul.com.br/br/pt/home/selecao-voo?" + "&".join(partes)


def gol(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1) -> str:
    """GOL has no verified stable deep link; the Smiles search with searchType=g3 covers GOL flights with miles.
    For cash, use the option's Google Flights link."""
    return smiles(origem, destino, ida, volta, adultos)


def programa(prog: str, origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1) -> str | None:
    """Best link to book an award: a deep link with route/date when we have one, else the program's award-search page."""
    from infra.programas import carregar

    p = carregar().programa(prog)
    link = p.link if p else prog
    if link == "smiles":
        return smiles(origem, destino, ida, volta, adultos)
    if link == "latam_pass":
        return latam(origem, destino, ida, volta, adultos, milhas=True)
    if link == "azul":
        return azul(origem, destino, ida, volta, adultos, pontos=True)
    if link and link.startswith("http"):
        return link
    return None
