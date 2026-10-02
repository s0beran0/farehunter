"""One command for a whole search: collect in parallel, validate what could win, analyse.

The model calls `farehunter recomendar --run RUN` once instead of orchestrating many steps and subagents,
which is what used to cost most of the tokens. Google Flights gets a small call budget (HTTP 429 risk) and is
used only where nothing else has the data (airlines' own round-trip fares, finalists' details).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fontes import coleta, google_flights
from infra.runs import confirmar, ler_pedido, status

ORCAMENTO_GOOGLE = 12  # real Google calls per search (cache hits are free)
RODADAS_VALIDACAO = 3


def _internacional(p: dict) -> bool:
    from fontes.rotas import pais_do_aeroporto

    origem = pais_do_aeroporto(p["origens"][0]) or p.get("pais")
    destino = pais_do_aeroporto(p["destinos"][0])
    return bool(destino) and destino != origem


def _confirmar_automatico(run: Path, ids: list[str]) -> tuple[list[str], list[str]]:
    """Live-check awards in code when an extractor exists for the program (no model tokens).
    Returns (confirmed ids, ids still needing the browser subagent)."""
    try:
        from fontes import confirmacao
    except ImportError:
        return [], ids
    feitos, pendentes = [], []
    for oid in ids:
        r = confirmacao.confirmar_opcao(run, oid)
        if r is None:
            pendentes.append(oid)
            continue
        confirmar(run, oid, r["via"], milhas=r.get("milhas"), taxas=r.get("taxas"),
                  indisponivel=r.get("indisponivel", False), obs=r.get("obs"))
        feitos.append(oid)
    return feitos, pendentes


def recomendar(run: Path, posicionamento: str = "auto", orcamento_google: int = ORCAMENTO_GOOGLE,
               gravar_historico: bool = True) -> dict:
    from passagens.analise import analisar_execucao

    p = ler_pedido(run)
    google_flights.definir_orcamento(orcamento_google)
    usar_hubs = posicionamento == "sim" or (posicionamento == "auto" and _internacional(p))

    etapas = {"dinheiro": coleta.coletar_dinheiro, "datas": coleta.coletar_datas, "milhas": coleta.coletar_milhas}
    if usar_hubs:
        etapas["posicionamento"] = coleta.coletar_posicionamento
    with ThreadPoolExecutor(max_workers=len(etapas)) as ex:
        futuros = {nome: ex.submit(fn, run) for nome, fn in etapas.items()}
    coletado = {}
    for nome, f in futuros.items():
        try:
            r = f.result()
            coletado[nome] = r if nome != "posicionamento" else {
                "origem": r.get("origem"), "hubs": [h["iata"] for h in r.get("hubs", []) if h.get("direto")]}
        except Exception as e:  # a collector crashing must not stop the search
            coletado[nome] = f"error: {type(e).__name__}: {e}"

    confirmadas, pendentes_navegador, detalhadas = [], [], 0
    for _ in range(RODADAS_VALIDACAO):
        pend = coleta.pendencias(run, maximo=4)
        if pend["pronto"]:
            break
        mudou = False
        if pend["detalhar"]:
            detalhadas += coleta.coletar_detalhes(run, pend["detalhar"])["detalhados"]
            mudou = True
        novos = [i for i in pend["confirmar_milhas"] if i not in confirmadas and i not in pendentes_navegador]
        if novos:
            feitos, faltam = _confirmar_automatico(run, novos)
            confirmadas += feitos
            pendentes_navegador += faltam
            mudou = mudou or bool(feitos)
        if not mudou:
            break

    texto, ranking = analisar_execucao(run, top=3, gravar_historico=gravar_historico)
    st = status(run)
    usadas = orcamento_google - (google_flights.orcamento_restante() or 0)
    google_flights.definir_orcamento(None)
    return {
        "relatorio": str(run / "relatorio.md"),
        "recomendacao": next((l for l in texto.splitlines() if l.startswith("**")), ""),
        "coletado": coletado,
        "validacao": {"detalhadas": detalhadas, "milhas_confirmadas": len(confirmadas),
                      "precisam_navegador": pendentes_navegador},
        "fontes_falharam": {f: s.get("motivo", "")[:200] for f, s in st.items() if not s.get("ok")},
        "google_chamadas": usadas,
    }
