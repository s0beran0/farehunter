"""Award availability via Seats.aero, for every miles program in the registry that Seats.aero covers.

Two paths, same output (options with `tipo=milhas`, `fonte=seats_aero`, `confirmado_ao_vivo=False`):
1. **Partner API** (`SEATS_AERO_API_KEY` set): `/search` + `/trips`, no 60-day limit. See mcp_seats/cliente.py.
2. **Official anonymous MCP** (`https://seats.aero/mcp`, no key): only flights departing within 60 days,
   50 results per call, 1,000 calls/day per IP. Validated 2026-10-02.

Taxes come in each program's own currency (USD, EUR, GBP, BRL...) and are converted to the search currency.
LATAM Pass is not covered by Seats.aero.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

from fontes.mcp_http import ErroMCP, chamar_tool, json_do_resultado
from infra.cache import Cache, chave_busca
from infra.config import carregar_perfil
from infra.limites import Contadores
from infra.programas import carregar as carregar_registro
from normalizacao import links
from normalizacao.schema import Opcao, Perna

URL_MCP = "https://seats.aero/mcp"
FONTE = "seats_aero"
DIAS_ANONIMO = 60
SIMBOLOS_MOEDA = {"R$": "BRL", "US$": "USD", "$": "USD", "€": "EUR", "£": "GBP", "CA$": "CAD", "A$": "AUD"}


class FonteIndisponivel(RuntimeError):
    pass


def ler_valor_moeda(texto: str | None) -> tuple[float, str | None]:
    """'R$62.14 BRL' → (62.14, 'BRL'); '$5.60 USD' → (5.6, 'USD'); '£54.20' → (54.2, 'GBP'). Unknown → (0, None)."""
    if not texto:
        return 0.0, None
    texto = texto.strip()
    m = re.search(r"([\d.,]+)\s*([A-Z]{3})?\s*$", texto)
    if not m:
        return 0.0, None
    valor = float(m.group(1).replace(",", ""))
    moeda = m.group(2)
    if not moeda:
        moeda = next((c for s, c in sorted(SIMBOLOS_MOEDA.items(), key=lambda x: -len(x[0])) if texto.startswith(s)), None)
    return valor, moeda


def converter_taxa(valor: float, moeda: str | None, destino: str, cambio) -> tuple[float, str | None]:
    """Convert a tax to the search currency. Returns (value, warning or None)."""
    if not valor:
        return 0.0, None
    if not moeda:
        return 0.0, f"tax {valor} in unknown currency, not counted"
    if moeda.upper() == destino.upper():
        return valor, None
    try:
        return cambio.converter(valor, moeda, destino), None
    except Exception as e:  # SemCambio or network errors
        return 0.0, f"tax {valor} {moeda} not converted ({e})"


def _voos(campo: str | list | None) -> list[str]:
    if not campo:
        return []
    itens = campo if isinstance(campo, list) else re.split(r"[,\s]+", campo)
    out = []
    for v in itens:
        v = v.strip()
        if m := re.fullmatch(r"([A-Z0-9]{2})(\d{1,4})", v):
            out.append(f"{m.group(1)} {m.group(2)}")
        elif v:
            out.append(v)
    return out


def _cambio(cambio):
    if cambio is not None:
        return cambio
    from infra.cambio import padrao

    return padrao()


def normalizar_mcp(dados: dict, trecho: str = "ida", passageiros: int = 1, moeda: str = "BRL",
                   cambio=None) -> list[Opcao]:
    reg = carregar_registro()
    opcoes = []
    for f in dados.get("flights") or []:
        prog = reg.por_seats(f.get("mileage_program", ""))
        if not prog or not f.get("miles_price"):
            continue
        partida = datetime.fromisoformat(f["departs_at"])
        chegada = datetime.fromisoformat(f["arrives_at"]) if f.get("arrives_at") else None
        valor, moeda_taxa = ler_valor_moeda(f.get("taxes"))
        taxas, aviso = converter_taxa(valor, moeda_taxa, moeda, _cambio(cambio) if valor else None)
        cias = f.get("operating_carriers") or []
        obs = [f"Seats.aero data {round((f.get('minutes_old') or 0) / 60, 1)} h old"]
        if aviso:
            obs.append(aviso)
        opcoes.append(Opcao(
            fonte=FONTE, tipo="milhas", programa=prog.id, trecho=trecho,
            pernas=[Perna(
                origem=f["origin"], destino=f["destination"], data=partida.date().isoformat(),
                partida=partida.strftime("%H:%M"), chegada=chegada.strftime("%H:%M") if chegada else None,
                cia=cias[0] if cias else None, voos=_voos(f.get("flights")), conexoes=int(f.get("stops") or 0),
                duracao_min=f.get("duration_minutes"),
            )],
            milhas=int(f["miles_price"]), taxas=taxas,
            assentos_disponiveis=f.get("remaining_seats") or None,
            link=links.programa(prog.id, f["origin"], f["destination"], partida.date().isoformat(), adultos=passageiros),
            observacoes=obs,
        ))
    return opcoes


def _chamar_mcp(args: dict) -> dict:
    perfil = carregar_perfil()
    Contadores(limites=perfil.limites).consumir("seats_aero_mcp_chamadas_dia")
    try:
        return json_do_resultado(chamar_tool(URL_MCP, "get_flights", args))
    except ErroMCP as e:
        raise FonteIndisponivel(f"seats.aero MCP: {e}") from e


def fontes_seats(programas: list[str] | None) -> list[str | None]:
    """Registry program ids → Seats.aero source ids. None/empty → [None] (= every program, no filter)."""
    if not programas:
        return [None]
    reg = carregar_registro()
    fontes = [reg.milhas[p].seats for p in programas if p in reg.milhas and reg.milhas[p].seats]
    return list(dict.fromkeys(fontes)) or [None]


def buscar_mcp(
    origens: list[str], destinos: list[str], inicio: str, fim: str, programas: list[str] | None = None,
    passageiros: int = 1, cabine: str = "economy", trecho: str = "ida", cache: Cache | None = None,
    moeda: str = "BRL", cambio=None,
) -> tuple[list[Opcao], list[str]]:
    """Search the window; if a response is truncated (50 per call), redo it day by day. Returns (options, warnings)."""
    cache = cache or Cache()
    hoje = date.today()
    limite = hoje + timedelta(days=DIAS_ANONIMO)
    ini, fim_d = date.fromisoformat(inicio), date.fromisoformat(fim)
    avisos = []
    if ini > limite:
        raise FonteIndisponivel(
            f"dates beyond {DIAS_ANONIMO} days: anonymous Seats.aero access does not cover them. Set SEATS_AERO_API_KEY."
        )
    if fim_d > limite:
        avisos.append(f"anonymous Seats.aero only covers until {limite.isoformat()}; later dates have no award data")
        fim_d = limite

    def chamada(d1: date, d2: date, fonte: str | None) -> dict:
        args = {
            "origins": origens, "destinations": destinos, "start_date": d1.isoformat(), "end_date": d2.isoformat(),
            "cabin": cabine, "max_stops": 2, "max_results": 50, "sort": "mileage_cost",
        }
        if fonte:
            args["programs"] = [fonte]
        if passageiros > 1:
            args["min_seats"] = passageiros
        chave = chave_busca("mcp", sorted(args.items(), key=lambda x: x[0]))
        if (hit := cache.get(FONTE, chave)) is not None:
            return hit
        dados = _chamar_mcp(args)
        cache.set(FONTE, chave, dados)
        return dados

    opcoes: list[Opcao] = []
    for fonte in fontes_seats(programas):
        dados = chamada(ini, fim_d, fonte)
        if dados.get("truncated_by") and ini != fim_d:
            d = ini
            while d <= fim_d:
                opcoes.extend(normalizar_mcp(chamada(d, d, fonte), trecho, passageiros, moeda, cambio))
                d += timedelta(days=1)
        else:
            opcoes.extend(normalizar_mcp(dados, trecho, passageiros, moeda, cambio))
        if dados.get("warnings"):
            avisos.append(f"seats.aero ({fonte or 'all programs'}): {dados['warnings']}")
    return opcoes, avisos


def buscar(
    origens: list[str], destinos: list[str], inicio: str, fim: str, passageiros: int = 1,
    cabine: str = "economy", trecho: str = "ida", programas: list[str] | None = None, moeda: str = "BRL",
) -> tuple[list[Opcao], list[str]]:
    """Partner API when a key is set; otherwise the anonymous MCP."""
    if os.environ.get("SEATS_AERO_API_KEY"):
        from mcp_seats.cliente import SeatsAero, normalizar_search

        cli = SeatsAero()
        fontes = [f for f in fontes_seats(programas) if f]
        opcoes: list[Opcao] = []
        for o in origens:
            for d in destinos:
                registros = cli.cached_search(o, d, inicio, fim, fontes=fontes or None, cabine=cabine)
                opcoes.extend(normalizar_search(registros, cabine=cabine, trecho=trecho, passageiros=passageiros,
                                                moeda=moeda))
        return opcoes, []
    return buscar_mcp(origens, destinos, inicio, fim, programas=programas, passageiros=passageiros, cabine=cabine,
                      trecho=trecho, moeda=moeda)
