"""Buy-miles promotions and transfer bonuses, read from blog RSS feeds (once a day, cached).

Feeds are grouped by region (the user's country picks them; `--regiao` overrides). Only extracts candidates
(title, link, date, bonus/discount %, quoted CPM, programs). The user decides what changes in milheiro.yaml,
after seeing the diff (/farehunter:miles). Titles may be in Portuguese or English.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from infra.cache import Cache

FEEDS = {
    "br": {
        "pdp_transferencia": "https://passageirodeprimeira.com/categorias/promocoes/transferencia-de-pontos/feed/",
        "pdp_compra": "https://passageirodeprimeira.com/categorias/promocoes/compra-de-pontos/feed/",
        "pontospravoar": "https://pontospravoar.com/category/promocoes/feed/",
        "cartoesdecredito": "https://cartoesdecredito.me/feed/",
    },
    "us": {
        "thepointsguy": "https://thepointsguy.com/feed/",
        "frequentmiler": "https://frequentmiler.com/feed/",
        "onemileatatime": "https://onemileatatime.com/feed/",
        "viewfromthewing": "https://viewfromthewing.com/feed/",
        "upgradedpoints": "https://upgradedpoints.com/feed/",
    },
    "uk": {"headforpoints": "https://www.headforpoints.com/feed/"},
    "au": {"pointhacks": "https://www.pointhacks.com.au/feed/"},
    "ca": {"princeoftravel": "https://princeoftravel.com/feed/"},
}
# Country → feed regions. Anyone outside these gets the US feeds, which cover global programs.
REGIOES_POR_PAIS = {"BR": ["br"], "US": ["us"], "GB": ["uk", "us"], "AU": ["au", "us"], "CA": ["ca", "us"]}
# Pages that list every live transfer bonus (for the promos researcher to read with WebFetch).
RASTREADORES_BONUS = [
    "https://frequentmiler.com/current-point-transfer-bonuses/",
    "https://thepointsguy.com/loyalty-programs/current-transfer-bonuses/",
]
# Program aliases as they appear in post titles (lowercase regex). Registry names are added on top of these.
ALIASES = {
    "smiles": r"smiles", "latam_pass": r"latam", "azul": r"azul|tudoazul",
    "livelo": r"livelo", "esfera": r"esfera", "inter_loop": r"inter\s*loop", "atomos": r"[áa]tomos",
    "united": r"united|mileageplus", "american": r"american airlines|aadvantage", "delta": r"delta|skymiles",
    "alaska": r"alaska|atmos", "aeroplan": r"aeroplan|air canada", "flyingblue": r"flying blue|air france|klm",
    "british": r"british airways|\bavios\b", "iberia": r"iberia", "qatar": r"qatar", "virginatlantic": r"virgin atlantic",
    "lifemiles": r"lifemiles|avianca", "turkish": r"turkish|miles\s*&\s*smiles", "emirates": r"emirates|skywards",
    "etihad": r"etihad", "singapore": r"krisflyer|singapore airlines", "asiamiles": r"asia miles|cathay",
    "lufthansa": r"miles\s*&\s*more|lufthansa", "qantas": r"qantas", "velocity": r"velocity",
    "amex_mr": r"amex|membership rewards|american express", "chase_ur": r"chase|ultimate rewards",
    "citi_ty": r"citi\b|thankyou", "capitalone": r"capital one", "bilt": r"bilt", "wellsfargo": r"wells fargo",
}
UA = {"User-Agent": "farehunter/0.3 RSS feed reader (personal use; +https://github.com/s0beran0/farehunter)"}


def regioes_para(pais: str | None) -> list[str]:
    return REGIOES_POR_PAIS.get((pais or "").upper(), ["us"])


def _numero(s: str) -> float:
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def extrair(titulo: str) -> dict:
    t = titulo.lower()
    bonus = [int(x) for x in re.findall(r"(\d{2,3})\s*%\s*(?:de\s*)?(?:[a-z]+\s+){0,2}?b[oô]nus", t)]
    desconto = [int(x) for x in re.findall(r"(\d{2})\s*%\s*(?:de\s*)?(?:off|desconto|discount)", t)]
    cpm = [_numero(x) for x in re.findall(r"(?:milheiro|cpm)[^\d]{0,25}r\$\s*([\d.,]+)", t)]
    centavos = [_numero(x) for x in re.findall(r"([\d.]+)\s*(?:cents?|¢)\s*(?:each|(?:per|a|/)\s*(?:mile|point))", t)]
    progs = [p for p, rx in ALIASES.items() if re.search(rx, t)]
    if re.search(r"transfer", t):
        tipo = "transferencia"
    elif re.search(r"compra|comprar|desconto|\bbuy\b|purchase|\bsale\b|discount|\boff\b", t):
        tipo = "compra"
    else:
        tipo = "outro"
    return {
        "tipo": tipo,
        "programas": progs,
        "bonus_pct_max": max(bonus) if bonus else None,
        "desconto_pct_max": max(desconto) if desconto else None,
        "cpm_citado": min(cpm) if cpm else None,  # BRL per 1,000 (Brazilian posts)
        "centavos_por_milha": min(centavos) if centavos else None,  # US cents per mile (US posts)
        "ultimo_dia": bool(re.search(r"[úu]ltimo dia|termina hoje|acaba hoje|last day|ends today|final day|ending soon", t)),
    }


def ler_feeds(regioes: list[str] | None = None, cache: Cache | None = None,
              http: httpx.Client | None = None) -> tuple[list[dict], dict[str, str]]:
    cache = cache or Cache()
    http = http or httpx.Client(timeout=20, headers=UA, follow_redirects=True)
    itens, falhas = [], {}
    feeds = {nome: url for r in (regioes or ["br", "us"]) for nome, url in FEEDS.get(r, {}).items()}
    for nome, url in feeds.items():
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
            falhas[nome] = f"invalid XML: {e}"
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
