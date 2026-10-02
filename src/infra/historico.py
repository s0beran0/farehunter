"""History of collected prices in historico.csv (SPEC §7.3)."""

from __future__ import annotations

import csv
from pathlib import Path

from i18n import dinheiro, numero, t
from infra.config import DADOS
from normalizacao.schema import Opcao

ARQUIVO = DADOS / "historico.csv"
COLUNAS = [
    "coletado_em", "rota", "trecho", "data_ida", "data_volta", "fonte", "tipo", "programa",
    "cias", "voos", "preco", "milhas", "taxas", "moeda", "confirmado_ao_vivo",
]


def rota_de(o: Opcao) -> str:
    return f"{o.pernas[0].origem}-{o.pernas[0].destino}"


def _linha(o: Opcao) -> dict:
    return {
        "coletado_em": o.coletado_em,
        "rota": rota_de(o),
        "trecho": o.trecho,
        "data_ida": o.data_ida,
        "data_volta": o.data_volta or "",
        "fonte": o.fonte,
        "tipo": o.tipo,
        "programa": o.programa or "",
        "cias": "+".join(sorted(o.cias)),
        "voos": "+".join(v for p in o.pernas for v in p.voos),
        "preco": "" if o.preco is None else f"{o.preco:.2f}",
        "milhas": "" if o.milhas is None else o.milhas,
        "taxas": f"{o.taxas:.2f}",
        "confirmado_ao_vivo": int(o.confirmado_ao_vivo),
    }


def gravar(opcoes: list[Opcao], arquivo: Path = ARQUIVO, moeda: str = "") -> int:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    novo = not arquivo.exists() or arquivo.stat().st_size == 0
    with arquivo.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            w.writeheader()
        for o in opcoes:
            w.writerow({**_linha(o), "moeda": moeda})
    return len(opcoes)


def ler(arquivo: Path = ARQUIVO) -> list[dict]:
    if not arquivo.exists():
        return []
    with arquivo.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def comparar_com_anterior(opcoes: list[Opcao], arquivo: Path = ARQUIVO, moeda_atual: str = "") -> list[str]:
    """For each (route, date, type, program) in the current search, compare the lowest value with the previous collection's lowest."""
    linhas = ler(arquivo)
    atuais_ts = {o.coletado_em for o in opcoes}
    anteriores = [l for l in linhas if l["coletado_em"] not in atuais_ts]
    if not anteriores:
        return []

    def melhor(itens, campo):
        vals = [float(i[campo]) for i in itens if i.get(campo)]
        return min(vals) if vals else None

    grupos: dict[tuple, list[Opcao]] = {}
    for o in opcoes:
        grupos.setdefault((rota_de(o), o.trecho, o.data_ida, o.data_volta or "", o.tipo, o.programa or ""), []).append(o)

    msgs = []
    for (rota, trecho, ida, volta, tipo, prog), ops in sorted(grupos.items()):
        ant = [
            l for l in anteriores
            if (l["rota"], l["trecho"], l["data_ida"], l["data_volta"], l["tipo"], l["programa"])
            == (rota, trecho, ida, volta, tipo, prog)
        ]
        ant = [l for l in ant if not moeda_atual or l.get("moeda", "BRL") in ("", moeda_atual)]
        if not ant:
            continue
        ultima = max(l["coletado_em"] for l in ant)
        ant = [l for l in ant if l["coletado_em"][:13] == ultima[:13]]  # same collection (same hour)
        campo = "preco" if tipo == "dinheiro" else "milhas"
        antes = melhor(ant, campo)
        agora = min((o.preco if tipo == "dinheiro" else o.milhas) for o in ops)
        if antes is None or agora is None or antes == agora:
            continue
        direcao = t("hist.subiu") if agora > antes else t("hist.desceu")
        fmt = dinheiro if tipo == "dinheiro" else (lambda v: numero(int(v)))
        rotulo = f"{rota} {t('trecho.' + trecho)} {ida}" + (f"→{volta}" if volta else "") + (f" {prog}" if prog else "")
        msgs.append(t("hist.linha", rotulo=rotulo, direcao=direcao, antes=fmt(antes), agora=fmt(agora), data=ultima[:10]))
    return msgs
