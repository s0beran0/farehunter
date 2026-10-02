"""Deterministic markdown report (SPEC §7.2), in the language set in i18n. The numbers come from here."""

from __future__ import annotations

from calculo.custo import NOMES_PROGRAMA, CustoCombinacao
from calculo.ranking import Resultado, descrever_veredito
from i18n import data_curta as _data_curta
from i18n import dinheiro as brl
from i18n import numero as mil
from i18n import t

NOMES_CIA = {"G3": "GOL", "LA": "LATAM", "JJ": "LATAM", "AD": "Azul", "2Z": "Voepass", "TP": "TAP", "CM": "Copa"}


def _cias(c: CustoCombinacao) -> str:
    return " / ".join(NOMES_CIA.get(x, x) for x in c.cias) or "—"


def _links(c: CustoCombinacao) -> str:
    links = []
    for o in c.opcoes:
        if o.link:
            rotulo = o.programa and NOMES_PROGRAMA.get(o.programa) or o.fonte
            links.append(f"[{rotulo}]({o.link})")
    return " · ".join(dict.fromkeys(links)) or "—"


def _detalhe_custo(c: CustoCombinacao) -> str:
    partes = []
    if c.custo_dinheiro:
        partes.append(t("det.tarifas", v=brl(c.custo_dinheiro)))
    for f in c.financiamentos:
        sub = []
        if f.milhas_do_saldo:
            sub.append(t("det.do_saldo", n=mil(f.milhas_do_saldo)))
        if f.milhas_compradas:
            sub.append(t("det.compradas", n=mil(f.milhas_compradas), v=brl(f.custo_compra)))
        for tr in f.transferencias:
            bonus = f" +{tr.bonus_pct:.0f}%" if tr.bonus_pct else ""
            sub.append(t("det.pontos", n=mil(tr.pontos), origem=tr.origem, bonus=bonus, v=brl(tr.custo)))
        partes.append(t("det.milhas", n=mil(f.milhas_necessarias), programa=NOMES_PROGRAMA.get(f.programa, f.programa),
                        partes=", ".join(sub)))
    if c.taxas:
        partes.append(t("det.taxas", v=brl(c.taxas)))
    if c.bagagem:
        partes.append(t("det.bagagem", v=brl(c.bagagem)))
    if c.deslocamento:
        partes.append(t("det.deslocamento", v=brl(c.deslocamento)))
    return "; ".join(partes)


def _observacoes(c: CustoCombinacao) -> str:
    obs = [_detalhe_custo(c)]
    if c.conexoes_total:
        obs.append(t("det.conexoes", n=c.conexoes_total))
    if c.datas_alternativas:
        outras = ", ".join(
            _data_curta(i) + (f"→{_data_curta(v)}" if v else "") for i, v in c.datas_alternativas[:4]
        )
        extra = t("det.e_mais", n=len(c.datas_alternativas) - 4) if len(c.datas_alternativas) > 4 else ""
        obs.append(t("det.mesmo_custo", datas=outras, extra=extra))
    obs.extend(f"⚠️ {r}" for r in c.riscos)
    return "<br>".join(x for x in obs if x)


SITES_PROGRAMA = {  # official sites for programs whose registry link is a deep-link builder
    "smiles": "https://www.smiles.com.br",
    "latam_pass": "https://latampass.latam.com",
    "azul": "https://www.voeazul.com.br/br/pt/azul-fidelidade",
}


def _site_compra(pid: str) -> str:
    from infra.programas import carregar

    p = carregar().programa(pid)
    if p and p.compra:
        return p.compra
    site = (p.link if p and p.link and p.link.startswith("http") else None) or SITES_PROGRAMA.get(pid, "")
    return t("plano.site_programa", site=site)


def _itinerario(o) -> str:
    partes = []
    for p in o.pernas:
        voos = " + ".join(p.voos) if p.voos else "—"
        horario = f"{p.partida or '?'}→{p.chegada or '?'}"
        partes.append(f"{voos} · {_data_curta(p.data)} {horario} · {p.origem}→{p.destino}")
    return "; ".join(partes)


