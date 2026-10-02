"""Registry of airline miles programs and transferable points currencies (config/programas.yaml, shipped with the plugin)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from infra.config import MODELOS_DIR, carregar_yaml


@dataclass(frozen=True)
class Programa:
    id: str
    nome: str
    tipo: str  # "milhas" (airline miles) | "pontos" (transferable points)
    moeda: str
    cias: tuple[str, ...] = ()
    seats: str | None = None
    link: str | None = None
    compra: str | None = None  # verified page to buy miles
    site: str | None = None  # points programs: where transfers are made


@dataclass(frozen=True)
class Parceria:
    origem: str  # points program id
    destino: str  # miles program id
    proporcao: float = 1.0  # points per mile
    minimo: int = 0


@dataclass
class Registro:
    milhas: dict[str, Programa] = field(default_factory=dict)
    pontos: dict[str, Programa] = field(default_factory=dict)
    parcerias: list[Parceria] = field(default_factory=list)

    def nome(self, pid: str | None) -> str:
        if not pid:
            return ""
        p = self.milhas.get(pid) or self.pontos.get(pid)
        return p.nome if p else pid

    def programa(self, pid: str) -> Programa | None:
        return self.milhas.get(pid) or self.pontos.get(pid)

    def por_seats(self, fonte: str) -> Programa | None:
        return next((p for p in self.milhas.values() if p.seats == fonte), None)

    def parceiros_de(self, origem: str) -> list[Parceria]:
        return [x for x in self.parcerias if x.origem == origem]

    def eh_milhas(self, pid: str) -> bool:
        return pid in self.milhas

    def eh_pontos(self, pid: str) -> bool:
        return pid in self.pontos


def registro_de_dict(d: dict) -> Registro:
    r = Registro()
    for pid, v in (d.get("milhas") or {}).items():
        r.milhas[pid] = Programa(
            id=pid, nome=v.get("nome", pid), tipo="milhas", moeda=str(v.get("moeda", "USD")).upper(),
            cias=tuple(str(c).upper() for c in v.get("cias") or ()), seats=v.get("seats"), link=v.get("link"),
            compra=v.get("compra"),
        )
    for pid, v in (d.get("pontos") or {}).items():
        r.pontos[pid] = Programa(id=pid, nome=v.get("nome", pid), tipo="pontos", moeda=str(v.get("moeda", "USD")).upper(),
                                 site=v.get("site"))
        for destino, cfg in (v.get("parceiros") or {}).items():
            cfg = cfg or {}
            r.parcerias.append(Parceria(pid, destino, float(cfg.get("proporcao") or 1), int(cfg.get("minimo") or 0)))
    return r


@lru_cache(maxsize=4)
def carregar(caminho: Path | None = None) -> Registro:
    return registro_de_dict(carregar_yaml(caminho or MODELOS_DIR / "programas.yaml"))
