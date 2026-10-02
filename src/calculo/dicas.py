"""Timing tips for a search, from config/dicas.yaml (sourced research; no Google calls):
how far ahead to buy for this kind of trip, sales coming before the departure, high season, cheaper flying days."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from i18n import data_curta, t
from infra.config import MODELOS_DIR, carregar_yaml

# Countries of the Americas: a trip within them counts as "regional" (shorter flights, earlier sweet spot).
AMERICAS = set("AR BO BR CL CO EC GY PE PY SR UY VE MX US CA GT BZ SV HN NI CR PA CU DO HT JM BS PR TT BB AW CW".split())


def _tipo(pais_origem: str | None, pais_destino: str | None) -> str:
    if pais_origem and pais_destino and pais_origem == pais_destino:
        return "domestico_br" if pais_origem == "BR" else "domestico"
    if pais_origem in AMERICAS and pais_destino in AMERICAS:
        return "regional"
    return "longo"


def _ultima_sexta_novembro(ano: int) -> date:
    ultimo = date(ano, 11, calendar.monthrange(ano, 11)[1])
    return ultimo - timedelta(days=(ultimo.weekday() - 4) % 7)


def _proxima_ocorrencia(evento: dict, apos: date) -> date:
    for ano in (apos.year, apos.year + 1, apos.year + 2):
        if evento.get("regra") == "ultima_sexta_novembro":
            d = _ultima_sexta_novembro(ano)
        else:
            mes, dia = map(int, evento["data"].split("-"))
            d = date(ano, mes, dia)
        if d >= apos:
            return d
    return d


def _alta_temporada(base: dict, destino: str, pais_destino: str | None, quando: date) -> dict | None:
    for tmp in (base.get("temporadas") or {}).values():
        if destino not in (tmp.get("aeroportos") or []) and pais_destino not in (tmp.get("paises") or []):
            continue
        if quando.month in (tmp.get("meses") or []):
            return tmp
        for faixa in tmp.get("faixas") or []:
            ini, fim = faixa.split("..")
            if f"{quando:%m-%d}" >= ini and f"{quando:%m-%d}" <= fim:
                return tmp
    return None


def gerar_dicas(data_ida: str, data_volta: str | None, destino: str, pais_origem: str | None,
                pais_destino: str | None, pais_usuario: str, hoje: date, base: dict | None = None) -> list[str]:
    base = base or carregar_yaml(MODELOS_DIR / "dicas.yaml")
    ida = date.fromisoformat(data_ida)
    dias = (ida - hoje).days
    tipo = _tipo(pais_origem, pais_destino)
    janela = base["janelas"][tipo]
    alta = _alta_temporada(base, destino, pais_destino, ida)
    melhor = janela["alta_temporada"] if alta else janela["melhor"]
    dicas: list[str] = []

    rotulo = t(f"dica.tipo.{tipo}")
    if dias > janela["cedo"]:
        dicas.append(t("dica.cedo", dias=dias, tipo=rotulo, a=melhor[0], b=melhor[1], fonte=janela["fontes"].split(";")[0]))
    elif dias > melhor[1]:
        dicas.append(t("dica.um_pouco_cedo", dias=dias, tipo=rotulo, a=melhor[0], b=melhor[1]))
    elif dias >= max(melhor[0], janela["tarde"]):
        dicas.append(t("dica.na_janela", dias=dias, tipo=rotulo, a=melhor[0], b=melhor[1]))
    elif dias >= janela["tarde"]:
        dicas.append(t("dica.final_da_janela", dias=dias, tipo=rotulo, a=melhor[0], b=melhor[1]))
    else:
        dicas.append(t("dica.tarde", dias=dias))

    # Sales before the last good moment to buy (departure minus the start of the best window).
    limite = ida - timedelta(days=melhor[0])
    eventos = []
    for ev in (base.get("promocoes") or {}).get(pais_usuario, []):
        d = _proxima_ocorrencia(ev, hoje)
        if hoje <= d <= limite:
            eventos.append((d, ev))
    eventos.sort(key=lambda x: x[0])
    if eventos:
        lista = "; ".join(f"{ev['nome']} — {data_curta(d.isoformat())}" for d, ev in eventos[:4])
        milhas = any(ev["tipo"] in ("milhas", "pontos", "passagens_e_milhas") for _, ev in eventos[:4])
        dicas.append(t("dica.promocoes", lista=lista) + (t("dica.promocoes_milhas") if milhas else ""))

    if alta:
        extra = f" ({alta['obs_pt']})" if alta.get("obs_pt") else ""
        dicas.append(t("dica.alta_temporada", fonte=alta.get("fonte", "")) + extra)

    dias_semana = {ida.weekday()} | ({date.fromisoformat(data_volta).weekday()} if data_volta else set())
    if dias_semana & {4, 5, 6}:
        dicas.append(t("dica.dia_da_semana", pct=base["dia_da_semana"]["economia_pct"]))
    return dicas
