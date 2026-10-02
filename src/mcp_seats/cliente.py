"""Minimal Seats.aero Partner API client (personal, non-commercial use).

Read-only. Honours the daily limit with a local counter and uses the file cache.
Without `SEATS_AERO_API_KEY` the client is not created and fontes/seats.py uses the official anonymous MCP (60 days).
Fields checked against the docs and real fixtures on 2026-10-02 (docs/research.md §Seats.aero); not yet
tested with a real key.
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
# Programs that published LATAM-operated flights on 2026-10-02 (LATAM Pass itself is not covered).
FONTES_PARCEIRAS_LATAM = ["delta", "virginatlantic", "livelo"]


class SemChave(RuntimeError):
    pass


class SeatsAero:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None, contadores: Contadores | None = None,
                 http: httpx.Client | None = None):
        self.api_key = api_key or os.environ.get("SEATS_AERO_API_KEY")
        if not self.api_key:
            raise SemChave("SEATS_AERO_API_KEY not set")
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
            raise SemChave(f"Seats.aero rejected the key ({r.status_code}): {r.text[:200]}")
        r.raise_for_status()
        dados = r.json()
        self.cache.set("seats_aero", chave, dados)
        return dados

    def cached_search(self, origem: str, destino: str, inicio: str, fim: str, fontes: list[str] | None = None,
                      cabine: str = "economy", take: int = 500) -> list[dict]:
        """GET /search — cached availability for a route over a date window. Paginates by cursor."""
        resultados: list[dict] = []
        params: dict[str, Any] = {
            "origin_airport": origem,
            "destination_airport": destino,
            "start_date": inicio,
            "end_date": fim,
            "cabins": cabine,
            "sources": ",".join(fontes) if fontes else None,  # None = every program
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
        """GET /trips/{id} — flights, times and taxes of an availability record."""
        return self._get(f"/trips/{availability_id}", {})

    def routes(self, fonte: str) -> list[dict]:
        return self._get("/routes", {"source": fonte})


def _hora_local(s: str) -> datetime:
    """Seats.aero sends the airport LOCAL time with a Z suffix. Ignore the time zone."""
    return datetime.fromisoformat(s.replace("Z", "").split(".")[0])


def _taxa(valor_centavos: int | None, moeda_taxa: str | None, moeda: str, cambio) -> tuple[float, str | None]:
    """Seats.aero reports taxes in the smallest unit (cents) of the program's currency."""
    from fontes.seats import converter_taxa

    if not valor_centavos:
        return 0.0, None
    return converter_taxa(valor_centavos / 100, moeda_taxa, moeda, cambio)


def normalizar_search(registros: list[dict], cabine: str = "economy", trecho: str = "ida",
                      passageiros: int = 1, moeda: str = "BRL", cambio=None) -> list[Opcao]:
    """Convert GET /search records (with include_trips) into options. Each trip becomes an option;
    a record without trips becomes an option without flight details."""
    from fontes.seats import _cambio
    from infra.programas import carregar

    registro = carregar()
    cambio = _cambio(cambio)
    letra = CABINES[cabine]
    opcoes: list[Opcao] = []
    for reg in registros:
        prog = registro.por_seats(reg.get("Source", ""))
        if not prog or not reg.get(f"{letra}Available"):
            continue
        programa = prog.id
        moeda_taxa = reg.get("TaxesCurrency")
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
                taxa, aviso = _taxa(t.get("TotalTaxes"), t.get("TaxesCurrency") or moeda_taxa, moeda, cambio)
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
                    milhas=int(t["MileageCost"]), taxas=taxa,
                    assentos_disponiveis=t.get("RemainingSeats") or None,
                    link=link, observacoes=obs_base + ([aviso] if aviso else []),
                ))
        else:
            milhas = reg.get(f"{letra}MileageCostRaw") or int(reg.get(f"{letra}MileageCost") or 0)
            if not milhas:
                continue
            taxa, aviso = _taxa(reg.get(f"{letra}TotalTaxesRaw") or reg.get(f"{letra}TotalTaxes"), moeda_taxa, moeda, cambio)
            cias = [c.strip() for c in (reg.get(f"{letra}Airlines") or "").split(",") if c.strip()]
            opcoes.append(Opcao(
                fonte="seats_aero", tipo="milhas", programa=programa, trecho=trecho,
                pernas=[Perna(origem=reg["Route"]["OriginAirport"], destino=reg["Route"]["DestinationAirport"],
                              data=reg["Date"], cia=cias[0] if cias else None,
                              conexoes=0 if reg.get(f"{letra}Direct") else 1)],
                milhas=int(milhas), taxas=taxa,
                assentos_disponiveis=reg.get(f"{letra}RemainingSeats") or None,
                link=link, observacoes=obs_base + ([aviso] if aviso else []) + ["sem detalhe de voo"],
            ))
    return opcoes
