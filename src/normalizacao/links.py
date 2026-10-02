"""Deep links para o usuário emitir/comprar manualmente. Formatos verificados em navegador em 2026-10-02
(docs/research.md §5.1). Se um site mudar, ajuste só aqui."""

from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import urlencode


def _epoch_ms_meio_dia(iso: str) -> int:
    d = date.fromisoformat(iso)
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp() * 1000)


def smiles(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1) -> str:
    """Busca de emissão Smiles. Mostra preço em milhas sem login (Clube/Diamante e normal)."""
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
    """Busca LATAM. Com milhas (`redemption=true`) o site exige login."""
    params = {
        "origin": origem, "destination": destino, "outbound": f"{ida}T12:00:00.000Z",
        "inbound": f"{volta}T12:00:00.000Z" if volta else "null", "adt": adultos, "chd": 0, "inf": 0,
        "trip": "RT" if volta else "OW", "cabin": "Economy", "redemption": "true" if milhas else "false",
        "sort": "RECOMMENDED",
    }
    return "https://www.latamairlines.com/br/pt/oferta-voos?" + urlencode(params)


def azul(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1,
         pontos: bool = True) -> str:
    """Seleção de voo Azul (datas MM/dd/yyyy; cc=PTS para pontos). Resultado pode exigir login."""
    def mdy(iso: str) -> str:
        return date.fromisoformat(iso).strftime("%m/%d/%Y")

    partes = [f"c[0].ds={origem}", f"c[0].std={mdy(ida)}", f"c[0].as={destino}"]
    if volta:
        partes += [f"c[1].ds={destino}", f"c[1].std={mdy(volta)}", f"c[1].as={origem}"]
    partes += [f"p[0].t=ADT", f"p[0].c={adultos}", "p[0].cp=false", "f.dl=3", "f.dr=3", f"cc={'PTS' if pontos else 'BRL'}"]
    return "https://www.voeazul.com.br/br/pt/home/selecao-voo?" + "&".join(partes)


def gol(origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1) -> str:
    """GOL não tem deep link estável verificado; a busca Smiles com searchType=g3 cobre voos GOL em milhas.
    Para dinheiro, o link do Google Flights da opção é o caminho."""
    return smiles(origem, destino, ida, volta, adultos)


def programa(prog: str, origem: str, destino: str, ida: str, volta: str | None = None, adultos: int = 1) -> str | None:
    if prog == "smiles":
        return smiles(origem, destino, ida, volta, adultos)
    if prog == "latam_pass":
        return latam(origem, destino, ida, volta, adultos, milhas=True)
    if prog == "azul":
        return azul(origem, destino, ida, volta, adultos, pontos=True)
    return None
