"""Carrega e valida perfil.yaml e milheiro.yaml da pasta de dados do usuário.

Código (RAIZ) e dados (DADOS) ficam separados: o plugin é substituído a cada atualização, os dados não.
DADOS = $FAREHUNTER_DATA, senão $CLAUDE_PLUGIN_DATA (pasta persistente do plugin), senão ~/.farehunter.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from i18n import t

RAIZ = Path(__file__).resolve().parents[2]
MODELOS_DIR = RAIZ / "config"  # valores iniciais que vêm com o plugin


def _dados() -> Path:
    for var in ("FAREHUNTER_DATA", "CLAUDE_PLUGIN_DATA"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser()
    return Path.home() / ".farehunter"


DADOS = _dados()
CONFIG_DIR = DADOS / "config"


def preparar_dados() -> Path:
    """Cria a pasta de dados e copia os modelos (milheiro.yaml) na primeira execução. Nunca sobrescreve."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for nome in ("milheiro.yaml",):
        destino = CONFIG_DIR / nome
        if not destino.exists() and (MODELOS_DIR / nome).exists():
            shutil.copy2(MODELOS_DIR / nome, destino)
    return DADOS
DIAS_VALIDADE_MILHEIRO = 15


@dataclass
class AeroportoAlternativo:
    iata: str
    custo_deslocamento_brl: float = 0.0
    observacao: str = ""


@dataclass
class SaldoPrograma:
    saldo: int = 0
    clube: bool = False
    categoria: str = ""


@dataclass
class Perfil:
    passageiros_padrao: int = 1
    aeroportos_origem: list[str] = field(default_factory=list)
    aeroportos_alternativos_origem: list[AeroportoAlternativo] = field(default_factory=list)
    aeroportos_alternativos_destino: list[AeroportoAlternativo] = field(default_factory=list)
    flex_dias_padrao: int = 3
    bagagem_despachada: bool = False
    custo_bagagem_trecho_brl: dict[str, float] = field(default_factory=dict)
    programas: dict[str, SaldoPrograma] = field(default_factory=dict)
    pontos_transferiveis: dict[str, int] = field(default_factory=dict)
    valor_minimo_economia_brl: float = 50.0
    conexao_curta_min: int = 60
    limites: dict[str, int] = field(default_factory=dict)

    def custo_bagagem(self, cia: str | None) -> float:
        tabela = self.custo_bagagem_trecho_brl
        if cia and cia.upper() in tabela:
            return float(tabela[cia.upper()])
        return float(tabela.get("padrao", 0.0))

    def alternativo(self, iata: str) -> AeroportoAlternativo | None:
        for a in [*self.aeroportos_alternativos_origem, *self.aeroportos_alternativos_destino]:
            if a.iata.upper() == iata.upper():
                return a
        return None


@dataclass
class CpmPrograma:
    cpm_compra_atual: float | None = None
    cpm_valor_uso: float | None = None
    compra_minima: int = 0  # milhas mínimas por compra
    compra_passo: int = 1000  # compra em múltiplos de
    fonte: str = ""
    atualizado_em: str = ""

    @property
    def cpm_uso_efetivo(self) -> float | None:
        """Valor das milhas que o usuário já tem. Sem valor de uso, cai no custo de compra."""
        return self.cpm_valor_uso if self.cpm_valor_uso is not None else self.cpm_compra_atual


@dataclass
class Transferencia:
    origem: str  # livelo, esfera...
    destino: str  # smiles, latam_pass, azul
    bonus_pct: float = 0.0
    ate: str = ""  # YYYY-MM-DD; vazio = sem validade definida
    proporcao: float = 1.0  # pontos de origem por milha (antes do bônus)
    minimo: int = 0  # mínimo de pontos por transferência

    def bonus_vigente(self, hoje: date) -> float:
        if self.ate:
            try:
                if date.fromisoformat(self.ate) < hoje:
                    return 0.0
            except ValueError:
                return 0.0
        return float(self.bonus_pct or 0)


@dataclass
class Milheiro:
    programas: dict[str, CpmPrograma] = field(default_factory=dict)
    pontos: dict[str, CpmPrograma] = field(default_factory=dict)
    transferencias: list[Transferencia] = field(default_factory=list)

    def avisos_validade(self, hoje: date) -> list[str]:
        avisos = []
        for nome, cpm in {**self.programas, **self.pontos}.items():
            if not cpm.atualizado_em:
                avisos.append(t("aviso.milheiro_sem_data", nome=nome))
                continue
            try:
                idade = (hoje - date.fromisoformat(cpm.atualizado_em)).days
            except ValueError:
                avisos.append(t("aviso.milheiro_data_invalida", nome=nome, data=cpm.atualizado_em))
                continue
            if idade > DIAS_VALIDADE_MILHEIRO:
                avisos.append(t("aviso.milheiro_velho", nome=nome, dias=idade, limite=DIAS_VALIDADE_MILHEIRO))
        return avisos


