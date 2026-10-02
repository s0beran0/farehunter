"""Loads and validates perfil.yaml and milheiro.yaml from the user's data folder.

Code (RAIZ) and data (DADOS) are kept apart: the plugin is replaced on every update, the data is not.
DADOS = $FAREHUNTER_DATA, else $CLAUDE_PLUGIN_DATA (the plugin's persistent folder), else ~/.farehunter.
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
MODELOS_DIR = RAIZ / "config"  # initial values shipped with the plugin


def _dados() -> Path:
    for var in ("FAREHUNTER_DATA", "CLAUDE_PLUGIN_DATA"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser()
    return Path.home() / ".farehunter"


DADOS = _dados()
CONFIG_DIR = DADOS / "config"


def preparar_dados() -> Path:
    """Create the data folder and copy the templates (milheiro.yaml) on first run. Never overwrites."""
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
    custo_deslocamento: float = 0.0
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
    custo_bagagem_trecho: dict[str, float] = field(default_factory=dict)
    programas: dict[str, SaldoPrograma] = field(default_factory=dict)
    pontos_transferiveis: dict[str, int] = field(default_factory=dict)
    valor_minimo_economia: float = 50.0
    conexao_curta_min: int = 60
    conexao_bilhetes_separados_min: int = 180  # minimum layover between separate tickets
    limites: dict[str, int] = field(default_factory=dict)

    def custo_bagagem(self, cia: str | None) -> float:
        tabela = self.custo_bagagem_trecho
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
    compra_minima: int = 0  # minimum miles per purchase
    compra_passo: int = 1000  # purchases in multiples of
    fonte: str = ""
    atualizado_em: str = ""
    moeda: str = ""  # currency of the CPM values; empty = the program's currency from the registry

    @property
    def cpm_uso_efetivo(self) -> float | None:
        """Value of miles the user already has. Without a use value, falls back to the purchase cost."""
        return self.cpm_valor_uso if self.cpm_valor_uso is not None else self.cpm_compra_atual


@dataclass
class Transferencia:
    origem: str  # points program id (livelo, amex_mr...)
    destino: str  # miles program id (smiles, united...)
    bonus_pct: float = 0.0
    ate: str = ""  # YYYY-MM-DD; empty = no end date
    proporcao: float = 1.0  # source points per mile (before the bonus)
    minimo: int = 0  # minimum points per transfer

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

    def na_moeda(self, moeda: str, cambio) -> tuple["Milheiro", list[str]]:
        """Copy with every CPM converted to `moeda`. Programs whose rate is unavailable are dropped (with a warning)."""
        from dataclasses import replace

        from infra import programas as registro_mod

        reg = registro_mod.carregar()
        avisos: list[str] = []

        def converter(grupo: dict[str, CpmPrograma]) -> dict[str, CpmPrograma]:
            out = {}
            for pid, cpm in grupo.items():
                prog = reg.programa(pid)
                origem = (cpm.moeda or (prog.moeda if prog else moeda)).upper()
                try:
                    taxa = cambio.taxa(origem, moeda)
                except Exception as e:  # SemCambio or network errors
                    avisos.append(f"{pid}: {e}")
                    continue
                conv = lambda v: None if v is None else round(v * taxa, 4)  # noqa: E731
                out[pid] = replace(cpm, cpm_compra_atual=conv(cpm.cpm_compra_atual),
                                   cpm_valor_uso=conv(cpm.cpm_valor_uso), moeda=moeda.upper())
            return out

        return Milheiro(converter(self.programas), converter(self.pontos), list(self.transferencias)), avisos

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
                    custo_deslocamento=float(item.get("custo_deslocamento") or 0),
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
        custo_bagagem_trecho={
            str(k).upper() if k != "padrao" else "padrao": float(v)
            for k, v in (d.get("custo_bagagem_trecho") or {}).items()
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
        valor_minimo_economia=float(d.get("valor_minimo_economia", 50)),
        conexao_curta_min=int(d.get("conexao_curta_min", 60)),
        conexao_bilhetes_separados_min=int(d.get("conexao_bilhetes_separados_min", 180)),
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
        moeda=str(v.get("moeda") or "").upper(),
    )


def milheiro_de_dict(d: dict[str, Any], registro=None) -> Milheiro:
    """Builds the miles table. Transfer pairs come from the program registry (ratio and minimum);
    the `transferencias` section only overrides them (current bonus, end date, or a custom ratio)."""
    from infra import programas as registro_mod

    reg = registro or registro_mod.carregar()
    # Program CPMs: new format under `programas:`; legacy files had them at the top level.
    brutos = dict(d.get("programas") or {})
    for pid in reg.milhas:
        if pid in d and pid not in brutos:
            brutos[pid] = d[pid]

    pares = {f"{p.origem}_{p.destino}": p for p in reg.parcerias}
    sobrescritas = d.get("transferencias") or {}
    transferencias = []
    for chave, par in pares.items():
        v = sobrescritas.get(chave) or {}
        transferencias.append(Transferencia(
            origem=par.origem, destino=par.destino,
            bonus_pct=float(v.get("bonus_pct") or 0), ate=str(v.get("ate") or ""),
            proporcao=float(v.get("proporcao") or par.proporcao),
            minimo=int(v["minimo"]) if v.get("minimo") is not None else par.minimo,
        ))
    for chave, v in sobrescritas.items():  # pairs not in the registry (custom)
        if chave in pares:
            continue
        v = v or {}
        origem = v.get("origem") or next((o for o in reg.pontos if chave.startswith(o + "_")), chave.partition("_")[0])
        destino = v.get("destino") or chave[len(origem) + 1:]
        transferencias.append(Transferencia(
            origem=origem, destino=destino, bonus_pct=float(v.get("bonus_pct") or 0), ate=str(v.get("ate") or ""),
            proporcao=float(v.get("proporcao") or 1.0), minimo=int(v.get("minimo") or 0),
        ))
    return Milheiro(
        programas={k: _cpm(v) for k, v in brutos.items()},
        pontos={k: _cpm(v) for k, v in (d.get("pontos") or {}).items()},
        transferencias=transferencias,
    )


def carregar_env(caminho: Path | None = None) -> None:
    """Load .env (KEY=value) without overriding variables already set in the environment."""
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


def _normalizar_milheiro(d: dict[str, Any]) -> dict[str, Any]:
    """Move legacy top-level program entries (old files) under `programas:`."""
    d = dict(d)
    programas = dict(d.get("programas") or {})
    for k in list(d):
        if k not in ("programas", "pontos", "transferencias") and isinstance(d[k], dict):
            programas.setdefault(k, d.pop(k))
    d["programas"] = programas
    return d


def mesclar_milheiro(modelo: dict[str, Any], usuario: dict[str, Any]) -> dict[str, Any]:
    """The user's table wins per program; programs only in the shipped table (e.g. added by a plugin update)
    are filled in from it."""
    modelo, usuario = _normalizar_milheiro(modelo), _normalizar_milheiro(usuario)
    return {
        "programas": {**modelo.get("programas", {}), **usuario.get("programas", {})},
        "pontos": {**(modelo.get("pontos") or {}), **(usuario.get("pontos") or {})},
        "transferencias": {**(modelo.get("transferencias") or {}), **(usuario.get("transferencias") or {})},
    }


def carregar_milheiro(caminho: Path | None = None) -> Milheiro:
    usuario = carregar_yaml(caminho or CONFIG_DIR / "milheiro.yaml")
    if caminho is not None:
        return milheiro_de_dict(usuario)
    return milheiro_de_dict(mesclar_milheiro(carregar_yaml(MODELOS_DIR / "milheiro.yaml"), usuario))
