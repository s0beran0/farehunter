"""Leitura, validação e gravação do config/perfil.yaml a partir das respostas da entrevista (/farehunter:profile).

O modelo nunca edita o YAML à mão: ele junta as respostas num JSON e chama `passagens perfil salvar`,
que valida, mescla com o perfil atual e regrava o arquivo com os comentários do modelo.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from infra.config import CONFIG_DIR, carregar_yaml, perfil_de_dict

ARQUIVO = CONFIG_DIR / "perfil.yaml"
PROGRAMAS = ("smiles", "latam_pass", "azul")
PADRAO: dict[str, Any] = {
    "configurado": False,
    "idioma": "pt",
    "passageiros_padrao": 1,
    "aeroportos_origem": [],
    "aeroportos_alternativos_origem": [],
    "aeroportos_alternativos_destino": [],
    "flex_dias_padrao": 3,
    "bagagem_despachada": False,
    "custo_bagagem_trecho_brl": {"G3": 130, "LA": 140, "AD": 200, "padrao": 180},
    "programas": {p: {"tem_conta": False, "clube": False, "categoria": ""} for p in PROGRAMAS},
    "pontos_programas": [],
    "valor_minimo_economia_brl": 50,
    "conexao_curta_min": 60,
    "limites": {"seats_aero_chamadas_dia": 1000, "seats_aero_mcp_chamadas_dia": 300, "playwright_paginas_por_execucao": 15},
}


class PerfilInvalido(ValueError):
    pass


def _mesclar(base: dict, novo: dict) -> dict:
    out = dict(base)
    for k, v in novo.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("custo_bagagem_trecho_brl",):
            out[k] = _mesclar(out[k], v)
        else:
            out[k] = v
    return out


def _iata(x: Any, campo: str) -> str:
    s = str(x).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", s):
        raise PerfilInvalido(f"{campo}: '{x}' não é um código IATA de 3 letras")
    return s


def _inteiro(x: Any, campo: str, minimo: int = 0) -> int:
    try:
        v = int(str(x).replace(".", "").replace("_", "")) if isinstance(x, str) else int(x)
    except (TypeError, ValueError) as e:
        raise PerfilInvalido(f"{campo}: '{x}' não é um número inteiro") from e
    if v < minimo:
        raise PerfilInvalido(f"{campo}: deve ser >= {minimo}")
    return v


def validar(d: dict) -> dict:
    """Normaliza e valida. Levanta PerfilInvalido com mensagem para mostrar ao usuário."""
    d = _mesclar(PADRAO, d)
    d["aeroportos_origem"] = [_iata(a, "aeroportos_origem") for a in d.get("aeroportos_origem") or []]
    for campo in ("aeroportos_alternativos_origem", "aeroportos_alternativos_destino"):
        alts = []
        for a in d.get(campo) or []:
            a = {"iata": a} if isinstance(a, str) else dict(a)
            alts.append({
                "iata": _iata(a.get("iata"), campo),
                "custo_deslocamento_brl": float(a.get("custo_deslocamento_brl") or 0),
                "observacao": str(a.get("observacao") or ""),
            })
        d[campo] = alts
    d["passageiros_padrao"] = _inteiro(d["passageiros_padrao"], "passageiros_padrao", 1)
    d["flex_dias_padrao"] = _inteiro(d["flex_dias_padrao"], "flex_dias_padrao", 0)
    if d["flex_dias_padrao"] > 10:
        raise PerfilInvalido("flex_dias_padrao: no máximo 10 dias")
    d["bagagem_despachada"] = bool(d["bagagem_despachada"])
    from i18n import normalizar

    d["idioma"] = normalizar(d.get("idioma"))
    for p, v in list(d["programas"].items()):
        if p not in PROGRAMAS:
            raise PerfilInvalido(f"programas: '{p}' desconhecido (use {', '.join(PROGRAMAS)})")
        if "saldo" in v:
            raise PerfilInvalido(
                f"programas.{p}.saldo: saldos não ficam no perfil (mudam o tempo todo); informe-os a cada busca"
            )
        d["programas"][p] = {
            "tem_conta": bool(v.get("tem_conta", False)),
            "clube": bool(v.get("clube", False)),
            "categoria": str(v.get("categoria") or ""),
        }
    d.pop("pontos_transferiveis", None)  # formato antigo, com saldos: descartado
    d["pontos_programas"] = list(dict.fromkeys(
        re.sub(r"\W+", "_", str(k).strip().lower()) for k in d.get("pontos_programas") or []
    ))
    d["valor_minimo_economia_brl"] = float(d["valor_minimo_economia_brl"])
    d["conexao_curta_min"] = _inteiro(d["conexao_curta_min"], "conexao_curta_min")
    perfil_de_dict(d)  # garante que o motor consegue carregar
    return d


def faltando(d: dict) -> list[str]:
    """O que ainda precisa ser perguntado para o perfil ser útil."""
    f = []
    if not d.get("configurado"):
        f.append("perfil nunca configurado (rode /farehunter:profile)")
    if not d.get("aeroportos_origem"):
        f.append("aeroportos_origem")
    return f


def _dump(v: Any) -> str:
    texto = yaml.safe_dump(v, allow_unicode=True, default_flow_style=True, sort_keys=False).strip()
    return texto.removesuffix("...").strip()  # escalares saem com marcador de fim de documento


def renderizar(d: dict) -> str:
    """Gera o YAML com os comentários explicativos (estrutura fixa, valores do usuário)."""
    alts_o = "\n".join(f"  - {_dump(a)}" for a in d["aeroportos_alternativos_origem"])
    alts_d = "\n".join(f"  - {_dump(a)}" for a in d["aeroportos_alternativos_destino"])
    progs = "\n".join(f"  {p + ':':<12} {_dump(v)}" for p, v in d["programas"].items())
    bag = "\n".join(f"  {k}: {v:g}" for k, v in d["custo_bagagem_trecho_brl"].items())
    limites = "\n".join(f"  {k}: {v}" for k, v in d["limites"].items())
    return f"""# Perfil do viajante. Preenchido pela entrevista do /farehunter:profile (atualizado em {date.today().isoformat()}).