def _alt(lista: list[Any] | None) -> list[AeroportoAlternativo]:
    out = []
    for item in lista or []:
        if isinstance(item, str):
            out.append(AeroportoAlternativo(iata=item.upper()))
        else:
            out.append(
                AeroportoAlternativo(
                    iata=str(item["iata"]).upper(),
                    custo_deslocamento_brl=float(item.get("custo_deslocamento_brl") or 0),
                    observacao=item.get("observacao", ""),
                )
            )
    return out


def perfil_de_dict(d: dict[str, Any]) -> Perfil:
    return Perfil(
        passageiros_padrao=int(d.get("passageiros_padrao", 1)),
        aeroportos_origem=[s.upper() for s in d.get("aeroportos_origem") or []],
        aeroportos_alternativos_origem=_alt(d.get("aeroportos_alternativos_origem")),
        aeroportos_alternativos_destino=_alt(d.get("aeroportos_alternativos_destino")),
        flex_dias_padrao=int(d.get("flex_dias_padrao", 3)),
        bagagem_despachada=bool(d.get("bagagem_despachada", False)),
        custo_bagagem_trecho_brl={
            str(k).upper() if k != "padrao" else "padrao": float(v)
            for k, v in (d.get("custo_bagagem_trecho_brl") or {}).items()
        },
        programas={
            nome: SaldoPrograma(
                saldo=int((v or {}).get("saldo") or 0),
                clube=bool((v or {}).get("clube", False)),
                categoria=(v or {}).get("categoria") or "",
            )
            for nome, v in (d.get("programas") or {}).items()
        },
        pontos_transferiveis={k: int(v or 0) for k, v in (d.get("pontos_transferiveis") or {}).items()},
        valor_minimo_economia_brl=float(d.get("valor_minimo_economia_brl", 50)),
        conexao_curta_min=int(d.get("conexao_curta_min", 60)),
        limites={k: int(v) for k, v in (d.get("limites") or {}).items()},
    )


def _cpm(v: dict[str, Any] | None) -> CpmPrograma:
    v = v or {}
    return CpmPrograma(
        cpm_compra_atual=(float(v["cpm_compra_atual"]) if v.get("cpm_compra_atual") is not None else None),
        cpm_valor_uso=(float(v["cpm_valor_uso"]) if v.get("cpm_valor_uso") is not None else None),
        compra_minima=int(v.get("compra_minima") or 0),
        compra_passo=int(v.get("compra_passo") or 1000),
        fonte=v.get("fonte") or "",
        atualizado_em=str(v.get("atualizado_em") or ""),
    )


def milheiro_de_dict(d: dict[str, Any]) -> Milheiro:
    transferencias = []
    for chave, v in (d.get("transferencias") or {}).items():
        v = v or {}
        origem, _, destino = chave.partition("_")
        transferencias.append(
            Transferencia(
                origem=v.get("origem", origem),
                destino=v.get("destino", destino),
                bonus_pct=float(v.get("bonus_pct") or 0),
                ate=str(v.get("ate") or ""),
                proporcao=float(v.get("proporcao") or 1.0),
                minimo=int(v.get("minimo") or 0),
            )
        )
    return Milheiro(
        programas={k: _cpm(d.get(k)) for k in ("smiles", "latam_pass", "azul") if k in d},
        pontos={k: _cpm(v) for k, v in (d.get("pontos") or {}).items()},
        transferencias=transferencias,
    )


def carregar_env(caminho: Path | None = None) -> None:
    """Carrega .env (KEY=valor) sem sobrescrever variáveis já definidas no ambiente."""
    import os

    arq = caminho or DADOS / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def carregar_yaml(caminho: Path) -> dict[str, Any]:
    if not caminho.exists():
        return {}
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def carregar_perfil(caminho: Path | None = None) -> Perfil:
    return perfil_de_dict(carregar_yaml(caminho or CONFIG_DIR / "perfil.yaml"))


def carregar_milheiro(caminho: Path | None = None) -> Milheiro:
    return milheiro_de_dict(carregar_yaml(caminho or CONFIG_DIR / "milheiro.yaml"))
