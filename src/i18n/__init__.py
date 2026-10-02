"""Report and engine texts in several languages (pt, en, es), plus currency-aware number formatting.

Usage: call `i18n.definir("en")` once (the CLI does it from the request/profile), then `t("key", **values)`.
An unknown language falls back to English; a key missing in a language falls back to Portuguese (reference language).
To add a language: copy the "en" block in mensagens.py, translate it and add its code to IDIOMAS.
"""

from __future__ import annotations

from datetime import date

from i18n.mensagens import MENSAGENS

IDIOMAS = ("pt", "en", "es")
_atual = "pt"
_moeda = "BRL"
SIMBOLOS = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "A$", "MXN": "MX$", "ARS": "AR$",
            "CLP": "CLP$", "COP": "COL$", "PEN": "S/", "UYU": "$U", "JPY": "¥", "CHF": "CHF", "NZD": "NZ$"}
SEM_CENTAVOS = {"JPY", "CLP", "COP", "KRW", "ARS"}


def normalizar(idioma: str | None) -> str:
    if not idioma:
        return "pt"
    base = idioma.strip().lower().replace("_", "-").split("-")[0]
    return base if base in IDIOMAS else "en"


def definir(idioma: str | None) -> str:
    global _atual
    _atual = normalizar(idioma)
    return _atual


def atual() -> str:
    return _atual


def definir_moeda(moeda: str | None) -> str:
    global _moeda
    _moeda = (moeda or "BRL").upper()
    return _moeda


def moeda() -> str:
    return _moeda


def t(chave: str, **kw) -> str:
    texto = MENSAGENS[_atual].get(chave)
    if texto is None:
        texto = MENSAGENS["pt"][chave]
    return texto.format(**kw) if kw else texto


def dinheiro(v: float | None) -> str:
    """Amount in the current search currency, formatted for the language: R$ 1.147,00 (pt/es) or R$1,147.00 (en)."""
    if v is None:
        return "—"
    simbolo = SIMBOLOS.get(_moeda, _moeda + " ")
    casas = 0 if _moeda in SEM_CENTAVOS else 2
    s = f"{v:,.{casas}f}"
    if _atual == "en":
        return f"{simbolo}{s}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{simbolo} {s}"


def numero(n: int) -> str:
    return f"{n:,}" if _atual == "en" else f"{n:,}".replace(",", ".")


def data_curta(d: str | None) -> str:
    if not d:
        return "—"
    dt = date.fromisoformat(d)
    dia = MENSAGENS[_atual]["_dias_semana"][dt.weekday()]
    if _atual == "en":
        return f"{dt:%b} {dt.day} ({dia})"
    return f"{dt:%d/%m} ({dia})"