def _plano(c: CustoCombinacao, pax: int) -> list[str]:
    """Step-by-step plan for the recommended combination: what to do, where, with which link and how much."""
    from infra.programas import carregar

    reg = carregar()
    passos: list[str] = []
    milhas_ops = [o for o in c.opcoes if o.tipo == "milhas"]
    for o in milhas_ops:
        texto = t("plano.conferir", programa=NOMES_PROGRAMA.get(o.programa, o.programa), itinerario=_itinerario(o),
                  milhas=mil(o.milhas), taxas=brl(o.taxas), link=o.link or "—")
        passos.append(texto)
    for f in c.financiamentos:
        nome = NOMES_PROGRAMA.get(f.programa, f.programa)
        for tr in f.transferencias:
            if tr.bonus_pct:
                bonus = t("plano.bonus", bonus=f"{tr.bonus_pct:.0f}", ate=tr.ate) if tr.ate else \
                    t("plano.bonus_sem_data", bonus=f"{tr.bonus_pct:.0f}")
            else:
                bonus = ""
            origem = reg.programa(tr.origem)
            passos.append(t("plano.transferir", pontos=mil(tr.pontos), origem=NOMES_PROGRAMA.get(tr.origem, tr.origem),
                            programa=nome, bonus=bonus, site=(origem.site if origem and origem.site else "—")))
        if f.milhas_compradas:
            cpm = f.custo_compra / f.milhas_compradas * 1000
            passos.append(t("plano.comprar_milhas", milhas=mil(f.milhas_compradas), programa=nome,
                            valor=brl(f.custo_compra), cpm=brl(cpm), link=_site_compra(f.programa)))
    for o in c.opcoes:
        trecho = t(f"trecho.{o.trecho}")
        if o.tipo == "milhas":
            texto = t("plano.emitir", programa=NOMES_PROGRAMA.get(o.programa, o.programa), trecho=trecho,
                      itinerario=_itinerario(o), milhas=mil(o.milhas * pax), taxas=brl(o.taxas * pax), pax=pax,
                      link=o.link or "—")
            if not o.taxas_confirmadas:
                texto += t("plano.taxa_nao_confirmada")
        else:
            texto = t("plano.comprar_dinheiro", trecho=trecho, itinerario=_itinerario(o), preco=brl((o.preco or 0) * pax),
                      pax=pax, link=o.link or "—")
        passos.append(texto)
    for grupo in c.bilhetes_por_direcao().values():
        for a, b in zip(grupo, grupo[1:]):
            chegada, saida = a.pernas[-1].chegada_dt(), b.pernas[0].partida_dt()
            if chegada and saida:
                passos.append(t("plano.bilhetes", hub=a.pernas[-1].destino, chegada=chegada.strftime("%H:%M"),
                                partida=saida.strftime("%H:%M"), horas=round((saida - chegada).total_seconds() / 3600, 1)))
    if c.bagagem:
        passos.append(t("plano.bagagem", valor=brl(c.bagagem)))
    passos.append(t("plano.total", custo=brl(c.custo), detalhe=_detalhe_custo(c)))
    passos.append(t("plano.conferencia"))
    return [f"{i}. {p}" for i, p in enumerate(passos, 1)]


def _datas(ida: str, volta: str | None) -> str:
    return _data_curta(ida) + (f" → {_data_curta(volta)}" if volta else "")


def _linha(i: int | str, c: CustoCombinacao, r: Resultado) -> str:
    eco = r.economia(c)
    eco_txt = t("rel.referencia") if c is r.referencia else (brl(eco) if eco is not None else "—")
    return (f"| {i} | {c.descricao()} | {_datas(c.data_ida, c.data_volta)} | {_cias(c)} | **{brl(c.custo)}** "
            f"| {eco_txt} | {_observacoes(c)} | {_links(c)} |")


def _matriz(r: Resultado) -> list[str]:
    if r.pedido.so_ida:
        datas = sorted({k[0] for k in r.matriz})
        if not datas:
            return [t("rel.grade_vazia")]
        melhor = min(r.matriz.values(), key=lambda c: c.custo)
        linhas = [t("rel.grade_cabecalho"), "|---|---|"]
        for d in datas:
            c = r.matriz[(d, None)]
            v = brl(c.custo)
            linhas.append(f"| {_data_curta(d)} | {'**' + v + '** ⭐' if c is melhor else v} |")
        return linhas
    idas = sorted({k[0] for k in r.matriz})
    voltas = sorted({k[1] for k in r.matriz if k[1]})
    if not idas or not voltas:
        return [t("rel.matriz_vazia")]
    melhor = min(r.matriz.values(), key=lambda c: c.custo)
    linhas = [f"| {t('rel.matriz_canto')} | " + " | ".join(_data_curta(v) for v in voltas) + " |",
              "|---" * (len(voltas) + 1) + "|"]
    for d in idas:
        celulas = []
        for v in voltas:
            c = r.matriz.get((d, v))
            if c is None:
                celulas.append("·")
            elif c is melhor:
                celulas.append(f"**{brl(c.custo)}** ⭐")
            else:
                celulas.append(brl(c.custo))
        linhas.append(f"| {_data_curta(d)} | " + " | ".join(celulas) + " |")
    linhas.append("")
    linhas.append(t("rel.matriz_legenda"))
    return linhas


