"""Read, validate and write the user's perfil.yaml from the interview answers (/farehunter:profile).

The model never edits the YAML by hand: it collects the answers into JSON and calls `farehunter perfil salvar`,
which validates them, merges them into the current profile and rewrites the file with explanatory comments.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from infra.config import CONFIG_DIR, carregar_yaml, perfil_de_dict

ARQUIVO = CONFIG_DIR / "perfil.yaml"
# Typical checked-bag prices for Brazilian airlines, in BRL; only used when the profile currency is BRL.
BAGAGEM_BR = {"G3": 130, "LA": 140, "AD": 200, "padrao": 180}
PADRAO: dict[str, Any] = {
    "configurado": False,
    "idioma": "pt",
    "moeda": "BRL",
    "pais": "BR",
    "passageiros_padrao": 1,
    "aeroportos_origem": [],
    "aeroportos_alternativos_origem": [],
    "aeroportos_alternativos_destino": [],
    "flex_dias_padrao": 3,
    "bagagem_despachada": False,
    "custo_bagagem_trecho": dict(BAGAGEM_BR),
    "programas": {},
    "pontos_programas": [],
    "valor_minimo_economia": 50,
    "conexao_curta_min": 60,
    "conexao_bilhetes_separados_min": 180,
    "limites": {"seats_aero_chamadas_dia": 1000, "seats_aero_mcp_chamadas_dia": 300, "playwright_paginas_por_execucao": 15},
}
# Keys renamed when the engine became currency-neutral (old profiles keep working).
LEGADO = {"custo_bagagem_trecho_brl": "custo_bagagem_trecho", "valor_minimo_economia_brl": "valor_minimo_economia"}


class PerfilInvalido(ValueError):
    pass


def _mesclar(base: dict, novo: dict) -> dict:
    out = dict(base)
    for k, v in novo.items():
        k = LEGADO.get(k, k)
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("custo_bagagem_trecho",):
            out[k] = _mesclar(out[k], v)
        else:
            out[k] = v
    return out


def _iata(x: Any, campo: str) -> str:
    s = str(x).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", s):
        raise PerfilInvalido(f"{campo}: '{x}' is not a 3-letter IATA airport code")
    return s


def _inteiro(x: Any, campo: str, minimo: int = 0) -> int:
    try:
        v = int(str(x).replace(".", "").replace("_", "")) if isinstance(x, str) else int(x)
    except (TypeError, ValueError) as e:
        raise PerfilInvalido(f"{campo}: '{x}' is not a whole number") from e
    if v < minimo:
        raise PerfilInvalido(f"{campo}: must be >= {minimo}")
    return v


def _sugestoes(valor: str, opcoes) -> str:
    import difflib

    parecidos = difflib.get_close_matches(valor, list(opcoes), n=3, cutoff=0.5)
    return f" Did you mean: {', '.join(parecidos)}?" if parecidos else f" Known: {', '.join(sorted(opcoes))}."


def validar(d: dict) -> dict:
    """Normalize and validate. Raises PerfilInvalido with a message the model can explain to the user."""
    from i18n import normalizar
    from infra.programas import carregar

    reg = carregar()
    d = _mesclar(PADRAO, d)
    d["aeroportos_origem"] = [_iata(a, "aeroportos_origem") for a in d.get("aeroportos_origem") or []]
    for campo in ("aeroportos_alternativos_origem", "aeroportos_alternativos_destino"):
        alts = []
        for a in d.get(campo) or []:
            a = {"iata": a} if isinstance(a, str) else dict(a)
            alts.append({
                "iata": _iata(a.get("iata"), campo),
                "custo_deslocamento": float(a.get("custo_deslocamento", a.get("custo_deslocamento_brl")) or 0),
                "observacao": str(a.get("observacao") or ""),
            })
        d[campo] = alts
    d["passageiros_padrao"] = _inteiro(d["passageiros_padrao"], "passageiros_padrao", 1)
    d["flex_dias_padrao"] = _inteiro(d["flex_dias_padrao"], "flex_dias_padrao", 0)
    if d["flex_dias_padrao"] > 10:
        raise PerfilInvalido("flex_dias_padrao: at most 10 days")
    d["bagagem_despachada"] = bool(d["bagagem_despachada"])
    d["idioma"] = normalizar(d.get("idioma"))

    d["moeda"] = str(d.get("moeda") or "BRL").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", d["moeda"]):
        raise PerfilInvalido(f"moeda: '{d['moeda']}' is not an ISO 4217 currency code (e.g. BRL, USD, EUR)")
    d["pais"] = str(d.get("pais") or "BR").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", d["pais"]):
        raise PerfilInvalido(f"pais: '{d['pais']}' is not an ISO 3166 country code (e.g. BR, US, PT)")
    # Brazilian bag prices only make sense in BRL; in another currency the interview must ask for the user's own.
    if d["moeda"] != "BRL" and d["custo_bagagem_trecho"] == BAGAGEM_BR:
        d["custo_bagagem_trecho"] = {}

    for p, v in list(d["programas"].items()):
        if not reg.eh_milhas(p):
            raise PerfilInvalido(f"programas: unknown program '{p}'." + _sugestoes(p, reg.milhas))
        if "saldo" in (v or {}):
            raise PerfilInvalido(
                f"programas.{p}.saldo: balances are not stored in the profile (they change all the time); "
                "they are asked on every search"
            )
        v = v or {}
        d["programas"][p] = {
            "tem_conta": bool(v.get("tem_conta", False)),
            "clube": bool(v.get("clube", False)),
            "categoria": str(v.get("categoria") or ""),
        }
    d.pop("pontos_transferiveis", None)  # old format with balances: discarded
    pontos = list(dict.fromkeys(re.sub(r"\W+", "_", str(k).strip().lower()) for k in d.get("pontos_programas") or []))
    for p in pontos:
        if not reg.eh_pontos(p):
            raise PerfilInvalido(f"pontos_programas: unknown points program '{p}'." + _sugestoes(p, reg.pontos))
    d["pontos_programas"] = pontos
    d["valor_minimo_economia"] = float(d["valor_minimo_economia"])
    d["conexao_curta_min"] = _inteiro(d["conexao_curta_min"], "conexao_curta_min")
    d["conexao_bilhetes_separados_min"] = _inteiro(d["conexao_bilhetes_separados_min"], "conexao_bilhetes_separados_min", 60)
    perfil_de_dict(d)  # make sure the engine can load it
    return d


def faltando(d: dict) -> list[str]:
    """What still needs to be asked for the profile to be useful."""
    f = []
    if not d.get("configurado"):
        f.append("profile never configured (run /farehunter:profile)")
    if not d.get("aeroportos_origem"):
        f.append("aeroportos_origem")
    return f


def _dump(v: Any) -> str:
    texto = yaml.safe_dump(v, allow_unicode=True, default_flow_style=True, sort_keys=False).strip()
    return texto.removesuffix("...").strip()  # scalars come out with a document-end marker


def renderizar(d: dict) -> str:
    """Render the YAML with explanatory comments (fixed layout, user's values)."""
    alts_o = "\n".join(f"  - {_dump(a)}" for a in d["aeroportos_alternativos_origem"])
    alts_d = "\n".join(f"  - {_dump(a)}" for a in d["aeroportos_alternativos_destino"])
    progs = "\n".join(f"  {p + ':':<16} {_dump(v)}" for p, v in d["programas"].items())
    bag = "\n".join(f"  {k}: {v:g}" for k, v in d["custo_bagagem_trecho"].items())
    limites = "\n".join(f"  {k}: {v}" for k, v in d["limites"].items())
    return f"""# Traveller profile, filled in by the /farehunter:profile interview (updated {date.today().isoformat()}).
# Balances are NOT stored here: they are asked on every search. The agent never logs in or asks for passwords.
configurado: {_dump(d["configurado"])}
idioma: {d["idioma"]}                 # pt | en | es: language of the conversation and the report
moeda: {d["moeda"]}                # ISO 4217: every price is shown in this currency
pais: {d["pais"]}                  # ISO 3166: where you buy tickets (point of sale for cash fares)

passageiros_padrao: {d["passageiros_padrao"]}
aeroportos_origem: {_dump(d["aeroportos_origem"])}
# Acceptable alternative airports, with the cost to get there PER TRIP and PER PASSENGER (in `moeda`).
aeroportos_alternativos_origem:{(chr(10) + alts_o) if alts_o else " []"}
aeroportos_alternativos_destino:{(chr(10) + alts_d) if alts_d else " []"}
flex_dias_padrao: {d["flex_dias_padrao"]}

bagagem_despachada: {_dump(d["bagagem_despachada"])}     # if true, the bag fee is added to fares that don't include one
# One 23 kg bag per flight, bought online, by airline IATA code (+ padrao = default), in `moeda`.
custo_bagagem_trecho:{(chr(10) + bag) if bag else " {}"}

# Miles programs you have an account with (ids from config/programas.yaml).
# clube = you pay for the program's subscription club; categoria = your elite tier (e.g. Diamante, Gold)
programas:{(chr(10) + progs) if progs else " {}"}

# Transferable points programs you have (livelo, esfera, amex_mr, chase_ur...).
pontos_programas: {_dump(d["pontos_programas"])}

valor_minimo_economia: {d["valor_minimo_economia"]:g}   # below this saving, effortful strategies go to "also possible"
conexao_curta_min: {d["conexao_curta_min"]}         # connections shorter than this are flagged as a risk
conexao_bilhetes_separados_min: {d["conexao_bilhetes_separados_min"]}   # minimum time between two separate tickets (re-check bags, delays)

limites:
{limites}
"""


def carregar_bruto(caminho: Path = ARQUIVO) -> dict:
    return _mesclar(PADRAO, carregar_yaml(caminho))


def salvar(respostas: dict, caminho: Path = ARQUIVO) -> tuple[dict, str]:
    """Merge the answers into the current profile, validate, mark as configured and save. Returns (profile, old YAML)."""
    antigo = caminho.read_text(encoding="utf-8") if caminho.exists() else ""
    novo = validar(_mesclar(carregar_bruto(caminho), {**respostas, "configurado": True}))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(renderizar(novo), encoding="utf-8")
    return novo, antigo