# Saldos são informados por você; o agente nunca faz login para lê-los nem pede senha.
configurado: {_dump(d["configurado"])}
idioma: {d["idioma"]}                         # pt | en | es — idioma das conversas e do relatório

passageiros_padrao: {d["passageiros_padrao"]}
aeroportos_origem: {_dump(d["aeroportos_origem"])}
# Aeroportos aceitáveis, com custo de deslocamento POR TRECHO e POR PASSAGEIRO.
aeroportos_alternativos_origem:{(chr(10) + alts_o) if alts_o else " []"}
aeroportos_alternativos_destino:{(chr(10) + alts_d) if alts_d else " []"}
flex_dias_padrao: {d["flex_dias_padrao"]}

bagagem_despachada: {_dump(d["bagagem_despachada"])}           # se true, soma a mala às tarifas que não incluem
custo_bagagem_trecho_brl:           # 1 mala de 23 kg por trecho, comprada online (blogs, 2026)
{bag}

# Programas em que você tem conta. SALDOS NÃO FICAM AQUI: o /farehunter:search pergunta a cada busca,
# porque mudam com compras, transferências e vencimentos.
# clube = assinante do clube do programa; categoria = ex. Diamante, Ouro, Safira
programas:
{progs}

# programas de pontos de cartão em que você tem conta (livelo, esfera, inter_loop, atomos...)
pontos_programas: {_dump(d["pontos_programas"])}

valor_minimo_economia_brl: {d["valor_minimo_economia_brl"]:g}       # abaixo disso, estratégia trabalhosa vai para "também possível"
conexao_curta_min: {d["conexao_curta_min"]}               # conexões abaixo disso são sinalizadas como risco

limites:
{limites}
"""


def carregar_bruto(caminho: Path = ARQUIVO) -> dict:
    return _mesclar(PADRAO, carregar_yaml(caminho))


def salvar(respostas: dict, caminho: Path = ARQUIVO) -> tuple[dict, str]:
    """Mescla respostas no perfil atual, valida, marca configurado e grava. Retorna (perfil, yaml antigo)."""
    antigo = caminho.read_text(encoding="utf-8") if caminho.exists() else ""
    novo = validar(_mesclar(carregar_bruto(caminho), {**respostas, "configurado": True}))
    caminho.write_text(renderizar(novo), encoding="utf-8")
    return novo, antigo
