"""Disponibilidade em milhas via Seats.aero.

Dois caminhos, mesma saída (opções `tipo=milhas`, `fonte=seats_aero`, `confirmado_ao_vivo=False`):
1. **Partner API** (`SEATS_AERO_API_KEY` definida): `/search` + `/trips`, sem limite de 60 dias. Ver mcp_seats/cliente.py.
2. **MCP oficial anônimo** (`https://seats.aero/mcp`, sem chave): só voos que partem em até 60 dias,
   50 resultados por chamada, 1.000 chamadas/dia por IP. Validado em 2026-10-02.

LATAM Pass não é coberto pelo Seats.aero; voos LATAM só aparecem via programas parceiros (não usados aqui).
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

from fontes.mcp_http import ErroMCP, chamar_tool, json_do_resultado
from infra.cache import Cache, chave_busca
from infra.config import carregar_perfil
from infra.limites import Contadores
from normalizacao import links
from normalizacao.schema import Opcao, Perna

URL_MCP = "https://seats.aero/mcp"
FONTE = "seats_aero"
PROGRAMAS = {"smiles": "smiles", "azul": "azul"}  # nome no Seats.aero → nome interno
DIAS_ANONIMO = 60


class FonteIndisponivel(RuntimeError):
    pass


def _taxas_brl(texto: str | None) -> tuple[float, str | None]:
    """'R$62.14 BRL' → (62.14, None). Moeda diferente de BRL → (0, aviso)."""
    if not texto:
        return 0.0, None
    m = re.search(r"([\d.,]+)\s*([A-Z]{3})?\s*$", texto.strip())
    if not m:
        return 0.0, f"taxa não interpretada: {texto}"
    valor = float(m.group(1).replace(",", ""))
    moeda = m.group(2) or ("BRL" if "R$" in texto else None)
    if moeda != "BRL":
        return 0.0, f"taxa em {moeda or '?'} ({texto}) não convertida"
    return valor, None


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


def normalizar_mcp(dados: dict, trecho: str = "ida", passageiros: int = 1) -> list[Opcao]:
    opcoes = []
    for f in dados.get("flights") or []:
        programa = PROGRAMAS.get(f.get("mileage_program", ""))
        if not programa or not f.get("miles_price"):
            continue
        partida = datetime.fromisoformat(f["departs_at"])
        chegada = datetime.fromisoformat(f["arrives_at"]) if f.get("arrives_at") else None
        taxas, aviso = _taxas_brl(f.get("taxes"))
        cias = f.get("operating_carriers") or []
        obs = [f"dado do Seats.aero com {round((f.get('minutes_old') or 0) / 60, 1)} h"]
        if aviso:
            obs.append(aviso)
        opcoes.append(Opcao(
            fonte=FONTE, tipo="milhas", programa=programa, trecho=trecho,
            pernas=[Perna(
                origem=f["origin"], destino=f["destination"], data=partida.date().isoformat(),
                partida=partida.strftime("%H:%M"), chegada=chegada.strftime("%H:%M") if chegada else None,
                cia=cias[0] if cias else None, voos=_voos(f.get("flights")), conexoes=int(f.get("stops") or 0),
                duracao_min=f.get("duration_minutes"),
            )],
            milhas=int(f["miles_price"]), taxas_brl=taxas,
            assentos_disponiveis=f.get("remaining_seats") or None,
            link=links.programa(programa, f["origin"], f["destination"], partida.date().isoformat(), adultos=passageiros),
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


def buscar_mcp(
    origens: list[str], destinos: list[str], inicio: str, fim: str, programas: list[str] | None = None,
    passageiros: int = 1, cabine: str = "economy", trecho: str = "ida", cache: Cache | None = None,
) -> tuple[list[Opcao], list[str]]:
    """Busca na janela; se a resposta vier truncada (50 por chamada), refaz dia a dia. Retorna (opções, avisos)."""
    cache = cache or Cache()
    hoje = date.today()
    limite = hoje + timedelta(days=DIAS_ANONIMO)
    ini, fim_d = date.fromisoformat(inicio), date.fromisoformat(fim)
    avisos = []
    if ini > limite:
        raise FonteIndisponivel(
            f"datas além de {DIAS_ANONIMO} dias: o acesso anônimo do Seats.aero não cobre. Defina SEATS_AERO_API_KEY."
        )
    if fim_d > limite:
        avisos.append(f"Seats.aero anônimo cobre só até {limite.isoformat()}; datas depois disso ficaram sem milhas")
        fim_d = limite
    programas = programas or list(PROGRAMAS)

    def chamada(d1: date, d2: date, programa: str) -> dict:
        args = {
            "origins": origens, "destinations": destinos, "start_date": d1.isoformat(), "end_date": d2.isoformat(),
            "programs": [programa], "cabin": cabine, "max_stops": 2, "max_results": 50, "sort": "mileage_cost",
        }
        if passageiros > 1:
            args["min_seats"] = passageiros
        chave = chave_busca("mcp", sorted(args.items(), key=lambda x: x[0]))
        if (hit := cache.get(FONTE, chave)) is not None:
            return hit
        dados = _chamar_mcp(args)
        cache.set(FONTE, chave, dados)
        return dados

    opcoes: list[Opcao] = []
    for programa in programas:
        dados = chamada(ini, fim_d, programa)
        if dados.get("truncated_by") and ini != fim_d:
            d = ini
            while d <= fim_d:
                opcoes.extend(normalizar_mcp(chamada(d, d, programa), trecho, passageiros))
                d += timedelta(days=1)
        else:
            opcoes.extend(normalizar_mcp(dados, trecho, passageiros))
        if dados.get("warnings"):
            avisos.append(f"seats.aero ({programa}): {dados['warnings']}")
    return opcoes, avisos


def buscar(
    origens: list[str], destinos: list[str], inicio: str, fim: str, passageiros: int = 1,
    cabine: str = "economy", trecho: str = "ida",
) -> tuple[list[Opcao], list[str]]:
    """Usa a Partner API se houver chave; senão o MCP anônimo."""
    if os.environ.get("SEATS_AERO_API_KEY"):
        from mcp_seats.cliente import SeatsAero, normalizar_search

        cli = SeatsAero()
        opcoes: list[Opcao] = []
        for o in origens:
            for d in destinos:
                registros = cli.cached_search(o, d, inicio, fim, cabine=cabine)
                opcoes.extend(normalizar_search(registros, cabine=cabine, trecho=trecho, passageiros=passageiros))
        return opcoes, []
    return buscar_mcp(origens, destinos, inicio, fim, passageiros=passageiros, cabine=cabine, trecho=trecho)
