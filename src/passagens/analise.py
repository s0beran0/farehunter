"""Final analysis of a run: ranking, report (relatorio.md), ranking.json and price history."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import i18n
from calculo.ranking import Pedido, analisar
from calculo.relatorio import gerar_relatorio
from infra import historico, runs
from infra.config import carregar_milheiro, carregar_perfil
from normalizacao.schema import carregar_opcoes


def analisar_execucao(run: Path, top: int = 5, exploratorio: bool = False,
                      gravar_historico: bool = True) -> tuple[str, list[dict]]:
    """Rank the run (validated options only unless `exploratorio`) and write relatorio.md / ranking.json."""
    dados_pedido = json.loads((run / "pedido.json").read_text(encoding="utf-8"))
    i18n.definir(dados_pedido.pop("idioma", None))
    pedido = Pedido(**dados_pedido)
    i18n.definir_moeda(pedido.moeda)
    perfil = carregar_perfil()
    from infra.cambio import padrao as cambio_padrao

    milheiro, avisos_cambio = carregar_milheiro().na_moeda(pedido.moeda, cambio_padrao())
    saldos = runs.ler_saldos(run)
    aviso_saldos = runs.aplicar_saldos(perfil, saldos)
    brutos = []
    for arq in sorted((run / "opcoes").glob("*.json")):
        brutos.extend(json.loads(arq.read_text(encoding="utf-8")))
    opcoes, avisos_carga = carregar_opcoes(brutos)

    resultado = analisar(opcoes, pedido, perfil, milheiro, hoje=date.today(), somente_validadas=not exploratorio)
    resultado.avisos.extend(avisos_carga[:5])
    if aviso_saldos:
        resultado.avisos.insert(0, aviso_saldos)
    resultado.avisos.extend(f"FX: {x}" for x in avisos_cambio)
    st = runs.status(run)
    fontes_ok = [f for f, s in st.items() if s.get("ok")]
    falhas = {f: s.get("motivo") or "sem detalhe" for f, s in st.items() if not s.get("ok")}
    for f, s in st.items():
        if s.get("ok") and s.get("motivo"):
            resultado.avisos.append(f"{f}: {s['motivo']}")

    comparacao = historico.comparar_com_anterior(opcoes, moeda_atual=pedido.moeda) if gravar_historico else []
    texto = gerar_relatorio(resultado, fontes_ok, falhas, top=top, milheiro=milheiro, saldos=saldos)
    if comparacao:
        texto += f"\n\n{i18n.t('rel.desde_ultima')}\n\n" + "\n".join(f"- {m}" for m in comparacao[:15])
    (run / "relatorio.md").write_text(texto, encoding="utf-8")

    ranking = [
        {
            "posicao": i,
            "descricao": c.descricao(),
            "custo": c.custo,
            "economia": resultado.economia(c),
            "data_ida": c.data_ida,
            "data_volta": c.data_volta,
            "estrategias": sorted(c.estrategias),
            "riscos": c.riscos,
            "opcoes": [
                {"id": o.id, "fonte": o.fonte, "tipo": o.tipo, "programa": o.programa, "trecho": o.trecho,
                 "pernas": [{"origem": p.origem, "destino": p.destino, "data": p.data, "partida": p.partida,
                             "voos": p.voos} for p in o.pernas],
                 "preco": o.preco, "milhas": o.milhas, "taxas": o.taxas,
                 "confirmado_ao_vivo": o.confirmado_ao_vivo, "link": o.link}
                for o in c.opcoes
            ],
            "programas_milhas_cache": [o.programa for o in c.opcoes if o.tipo == "milhas" and not o.confirmado_ao_vivo],
        }
        for i, c in enumerate(resultado.principais[:20], 1)
    ]
    (run / "ranking.json").write_text(json.dumps(ranking, ensure_ascii=False, indent=1), encoding="utf-8")
    if gravar_historico:
        historico.gravar(opcoes, moeda=pedido.moeda)
    return texto, ranking
