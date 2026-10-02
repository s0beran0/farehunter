"""Cache local em arquivo por (fonte, chave) com TTL (SPEC §8)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from infra.config import DADOS

CACHE_DIR = DADOS / "cache"

# TTL padrão em horas por fonte. Dinheiro muda rápido; disponibilidade de milhas em cache, menos.
TTL_HORAS = {
    "kiwi": 2,
    "google_flights": 2,
    "google_flights_grade": 2,
    "seats_aero": 6,
    "playwright_latam": 2,
    "playwright_smiles": 2,
    "playwright_azul": 2,
    "promos": 24,
}
TTL_PADRAO_HORAS = 2


class Cache:
    def __init__(self, diretorio: Path = CACHE_DIR, agora=time.time):
        self.dir = diretorio
        self.agora = agora

    def _arquivo(self, fonte: str, chave: str) -> Path:
        h = hashlib.sha1(chave.encode()).hexdigest()[:16]
        return self.dir / fonte / f"{h}.json"

    def get(self, fonte: str, chave: str, ttl_horas: float | None = None) -> Any | None:
        arq = self._arquivo(fonte, chave)
        if not arq.exists():
            return None
        try:
            registro = json.loads(arq.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        ttl = (ttl_horas if ttl_horas is not None else TTL_HORAS.get(fonte, TTL_PADRAO_HORAS)) * 3600
        if self.agora() - registro["salvo_em"] > ttl:
            return None
        return registro["dados"]

    def set(self, fonte: str, chave: str, dados: Any) -> Path:
        arq = self._arquivo(fonte, chave)
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(
            json.dumps({"chave": chave, "salvo_em": self.agora(), "dados": dados}, ensure_ascii=False),
            encoding="utf-8",
        )
        return arq

    def limpar_expirados(self) -> int:
        removidos = 0
        for arq in self.dir.glob("*/*.json"):
            fonte = arq.parent.name
            try:
                salvo = json.loads(arq.read_text(encoding="utf-8"))["salvo_em"]
            except (json.JSONDecodeError, KeyError):
                arq.unlink()
                removidos += 1
                continue
            if self.agora() - salvo > TTL_HORAS.get(fonte, TTL_PADRAO_HORAS) * 3600:
                arq.unlink()
                removidos += 1
        return removidos


def chave_busca(*partes: Any) -> str:
    return "|".join(str(p).upper() for p in partes)