def gerar_relatorio(
    r: Resultado,
    fontes_ok: list[str],
    fontes_falharam: dict[str, str],
    top: int = 5,
    milheiro=None,
    saldos: dict | None = None,
) -> str:
    p = r.pedido
    linhas: list[str] = []
    rota = f"{'/'.join(p.origens)} → {'/'.join(p.destinos)}"
    if p.datas_exatas():
        datas = _datas(p.data_ida, p.data_volta) + ("" if p.data_volta else t("rel.so_ida"))
        linhas.append(t("rel.titulo", rota=rota, datas=datas, pax=p.passageiros, flex=p.flex_dias))
    else:
        ini, fim = p.janela_ida()
        noites = "" if p.noites_min is None else (
            str(p.noites_min) if p.noites_max in (None, p.noites_min) else f"{p.noites_min}–{p.noites_max}")
        linhas.append(t("rel.titulo_janela", rota=rota, ini=_data_curta(ini.isoformat()), fim=_data_curta(fim.isoformat()),
                        noites=noites, pax=p.passageiros))
    linhas.append("")

    melhor = r.principais[0] if r.principais else (r.ranking[0] if r.ranking else None)
    if melhor is None:
        linhas.append(t("rel.nenhuma_validada", motivo=t("rel.sem_validada_motivo")))
    else:
        eco = r.economia(melhor)
        frase = t("rel.mais_barato", descricao=melhor.descricao(), datas=_datas(melhor.data_ida, melhor.data_volta),
                  cias=_cias(melhor), custo=brl(melhor.custo))
        if melhor is r.referencia:
            frase += t("rel.eh_referencia") if p.datas_exatas() else t("rel.eh_referencia_janela")
        elif eco is not None:
            frase += t("rel.economia", economia=brl(eco), referencia=brl(r.referencia.custo))
        else:
            frase += "."
        linhas.append(frase)
        linhas.append("")
        linhas.append(t("plano.titulo"))
        linhas.append("")
        linhas.extend(_plano(melhor, p.passageiros))
    linhas.append("")

    linhas.append(t("rel.top", n=top))
    linhas.append("")
    linhas.append(t("rel.cabecalho"))
    linhas.append("|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(r.principais[:top], 1):
        linhas.append(_linha(i, c, r))
    if r.referencia is not None and r.referencia not in r.principais[:top]:
        linhas.append(_linha("ref", r.referencia, r))
    linhas.append("")

    if r.tambem_possivel:
        linhas.append(t("rel.tambem"))
        linhas.append("")
        linhas.append(t("rel.cabecalho"))
        linhas.append("|---|---|---|---|---|---|---|---|")
        for i, c in enumerate(r.tambem_possivel[:3], 1):
            linhas.append(_linha(i, c, r))
        linhas.append("")

    linhas.append(t("rel.matriz"))
    linhas.append("")
    linhas.extend(_matriz(r))
    linhas.append("")

    linhas.append(t("rel.milhas"))
    linhas.append("")
    if not r.vereditos:
        linhas.append(t("rel.sem_resgates"))
    for v in r.vereditos:
        o = v.melhor_opcao
        linhas.append(t(
            "rel.resgate", programa=NOMES_PROGRAMA.get(v.programa, v.programa), milhas=mil(v.milhas),
            taxas=brl(v.taxas), data=_data_curta(o.data_ida), rota=f"{o.pernas[0].origem}→{o.pernas[-1].destino}",
            status=t("rel.status_vivo") if o.confirmado_ao_vivo else t("rel.status_cache"),
            preco=brl(v.preco_dinheiro_comparado), base=v.base_comparacao,
        ))
        linhas.append(f"  - {descrever_veredito(v)}")
    if milheiro is not None:
        premissas = [
            t("rel.premissa_item", programa=NOMES_PROGRAMA.get(prog, prog), compra=brl(cpm.cpm_compra_atual),
              uso=brl(cpm.cpm_uso_efetivo), data=cpm.atualizado_em or t("rel.sem_data"))
            for prog, cpm in milheiro.programas.items()
            if cpm.cpm_compra_atual is not None
        ]
        if premissas:
            linhas.append("")
            linhas.append(t("rel.premissas", lista="; ".join(premissas)))
    linhas.append("")

    if saldos and saldos.get("saldos"):
        lista = ", ".join(f"{NOMES_PROGRAMA.get(k, k)} {mil(v)}" for k, v in saldos["saldos"].items())
        linhas.append(t("rel.saldos", quando=saldos["informados_em"].replace("T", " "), lista=lista))
        linhas.append("")
    linhas.append(t("rel.fontes"))
    linhas.append("")
    linhas.append(t("rel.fontes_ok", lista=", ".join(fontes_ok) or t("rel.nenhuma_fonte")))
    for f, motivo in fontes_falharam.items():
        linhas.append(t("rel.fonte_falhou", fonte=f, motivo=motivo))
    for a in r.avisos:
        linhas.append(f"- ⚠️ {a}")
    linhas.append(t("rel.precos_mudam"))
    linhas.append("")

    linhas.append(t("rel.rodape"))
    return "\n".join(linhas)
