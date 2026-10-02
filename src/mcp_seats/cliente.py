"""Cliente mínimo da Partner API do Seats.aero (uso pessoal, não comercial).

Só leitura. Respeita o limite diário com contador local e usa o cache em arquivo.
Sem `SEATS_AERO_API_KEY` o cliente não é criado e fontes/seats.py usa o MCP oficial anônimo (até 60 dias).
Campos conferidos na documentação e em fixtures reais em 2026-10-02 (docs/research.md §Seats.aero); ainda não
testado com chave real.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from infra.cache import Cache, chave_busca
from infra.config import carregar_perfil
from infra.limites import Contadores
from normalizacao import links
from normalizacao.schema import Opcao, Perna

BASE_URL = "https://seats.aero/partnerapi"
CABINES = {"economy": "Y", "premium": "W", "business": "J", "first": "F"}
# Programas do Seats.aero relevantes para voos no Brasil (o valor é o `source` da API).
FONTES_BRASIL = ["smiles", "azul"]
# Programas que publicaram voos operados pela LATAM em 2026-10-02 (LATAM Pass não é coberto diretamente).
FONTES_PARCEIRAS_LATAM = ["delta", "virginatlantic", "livelo"]


class SemChave(RuntimeError):
    pass


class SeatsAero:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None, contadores: Contadores | None = None,
                 http: httpx.Client | None = None):
        self.api_key = api_key or os.environ.get("SEATS_AERO_API_KEY")
        if not self.api_key:
            raise SemChave("SEATS_AERO_API_KEY não definida")
        self.cache = cache or Cache()
        self.contadores = contadores or Contadores(limites=carregar_perfil().limites)
        self.http = http or httpx.Client(base_url=BASE_URL, timeout=30)

    def _get(self, caminho: str, params: dict[str, Any]) -> Any:
        params = {k: v for k, v in params.items() if v not in (None, "", [])}
        chave = chave_busca(caminho, sorted(params.items()))
        if (hit := self.cache.get("seats_aero", chave)) is not None:
            return hit
        self.contadores.consumir("seats_aero_chamadas_dia")
        r = self.http.get(caminho, params=params, headers={"Partner-Authorization": self.api_key, "accept": "application/json"})
        if r.status_code in (401, 403):
            raise SemChave(f"Seats.aero recusou a chave ({r.status_code}): {r.text[:200]}")
        r.raise_for_status()
        dados = r.json()
        self.cache.set("seats_aero", chave, dados)
        return dados

    def cached_search(self, origem: str, destino: str, inicio: str, fim: str, fontes: list[str] | None = None,
                      cabine: str = "economy", take: int = 500) -> list[dict]:
        """GET /search — disponibilidade em cache para uma rota numa janela de datas. Pagina por cursor."""
        resultados: list[dict] = []
        params: dict[str, Any] = {
            "origin_airport": origem,
            "destination_airport": destino,
            "start_date": inicio,
            "end_date": fim,
            "cabins": cabine,
            "sources": ",".join(fontes or FONTES_BRASIL),
            "take": take,
            "include_trips": "true",
        }
        for _ in range(5):
            pagina = self._get("/search", params)
            resultados.extend(pagina.get("data") or [])
            if not pagina.get("hasMore") or not pagina.get("cursor"):
                break
            params = {**params, "cursor": pagina["cursor"], "skip": len(resultados)}
        return resultados

    def trips(self, availability_id: str) -> dict:
        """GET /trips/{id} — voos, horários e taxas de um registro de disponibilidade."""
        return self._get(f"/trips/{availability_id}", {})

    def routes(self, fonte: str) -> list[dict]:
        return self._get("/routes", {"source": fonte})


def _hora_local(s: str) -> datetime:
    """O Seats.aero manda horário LOCAL do aeroporto com sufixo Z. Ignorar o fuso."""
    return datetime.fromisoformat(s.replace("Z", "").split(".")[0])


def _taxa(valor_centavos: int | None, moeda: str | None) -> tuple[float, str | None]:
    if not valor_centavos:
        return 0.0, None
    if (moeda or "").upper() != "BRL":
        return 0.0, f"taxa em {moeda} ({valor_centavos / 100:.2f}) não convertida"
    return valor_centavos / 100, None


def normalizar_search(registros: list[dict], cabine: str = "economy", trecho: str = "ida",
                      passageiros: int = 1) -> list[Opcao]:
    """Converte registros do GET /search (com include_trips) em opções. Um trip vira uma opção;
    registro sem trips vira uma opção sem detalhe de voo."""
    letra = CABINES[cabine]
    opcoes: list[Opcao] = []
    for reg in registros:
        programa = {"smiles": "smiles", "azul": "azul"}.get(reg.get("Source", ""))
        if not programa or not reg.get(f"{letra}Available"):
            continue
        moeda = reg.get("TaxesCurrency")
        idade_h = None
        if reg.get("UpdatedAt"):
            atualizado = datetime.fromisoformat(reg["UpdatedAt"].replace("Z", "+00:00"))
            idade_h = round((datetime.now(timezone.utc) - atualizado).total_seconds() / 3600, 1)
        obs_base = [f"dado do Seats.aero com {idade_h} h"] if idade_h is not None else []
        link = links.programa(programa, reg["Route"]["OriginAirport"], reg["Route"]["DestinationAirport"], reg["Date"],
                              adultos=passageiros)
        trips = [t for t in (reg.get("AvailabilityTrips") or []) if (t.get("Cabin") or cabine) == cabine]
        if trips:
            for t in trips:
                partida, chegada = _hora_local(t["DepartsAt"]), _hora_local(t["ArrivesAt"])
                taxa, aviso = _taxa(t.get("TotalTaxes"), t.get("TaxesCurrency") or moeda)
                voos = [v.strip() for v in (t.get("FlightNumbers") or "").split(",") if v.strip()]
                carriers = [c.strip() for c in (t.get("Carriers") or "").split(",") if c.strip()]
                opcoes.append(Opcao(
                    fonte="seats_aero", tipo="milhas", programa=programa, trecho=trecho,
                    pernas=[Perna(
                        origem=t.get("OriginAirport") or reg["Route"]["OriginAirport"],
                        destino=t.get("DestinationAirport") or reg["Route"]["DestinationAirport"],
                        data=partida.date().isoformat(), partida=partida.strftime("%H:%M"),
                        chegada=chegada.strftime("%H:%M"), cia=carriers[0] if carriers else None, voos=voos,
                        conexoes=int(t.get("Stops") or 0), duracao_min=t.get("TotalDuration"),
                    )],
                    milhas=int(t["MileageCost"]), taxas_brl=taxa,
                    assentos_disponiveis=t.get("RemainingSeats") or None,
                    link=link, observacoes=obs_base + ([aviso] if aviso else []),
                ))
        else:
            milhas = reg.get(f"{letra}MileageCostRaw") or int(reg.get(f"{letra}MileageCost") or 0)
            if not milhas:
                continue
            taxa, aviso = _taxa(reg.get(f"{letra}TotalTaxesRaw") or reg.get(f"{letra}TotalTaxes"), moeda)
            cias = [c.strip() for c in (reg.get(f"{letra}Airlines") or "").split(",") if c.strip()]
            opcoes.append(Opcao(
                fonte="seats_aero", tipo="milhas", programa=programa, trecho=trecho,
                pernas=[Perna(origem=reg["Route"]["OriginAirport"], destino=reg["Route"]["DestinationAirport"],
                              data=reg["Date"], cia=cias[0] if cias else None,
                              conexoes=0 if reg.get(f"{letra}Direct") else 1)],
                milhas=int(milhas), taxas_brl=taxa,
                assentos_disponiveis=reg.get(f"{letra}RemainingSeats") or None,
                link=link, observacoes=obs_base + ([aviso] if aviso else []) + ["sem detalhe de voo"],
            ))
    return opcoes
