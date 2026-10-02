"""A search run directory: runs/<id>/{pedido.json, status.json, opcoes/<fonte>.json, bruto/}."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from infra.config import DADOS
from normalizacao.schema import Opcao

RUNS_DIR = DADOS / "runs"
_TRAVA = threading.RLock()  # collectors run in parallel threads and share status.json / opcoes files


def ler_pedido(run: Path) -> dict:
    return json.loads((run / "pedido.json").read_text(encoding="utf-8"))


def status(run: Path) -> dict:
    arq = run / "status.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def _gravar_status(run: Path, fonte: str, ok: bool, motivo: str = "", n: int = 0) -> None:
    st = status(run)
    st[fonte] = {"ok": ok, "motivo": motivo, "opcoes": n, "em": datetime.now().isoformat(timespec="seconds")}
    (run / "status.json").write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")


def registrar_opcoes(run: Path, fonte: str, opcoes: list[Opcao], aviso: str = "") -> int:
    """Append options (deduplicated by id) and mark the source as OK. Returns how many were new."""
    with _TRAVA:
        destino = run / "opcoes" / f"{fonte}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        existentes = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else []
        vistos = {o["id"] for o in existentes}
        novos = [o.to_dict() for o in opcoes if o.id not in vistos]
        destino.write_text(json.dumps(existentes + novos, ensure_ascii=False, indent=1), encoding="utf-8")
        anterior = status(run).get(fonte, {})
        motivo = "; ".join(x for x in [anterior.get("motivo", ""), aviso] if x)
        _gravar_status(run, fonte, True, motivo=motivo, n=len(existentes) + len(novos))
        return len(novos)


def registrar_falha(run: Path, fonte: str, motivo: str) -> None:
    """Full failure if the source has returned nothing in this run yet; otherwise it becomes a partial-failure warning."""
    with _TRAVA:
        st = status(run).get(fonte)
        if st and st.get("ok") and st.get("opcoes"):
            motivo_total = "; ".join(x for x in [st.get("motivo", ""), f"parcial: {motivo}"] if x)
            _gravar_status(run, fonte, True, motivo=motivo_total, n=st["opcoes"])
        else:
            anterior = (st or {}).get("motivo", "")
            motivos = [m for m in anterior.split("; ") if m] if anterior else []
            if motivo not in motivos:
                motivos.append(motivo)
            _gravar_status(run, fonte, False, motivo="; ".join(motivos[-5:]))


def _arquivos_opcoes(run: Path):
    return sorted((run / "opcoes").glob("*.json"))


def buscar_opcao(run: Path, opcao_id: str) -> tuple[Path, dict] | None:
    for arq in _arquivos_opcoes(run):
        for o in json.loads(arq.read_text(encoding="utf-8")):
            if o["id"] == opcao_id:
                return arq, o
    return None


def confirmar(run: Path, opcao_id: str, fonte_confirmacao: str, milhas: int | None = None,
              taxas: float | None = None, preco: float | None = None, indisponivel: bool = False,
              link: str | None = None, obs: str | None = None) -> dict:
    """Result of the live (Playwright) confirmation of a cached option.
    Unavailable → the option is removed from the run. Available → values updated and `confirmado_ao_vivo=True`."""
    with _TRAVA:
        achado = buscar_opcao(run, opcao_id)
        if achado is None:
            raise KeyError(f"option {opcao_id} not found in {run}")
        arq, _ = achado
        dados = json.loads(arq.read_text(encoding="utf-8"))
        novos, resultado = [], {}
        for o in dados:
            if o["id"] != opcao_id:
                novos.append(o)
                continue
            if indisponivel:
                resultado = {"id": opcao_id, "removida": True}
                continue
            if milhas is not None:
                o["milhas"] = milhas
            if taxas is not None:
                o["taxas"] = taxas
                o["taxas_confirmadas"] = True
            if preco is not None:
                o["preco"] = preco
            if link:
                o["link"] = link
            o["confirmado_ao_vivo"] = True
            if obs:
                o.setdefault("observacoes", []).append(obs)
            o.setdefault("observacoes", []).append(
                f"confirmado ao vivo via {fonte_confirmacao} em {datetime.now().isoformat(timespec='minutes')}"
            )
            novos.append(o)
            resultado = {"id": opcao_id, "atualizada": o}
        arq.write_text(json.dumps(novos, ensure_ascii=False, indent=1), encoding="utf-8")
        return resultado


def gravar_saldos(run: Path, saldos: dict[str, int]) -> dict:
    """Balances only apply to this run (the profile never stores balances: they are volatile)."""
    with _TRAVA:
        registro = {"informados_em": datetime.now().isoformat(timespec="minutes"), "saldos": saldos}
        (run / "saldos.json").write_text(json.dumps(registro, indent=2), encoding="utf-8")
        return registro


def ler_saldos(run: Path) -> dict | None:
    arq = run / "saldos.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def aplicar_saldos(perfil, registro: dict | None) -> str | None:
    """Inject the run's balances into the Perfil. Returns a warning when no balances were given."""
    from infra.config import SaldoPrograma
    from infra.programas import carregar

    if registro is None:
        from i18n import t

        return t("aviso.saldos_nao_informados")
    for nome, valor in registro["saldos"].items():
        if carregar().eh_milhas(nome):
            perfil.programas.setdefault(nome, SaldoPrograma()).saldo = valor
        else:
            perfil.pontos_transferiveis[nome] = valor
    return None
