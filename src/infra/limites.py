"""Local usage counters: Seats.aero daily API limit and Playwright pages per run (SPEC §8)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from infra.config import DADOS

ARQUIVO = DADOS / "cache" / "contadores.json"

LIMITES_PADRAO = {
    "seats_aero_chamadas_dia": 1000,  # Partner API (Pro)
    "seats_aero_mcp_chamadas_dia": 300,  # anonymous MCP (server limit: 1,000/IP/day)
    "playwright_paginas_por_execucao": 15,
}


class LimiteExcedido(RuntimeError):
    pass


class Contadores:
    def __init__(self, arquivo: Path = ARQUIVO, limites: dict[str, int] | None = None, hoje=date.today):
        self.arquivo = arquivo
        self.limites = {**LIMITES_PADRAO, **(limites or {})}
        self.hoje = hoje

    def _ler(self) -> dict:
        if not self.arquivo.exists():
            return {}
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _gravar(self, dados: dict) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(dados, indent=2), encoding="utf-8")

    def _chave(self, nome: str, execucao: str | None) -> str:
        if nome.endswith("_dia"):
            return f"{nome}:{self.hoje().isoformat()}"
        return f"{nome}:{execucao or 'sem-execucao'}"

    def usado(self, nome: str, execucao: str | None = None) -> int:
        return self._ler().get(self._chave(nome, execucao), 0)

    def restante(self, nome: str, execucao: str | None = None) -> int:
        return self.limites[nome] - self.usado(nome, execucao)

    def consumir(self, nome: str, quantidade: int = 1, execucao: str | None = None) -> int:
        """Record usage; raises LimiteExcedido when over the limit. Returns what is left."""
        dados = self._ler()
        chave = self._chave(nome, execucao)
        atual = dados.get(chave, 0)
        if atual + quantidade > self.limites[nome]:
            raise LimiteExcedido(f"{nome}: limite {self.limites[nome]} atingido ({atual} usados)")
        dados[chave] = atual + quantidade
        # drop old daily counters
        hoje = self.hoje().isoformat()
        dados = {k: v for k, v in dados.items() if not (k.split(":")[0].endswith("_dia") and not k.endswith(hoje))}
        self._gravar(dados)
        return self.limites[nome] - dados[chave]
