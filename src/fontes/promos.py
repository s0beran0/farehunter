"""Promoções de compra de milhas e bônus de transferência, lidas dos feeds RSS dos blogs (1x/dia, com cache).

Só extrai candidatos (título, link, data, % de bônus/desconto, CPM citado, programas). Quem decide o que
muda no milheiro.yaml é o usuário, depois de ver o diff (/farehunter:miles).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from infra.cache import Cache

FEEDS = {
    "pdp_transferencia": "https://passageirodeprimeira.com/categorias/promocoes/transferencia-de-pontos/feed/",
    "pdp_compra": "https://passageirodeprimeira.com/categorias/promocoes/compra-de-pontos/feed/",
    "pontospravoar": "https://pontospravoar.com/category/promocoes/feed/",
    "cartoesdecredito": "https://cartoesdecredito.me/feed/",
}
PROGRAMAS = {
    "smiles": r"smiles",
    "latam_pass": r"latam",
    "azul": r"azul|tudoazul",
    "livelo": r"livelo",
    "esfera": r"esfera",
    "inter_loop": r"inter\s*loop|loop",
}
UA = {"User-Agent": "farehunter/0.1 (personal use; RSS read once a day)"}


def _float_br(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def extrair(titulo: str) -> dict:
    t = titulo.lower()
    bonus = [int(x) for x in re.findall(r"(\d{2,3})\s*%\s*(?:de\s*)?b[oô]nus", t)]
    desconto = [int(x) for x in re.findall(r"(\d{2})\s*%\s*(?:de\s*)?(?:off|desconto)", t)]
    cpm = [_float_br(x) for x in re.findall(r"(?:milheiro|cpm)[^\d]{0,25}r\$\s*([\d.,]+)", t)]
    progs = [p for p, rx in PROGRAMAS.items() if re.search(rx, t)]
    tipo = "transferencia" if re.search(r"transfer", t) else ("compra" if re.search(r"compra|comprar|desconto|off", t) else "outro")
    return {
        "tipo": tipo,
        "programas": progs,
        "bonus_pct_max": max(bonus) if bonus else None,
        "desconto_pct_max": max(desconto) if desconto else None,
        "cpm_citado": min(cpm) if cpm else None,
        "ultimo_dia": bool(re.search(r"[úu]ltimo dia|termina hoje|acaba hoje", t)),
    }


def ler_feeds(cache: Cache | None = None, http: httpx.Client | None = None) -> tuple[list[dict], dict[str, str]]:
    cache = cache or Cache()
    http = http or httpx.Client(timeout=20, headers=UA, follow_redirects=True)
    itens, falhas = [], {}
    for nome, url in FEEDS.items():
        xml = cache.get("promos", url)
        if xml is None:
            try:
                r = http.get(url)
                r.raise_for_status()
                xml = r.text
                cache.set("promos", url, xml)
            except httpx.HTTPError as e:
                falhas[nome] = f"{type(e).__name__}: {e}"
                continue
        try:
            raiz = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
        except ET.ParseError as e:
            falhas[nome] = f"XML inválido: {e}"
            continue
        for item in raiz.iter("item"):
            titulo = (item.findtext("title") or "").strip()
            data = item.findtext("pubDate")
            try:
                data_iso = parsedate_to_datetime(data).date().isoformat() if data else None
            except (TypeError, ValueError):
                data_iso = None
            info = extrair(titulo)
            if not info["programas"] or (info["tipo"] == "outro" and not info["bonus_pct_max"]):
                continue
            itens.append({"feed": nome, "titulo": titulo, "link": item.findtext("link"), "data": data_iso, **info})
    itens.sort(key=lambda x: x["data"] or "", reverse=True)
    return itens, falhas
