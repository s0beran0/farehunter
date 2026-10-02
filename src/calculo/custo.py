"""Custo efetivo em BRL de uma combinação de opções (SPEC §5.1).

Regras:
- dinheiro:          preço × passageiros (+ bagagem por trecho, se o perfil pedir e a tarifa não incluir)
- milhas:            as milhas de cada programa são somadas na combinação e financiadas nesta ordem:
                       1. saldo do usuário, valorado a `cpm_valor_uso` (custo de oportunidade)
                       2. a fonte mais barata por milha entre: compra (cpm_compra_atual, respeitando
                          mínimo e múltiplo de compra) e transferência de pontos (cpm dos pontos de origem,
                          proporção e bônus vigente), limitada ao saldo de pontos
                     + taxas × passageiros
- aeroporto alt.:    + custo_deslocamento_brl × passageiros para cada perna que sai/chega num aeroporto alternativo
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from i18n import t
from infra.config import Milheiro, Perfil
from normalizacao.schema import Opcao

NOMES_PROGRAMA = {"smiles": "Smiles", "latam_pass": "LATAM Pass", "azul": "Azul Fidelidade"}


@dataclass
class Transferido:
    origem: str
    pontos: int
    milhas: int
    bonus_pct: float
    custo_brl: float


@dataclass
class Financiamento:
    programa: str
    milhas_necessarias: int
    milhas_do_saldo: int = 0
    custo_saldo_brl: float = 0.0
    milhas_compradas: int = 0
    custo_compra_brl: float = 0.0
    transferencias: list[Transferido] = field(default_factory=list)
    custo_brl: float | None = 0.0
    avisos: list[str] = field(default_factory=list)

    @property
    def estrategias(self) -> set[str]:
        s = set()
        if self.milhas_do_saldo:
            s.add("milhas_proprias")
        if self.milhas_compradas:
            s.add("comprar_milhas")
        if self.transferencias:
            s.add("transferir_pontos")
        return s


def _arredondar_compra(milhas: int, minimo: int, passo: int) -> int:
    passo = max(passo, 1)
    return max(minimo, math.ceil(milhas / passo) * passo)


def financiar_milhas(
    programa: str,
    milhas_necessarias: int,
    perfil: Perfil,
    milheiro: Milheiro,
    hoje: date,
    saldo_disponivel: int | None = None,
    pontos_disponiveis: dict[str, int] | None = None,
) -> Financiamento:
    """Decide como pagar `milhas_necessarias` de um programa. `pontos_disponiveis` é mutado (pool compartilhado)."""
    fin = Financiamento(programa=programa, milhas_necessarias=milhas_necessarias)
    cpm = milheiro.programas.get(programa)
    if saldo_disponivel is None:
        saldo = perfil.programas[programa].saldo if programa in perfil.programas else 0
    else:
        saldo = saldo_disponivel
    pontos = pontos_disponiveis if pontos_disponiveis is not None else dict(perfil.pontos_transferiveis)

    usar_saldo = min(saldo, milhas_necessarias)
    if usar_saldo:
        valor_uso = cpm.cpm_uso_efetivo if cpm else None
        if valor_uso is None:
            fin.avisos.append(t("aviso.sem_valor_saldo", programa=NOMES_PROGRAMA.get(programa, programa)))
            fin.custo_brl = None
            return fin
        fin.milhas_do_saldo = usar_saldo
        fin.custo_saldo_brl = usar_saldo / 1000 * valor_uso
    restante = milhas_necessarias - usar_saldo

    # Fontes para o restante, ordenadas por custo por milha.
    fontes: list[tuple[float, str, object]] = []
    if cpm and cpm.cpm_compra_atual is not None:
        fontes.append((cpm.cpm_compra_atual / 1000, "compra", None))
    for tr in milheiro.transferencias:
        if tr.destino != programa or pontos.get(tr.origem, 0) <= 0:
            continue
        cpm_pontos = milheiro.pontos.get(tr.origem)
        if cpm_pontos is None or cpm_pontos.cpm_uso_efetivo is None:
            fin.avisos.append(t("aviso.sem_cpm_pontos", origem=tr.origem))
            continue
        bonus = tr.bonus_vigente(hoje)
        custo_por_milha = cpm_pontos.cpm_uso_efetivo / 1000 * tr.proporcao / (1 + bonus / 100)
        fontes.append((custo_por_milha, "transferencia", tr))
    fontes.sort(key=lambda f: f[0])

    for _, tipo, tr in fontes:
        if restante <= 0:
            break
        if tipo == "compra":
            qtd = _arredondar_compra(restante, cpm.compra_minima, cpm.compra_passo)
            fin.milhas_compradas = qtd
            fin.custo_compra_brl = qtd / 1000 * cpm.cpm_compra_atual
            restante = 0
        else:
            bonus = tr.bonus_vigente(hoje)
            milhas_por_ponto = (1 + bonus / 100) / tr.proporcao
            pontos_necessarios = math.ceil(restante / milhas_por_ponto - 1e-9)
            usar = min(pontos_necessarios, pontos[tr.origem])
            if usar < tr.minimo:
                if pontos[tr.origem] < tr.minimo:
                    continue  # saldo de pontos abaixo do mínimo de transferência
                usar = tr.minimo  # transfere o mínimo; a sobra de milhas não é contada como economia
                if cpm and cpm.cpm_compra_atual is not None:
                    custo_transf = usar / 1000 * milheiro.pontos[tr.origem].cpm_uso_efetivo
                    qtd = _arredondar_compra(restante, cpm.compra_minima, cpm.compra_passo)
                    if qtd / 1000 * cpm.cpm_compra_atual <= custo_transf:
                        continue  # por causa do mínimo, comprar o que falta sai mais barato
            milhas_obtidas = min(restante, math.floor(usar * milhas_por_ponto + 1e-9))
            custo = usar / 1000 * milheiro.pontos[tr.origem].cpm_uso_efetivo
            pontos[tr.origem] -= usar
            fin.transferencias.append(Transferido(tr.origem, usar, milhas_obtidas, bonus, custo))
            restante -= milhas_obtidas

    if restante > 0:
        fin.avisos.append(t("aviso.faltam_milhas", programa=NOMES_PROGRAMA.get(programa, programa), milhas=restante))
        fin.custo_brl = None
        return fin

    fin.custo_brl = fin.custo_saldo_brl + fin.custo_compra_brl + sum(tr.custo_brl for tr in fin.transferencias)
    return fin


@dataclass
class CustoCombinacao:
    opcoes: list[Opcao]
    passageiros: int
    custo_brl: float | None
    custo_dinheiro_brl: float = 0.0
    custo_milhas_brl: float = 0.0
    taxas_brl: float = 0.0
    bagagem_brl: float = 0.0
    deslocamento_brl: float = 0.0
    financiamentos: list[Financiamento] = field(default_factory=list)
    estrategias: set[str] = field(default_factory=set)
    riscos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    datas_alternativas: list[tuple[str, str | None]] = field(default_factory=list)

    @property
    def data_ida(self) -> str:
        return self.opcoes[0].pernas[0].data

    @property
    def data_volta(self) -> str | None:
        ultima = self.opcoes[-1]
        if ultima.trecho == "ida_volta" or ultima.trecho == "volta":
            return ultima.pernas[-1].data
        return None

    @property
    def duracao_total_min(self) -> int:
        return sum(o.duracao_total_min for o in self.opcoes)

    @property
    def conexoes_total(self) -> int:
        return sum(o.conexoes_total for o in self.opcoes)

    @property
    def trabalhosa(self) -> bool:
        return bool(self.estrategias & {"comprar_milhas", "transferir_pontos", "aeroporto_alternativo"})

    @property
    def cias(self) -> list[str]:
        vistas: list[str] = []
        for o in self.opcoes:
            for p in o.pernas:
                if p.cia and p.cia not in vistas:
                    vistas.append(p.cia)
        return vistas

    def descricao(self) -> str:
        partes = []
        for o in self.opcoes:
            rotulo = t(f"trecho.{o.trecho}")
            if o.tipo == "dinheiro":
                partes.append(t("estrategia.dinheiro", trecho=rotulo))
            else:
                partes.append(t("estrategia.milhas", trecho=rotulo, programa=NOMES_PROGRAMA.get(o.programa, o.programa)))
        texto = " + ".join(partes)
        extras = []
        if "comprar_milhas" in self.estrategias:
            extras.append(t("extra.comprar"))
        if "transferir_pontos" in self.estrategias:
            extras.append(t("extra.transferir"))
        if "aeroporto_alternativo" in self.estrategias:
            extras.append(t("extra.aeroporto"))
        return texto + (f" ({', '.join(extras)})" if extras else "")


def custo_combinacao(
    opcoes: list[Opcao],
    perfil: Perfil,
    milheiro: Milheiro,
    passageiros: int,
    hoje: date,
) -> CustoCombinacao:
    res = CustoCombinacao(opcoes=opcoes, passageiros=passageiros, custo_brl=None)
    n = passageiros

    milhas_por_programa: dict[str, int] = {}
    for o in opcoes:
        if o.assentos_disponiveis is not None and o.assentos_disponiveis < n:
            res.avisos.append(t("aviso.assentos", id=o.id, assentos=o.assentos_disponiveis, pax=n))
            return res
        if o.tipo == "dinheiro":
            res.custo_dinheiro_brl += (o.preco_brl or 0) * n
            res.estrategias.add("dinheiro")
        else:
            milhas_por_programa[o.programa] = milhas_por_programa.get(o.programa, 0) + (o.milhas or 0) * n
            res.taxas_brl += o.taxas_brl * n
            if not o.confirmado_ao_vivo:
                res.riscos.append(t("risco.cache", programa=NOMES_PROGRAMA.get(o.programa, o.programa)))
            prog = perfil.programas.get(o.programa)
            if prog and (prog.clube or prog.categoria) and o.fonte == "seats_aero":
                res.riscos.append(t("risco.clube"))

        for p in o.pernas:
            if perfil.bagagem_despachada and not o.bagagem_inclusa:
                res.bagagem_brl += perfil.custo_bagagem(p.cia) * n
            for iata in (p.origem, p.destino):
                alt = perfil.alternativo(iata)
                if alt:
                    res.deslocamento_brl += alt.custo_deslocamento_brl * n
                    res.estrategias.add("aeroporto_alternativo")
            if any(e < perfil.conexao_curta_min for e in p.escalas_min):
                res.riscos.append(t("risco.conexao_curta", minutos=min(p.escalas_min), origem=p.origem, destino=p.destino))

    pontos_pool = dict(perfil.pontos_transferiveis)
    for programa, milhas in milhas_por_programa.items():
        fin = financiar_milhas(programa, milhas, perfil, milheiro, hoje, pontos_disponiveis=pontos_pool)
        res.financiamentos.append(fin)
        res.avisos.extend(fin.avisos)
        if fin.custo_brl is None:
            return res
        res.custo_milhas_brl += fin.custo_brl
        res.estrategias |= fin.estrategias

    if len(opcoes) > 1:
        cias_por_bilhete = [o.cias for o in opcoes]
        if len({frozenset(c) for c in cias_por_bilhete}) > 1:
            res.riscos.append(t("risco.bilhetes_separados"))

    res.riscos = list(dict.fromkeys(res.riscos))
    res.custo_brl = round(
        res.custo_dinheiro_brl + res.custo_milhas_brl + res.taxas_brl + res.bagagem_brl + res.deslocamento_brl, 2
    )
    return res


def cpm_equilibrio(preco_dinheiro_brl: float, taxas_brl: float, milhas: int) -> float | None:
    """CPM em que pagar com milhas empata com pagar em dinheiro: (tarifa - taxas) / milhas × 1000."""
    if not milhas:
        return None
    return round((preco_dinheiro_brl - taxas_brl) / milhas * 1000, 2)
