"""Schema normalizado de opção (SPEC §7.1).

Convenções:
- Valores monetários e milhas são **por passageiro**. O motor multiplica pelo número de passageiros.
- `trecho` diz o que a opção cobre: "ida", "volta" ou "ida_volta" (bilhete único de ida e volta).
- Cada `Perna` é uma direção completa (pode ter conexões).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

FONTES_CONHECIDAS = {
    "kiwi",
    "google_flights",
    "seats_aero",
    "playwright_latam",
    "playwright_smiles",
    "playwright_azul",
    "playwright_cia",
    "manual",
}
TIPOS = {"dinheiro", "milhas"}
PROGRAMAS = {"smiles", "latam_pass", "azul"}
TRECHOS = {"ida", "volta", "ida_volta"}


@dataclass
class Perna:
    origem: str
    destino: str
    data: str  # YYYY-MM-DD (data de partida)
    partida: str | None = None  # HH:MM
    chegada: str | None = None  # HH:MM
    cia: str | None = None  # código IATA da cia operadora principal
    voos: list[str] = field(default_factory=list)
    conexoes: int = 0
    duracao_min: int | None = None
    escalas_min: list[int] = field(default_factory=list)  # tempo de cada conexão, se conhecido

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Perna":
        return cls(
            origem=str(d["origem"]).upper(),
            destino=str(d["destino"]).upper(),
            data=str(d["data"]),
            partida=d.get("partida"),
            chegada=d.get("chegada"),
            cia=(str(d["cia"]).upper() if d.get("cia") else None),
            voos=list(d.get("voos") or []),
            conexoes=int(d.get("conexoes") or 0),
            duracao_min=(int(d["duracao_min"]) if d.get("duracao_min") is not None else None),
            escalas_min=[int(x) for x in (d.get("escalas_min") or [])],
        )


@dataclass
class Opcao:
    fonte: str
    tipo: str
    pernas: list[Perna]
    trecho: str = "ida"
    programa: str | None = None
    preco_brl: float | None = None
    milhas: int | None = None
    taxas_brl: float = 0.0
    bagagem_inclusa: bool = False
    assentos_disponiveis: int | None = None
    confirmado_ao_vivo: bool = False
    link: str | None = None
    coletado_em: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    id: str = ""
    observacoes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.gerar_id()

    def gerar_id(self) -> str:
        chave = json.dumps(
            [
                self.fonte,
                self.tipo,
                self.programa,
                self.trecho,
                [(p.origem, p.destino, p.data, p.partida, p.voos) for p in self.pernas],
                self.preco_brl,
                self.milhas,
            ],
            sort_keys=True,
        )
        return hashlib.sha1(chave.encode()).hexdigest()[:12]

    def validar(self) -> list[str]:
        erros: list[str] = []
        if self.tipo not in TIPOS:
            erros.append(f"tipo inválido: {self.tipo}")
        if self.trecho not in TRECHOS:
            erros.append(f"trecho inválido: {self.trecho}")
        if not self.pernas:
            erros.append("opção sem pernas")
        if self.trecho == "ida_volta" and len(self.pernas) < 2:
            erros.append("trecho ida_volta precisa de 2 pernas")
        if self.tipo == "dinheiro" and (self.preco_brl is None or self.preco_brl <= 0):
            erros.append("opção em dinheiro sem preco_brl")
        if self.tipo == "milhas":
            if self.programa not in PROGRAMAS:
                erros.append(f"programa inválido: {self.programa}")
            if not self.milhas or self.milhas <= 0:
                erros.append("opção em milhas sem milhas")
        return erros

    @property
    def data_ida(self) -> str:
        return self.pernas[0].data

    @property
    def data_volta(self) -> str | None:
        return self.pernas[-1].data if self.trecho == "ida_volta" else None

    @property
    def cias(self) -> set[str]:
        return {p.cia for p in self.pernas if p.cia}

    @property
    def duracao_total_min(self) -> int:
        return sum(p.duracao_min or 0 for p in self.pernas)

    @property
    def conexoes_total(self) -> int:
        return sum(p.conexoes for p in self.pernas)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Opcao":
        return cls(
            fonte=d["fonte"],
            tipo=d["tipo"],
            pernas=[Perna.from_dict(p) for p in d["pernas"]],
            trecho=d.get("trecho", "ida_volta" if len(d["pernas"]) >= 2 else "ida"),
            programa=d.get("programa"),
            preco_brl=(float(d["preco_brl"]) if d.get("preco_brl") is not None else None),
            milhas=(int(d["milhas"]) if d.get("milhas") is not None else None),
            taxas_brl=float(d.get("taxas_brl") or 0),
            bagagem_inclusa=bool(d.get("bagagem_inclusa", False)),
            assentos_disponiveis=d.get("assentos_disponiveis"),
            confirmado_ao_vivo=bool(d.get("confirmado_ao_vivo", False)),
            link=d.get("link"),
            coletado_em=d.get("coletado_em") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            id=d.get("id", ""),
            observacoes=list(d.get("observacoes") or []),
        )


def carregar_opcoes(dados: list[dict[str, Any]]) -> tuple[list[Opcao], list[str]]:
    """Converte dicts em Opcao, descartando inválidas. Retorna (opções, avisos)."""
    opcoes: list[Opcao] = []
    avisos: list[str] = []
    for i, d in enumerate(dados):
        try:
            op = Opcao.from_dict(d)
        except (KeyError, TypeError, ValueError) as e:
            avisos.append(f"opção #{i} descartada: campo ausente/inválido ({e})")
            continue
        erros = op.validar()
        if erros:
            avisos.append(f"opção #{i} ({d.get('fonte')}) descartada: {'; '.join(erros)}")
            continue
        opcoes.append(op)
    return opcoes, avisos
