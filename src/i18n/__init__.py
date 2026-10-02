"""Textos do relatório e do motor em vários idiomas (pt, en, es).

Uso: `i18n.definir("en")` uma vez (a CLI faz isso a partir do pedido/perfil) e `t("chave", **valores)`.
Idioma desconhecido cai em inglês; chave ausente num idioma cai no português (idioma de referência).
Para adicionar um idioma: copie o bloco "en" em mensagens.py, traduza e acrescente o código em IDIOMAS.
"""

from __future__ import annotations

from datetime import date

from i18n.mensagens import MENSAGENS

IDIOMAS = ("pt", "en", "es")
_atual = "pt"


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


def t(chave: str, **kw) -> str:
    texto = MENSAGENS[_atual].get(chave)
    if texto is None:
        texto = MENSAGENS["pt"][chave]
    return texto.format(**kw) if kw else texto


def dinheiro(v: float | None) -> str:
    """Valor em BRL no formato do idioma: R$ 1.147,00 (pt/es) ou R$1,147.00 (en)."""
    if v is None:
        return "—"
    if _atual == "en":
        return f"R${v:,.2f}"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


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
