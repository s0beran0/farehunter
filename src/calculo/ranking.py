"""Combinações, ranking, referência, matriz de datas e métricas de milhas (SPEC §5.2 e §5.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import product

from calculo.custo import NOMES_PROGRAMA, CustoCombinacao, cpm_equilibrio, custo_combinacao
from calculo.formato import brl
from i18n import t
from infra.config import Milheiro, Perfil
from normalizacao.schema import Opcao

MAX_POR_GRUPO = 25  # poda: melhores opções avulsas por (trecho, data, tipo, programa)


@dataclass
class Pedido:
    origens: list[str]
    destinos: list[str]
    data_ida: str
    data_volta: str | None = None  # None = só ida
    flex_dias: int = 3
    passageiros: int = 1
    cabine: str = "economy"

    @property
    def so_ida(self) -> bool:
        return self.data_volta is None

    def janela(self, centro: str) -> tuple[date, date]:
        c = date.fromisoformat(centro)
        return c - timedelta(days=self.flex_dias), c + timedelta(days=self.flex_dias)


@dataclass
class VereditoPrograma:
    programa: str
    melhor_opcao: Opcao
    milhas: int
    taxas_brl: float
    preco_dinheiro_comparado: float | None
    base_comparacao: str
    cpm_equilibrio: float | None
    cpm_compra_atual: float | None
    compensa_comprar: bool | None


@dataclass
class Resultado:
    pedido: Pedido
    ranking: list[CustoCombinacao]
    principais: list[CustoCombinacao]
    tambem_possivel: list[CustoCombinacao]
    referencia: CustoCombinacao | None
    matriz: dict[tuple[str, str | None], CustoCombinacao]
    vereditos: list[VereditoPrograma]
    avisos: list[str] = field(default_factory=list)

    def economia(self, c: CustoCombinacao) -> float | None:
        if self.referencia is None or self.referencia.custo_brl is None or c.custo_brl is None:
            return None
        return round(self.referencia.custo_brl - c.custo_brl, 2)


def _na_janela(d: str, ini: date, fim: date) -> bool:
    return ini <= date.fromisoformat(d) <= fim


def deduplicar(opcoes: list[Opcao]) -> list[Opcao]:
    """Mesmo voo vindo de fontes diferentes (ex.: Kiwi e Google): fica o mais barato."""
    melhores: dict[tuple, Opcao] = {}
    sem_chave: list[Opcao] = []
    for o in opcoes:
        if not all(p.voos for p in o.pernas):
            sem_chave.append(o)
            continue
        chave = (o.tipo, o.programa, o.trecho,
                 tuple((p.data, tuple(v.replace(" ", "").upper() for v in p.voos)) for p in o.pernas))
        valor = o.preco_brl if o.tipo == "dinheiro" else (o.milhas, o.taxas_brl)
        atual = melhores.get(chave)
        if atual is None:
            melhores[chave] = o
            continue
        valor_atual = atual.preco_brl if atual.tipo == "dinheiro" else (atual.milhas, atual.taxas_brl)
        if o.confirmado_ao_vivo != atual.confirmado_ao_vivo:
            if o.confirmado_ao_vivo:  # dado ao vivo vence o de cache, mesmo se mais caro
                melhores[chave] = o
        elif valor < valor_atual:
            melhores[chave] = o
    return [*melhores.values(), *sem_chave]


def _podar(opcoes: list[Opcao], perfil: Perfil, milheiro: Milheiro, pedido: Pedido, hoje: date) -> list[Opcao]:
    grupos: dict[tuple, list[tuple[float, Opcao]]] = {}
    for o in opcoes:
        c = custo_combinacao([o], perfil, milheiro, pedido.passageiros, hoje)
        if c.custo_brl is None:
            continue
        chave = (o.trecho, o.data_ida, o.data_volta, o.tipo, o.programa)
        grupos.setdefault(chave, []).append((c.custo_brl, o))
    podadas = []
    for itens in grupos.values():
        itens.sort(key=lambda x: x[0])
        podadas.extend(o for _, o in itens[:MAX_POR_GRUPO])
    return podadas


def gerar_combinacoes(opcoes: list[Opcao], pedido: Pedido) -> list[list[Opcao]]:
    ida_ini, ida_fim = pedido.janela(pedido.data_ida)
    idas = [o for o in opcoes if o.trecho == "ida" and _na_janela(o.data_ida, ida_ini, ida_fim)]
    if pedido.so_ida:
        return [[o] for o in idas]

    vol_ini, vol_fim = pedido.janela(pedido.data_volta)
    voltas = [o for o in opcoes if o.trecho == "volta" and _na_janela(o.data_ida, vol_ini, vol_fim)]
    combos: list[list[Opcao]] = [
        [o]
        for o in opcoes
        if o.trecho == "ida_volta"
        and _na_janela(o.data_ida, ida_ini, ida_fim)
        and _na_janela(o.data_volta, vol_ini, vol_fim)
    ]
    for ida, volta in product(idas, voltas):
        if date.fromisoformat(volta.data_ida) >= date.fromisoformat(ida.pernas[-1].data):
            combos.append([ida, volta])
    return combos


def _chave_ordem(c: CustoCombinacao) -> tuple:
    return (c.custo_brl, c.duracao_total_min or 10**9, c.conexoes_total)


def _so_dinheiro(c: CustoCombinacao) -> bool:
    return c.estrategias == {"dinheiro"}


def _mesmo_voo(a: Opcao, b: Opcao) -> bool:
    va = [v.replace(" ", "").upper() for p in a.pernas for v in p.voos]
    vb = [v.replace(" ", "").upper() for p in b.pernas for v in p.voos]
    return bool(va) and va == vb and [p.data for p in a.pernas] == [p.data for p in b.pernas]


def _mesma_rota_data(a: Opcao, b: Opcao) -> bool:
    return [(p.origem, p.destino, p.data) for p in a.pernas] == [(p.origem, p.destino, p.data) for p in b.pernas]


def comparar_com_dinheiro(op_milhas: Opcao, dinheiro: list[Opcao]) -> tuple[float | None, str]:
    """Acha a tarifa em dinheiro comparável a um resgate: mesmo voo > mesma cia/rota/data > mesma rota/data."""
    mesmos = [d for d in dinheiro if _mesmo_voo(op_milhas, d)]
    if mesmos:
        return min(d.preco_brl for d in mesmos), t("base.mesmo_voo")
    mesma_rota = [d for d in dinheiro if _mesma_rota_data(op_milhas, d) and d.trecho == op_milhas.trecho]
    mesma_cia = [d for d in mesma_rota if d.cias & op_milhas.cias]
    if mesma_cia:
        return min(d.preco_brl for d in mesma_cia), t("base.mesma_cia")
    if mesma_rota:
        return min(d.preco_brl for d in mesma_rota), t("base.mesma_rota")
    return None, t("base.nenhuma")


def vereditos_milhas(opcoes: list[Opcao], milheiro: Milheiro) -> list[VereditoPrograma]:
    dinheiro = [o for o in opcoes if o.tipo == "dinheiro"]
    out = []
    for programa in ("smiles", "latam_pass", "azul"):
        resgates = [o for o in opcoes if o.tipo == "milhas" and o.programa == programa]
        if not resgates:
            continue
        melhor_cpm: VereditoPrograma | None = None
        for r in resgates:
            preco, base = comparar_com_dinheiro(r, dinheiro)
            eq = cpm_equilibrio(preco, r.taxas_brl, r.milhas) if preco is not None else None
            cpm = milheiro.programas.get(programa)
            compra = cpm.cpm_compra_atual if cpm else None
            v = VereditoPrograma(
                programa=programa,
                melhor_opcao=r,
                milhas=r.milhas,
                taxas_brl=r.taxas_brl,
                preco_dinheiro_comparado=preco,
                base_comparacao=base,
                cpm_equilibrio=eq,
                cpm_compra_atual=compra,
                compensa_comprar=(eq > compra) if (eq is not None and compra is not None) else None,
            )
            # "melhor resgate" = maior CPM de equilíbrio (cada milha rende mais); sem comparação, menos milhas.
            if melhor_cpm is None:
                melhor_cpm = v
            elif (v.cpm_equilibrio or -1, -v.milhas) > (melhor_cpm.cpm_equilibrio or -1, -melhor_cpm.milhas):
                melhor_cpm = v
        out.append(melhor_cpm)
    return out


def agrupar_iguais(ordenadas: list[CustoCombinacao]) -> list[CustoCombinacao]:
    """Junta combinações com mesma estratégia, cias e custo (só mudam datas/voos): fica a primeira,
    com as outras datas em `datas_alternativas`. Evita um top 5 com a mesma opção repetida."""
    vistos: dict[tuple, CustoCombinacao] = {}
    out = []
    for c in ordenadas:
        chave = (c.descricao(), tuple(c.cias), c.custo_brl)
        if chave in vistos:
            primeira = vistos[chave]
            par = (c.data_ida, c.data_volta)
            if par != (primeira.data_ida, primeira.data_volta) and par not in primeira.datas_alternativas:
                primeira.datas_alternativas.append(par)
            continue
        vistos[chave] = c
        out.append(c)
    return out


def analisar(
    opcoes: list[Opcao],
    pedido: Pedido,
    perfil: Perfil,
    milheiro: Milheiro,
    hoje: date | None = None,
) -> Resultado:
    hoje = hoje or date.today()
    avisos = milheiro.avisos_validade(hoje)
    podadas = _podar(deduplicar(opcoes), perfil, milheiro, pedido, hoje)

    avaliadas: list[CustoCombinacao] = []
    for combo in gerar_combinacoes(podadas, pedido):
        c = custo_combinacao(combo, perfil, milheiro, pedido.passageiros, hoje)
        if c.custo_brl is None:
            avisos.extend(c.avisos)
            continue
        avaliadas.append(c)
    avaliadas.sort(key=_chave_ordem)

    exatas = [
        c for c in avaliadas if _so_dinheiro(c) and c.data_ida == pedido.data_ida and c.data_volta == pedido.data_volta
        and "aeroporto_alternativo" not in c.estrategias
    ]
    referencia = exatas[0] if exatas else None
    if referencia is None:
        avisos.append(t("aviso.sem_referencia"))

    principais, tambem = [], []
    for c in agrupar_iguais(avaliadas):
        if referencia is not None and c.trabalhosa:
            economia = referencia.custo_brl - c.custo_brl
            if economia < perfil.valor_minimo_economia_brl:
                tambem.append(c)
                continue
        principais.append(c)

    matriz: dict[tuple[str, str | None], CustoCombinacao] = {}
    for c in avaliadas:
        chave = (c.data_ida, c.data_volta)
        if chave not in matriz:
            matriz[chave] = c

    return Resultado(
        pedido=pedido,
        ranking=avaliadas,
        principais=principais,
        tambem_possivel=tambem,
        referencia=referencia,
        matriz=matriz,
        vereditos=vereditos_milhas(podadas, milheiro),
        avisos=list(dict.fromkeys(avisos)),
    )


def descrever_veredito(v: VereditoPrograma) -> str:
    nome = NOMES_PROGRAMA.get(v.programa, v.programa)
    if v.cpm_equilibrio is None:
        return t("veredito.sem_comparacao", programa=nome)
    if v.cpm_compra_atual is None:
        return t("veredito.sem_cpm", programa=nome, eq=brl(v.cpm_equilibrio))
    sim = t("sim") if v.compensa_comprar else t("nao")
    return t("veredito.completo", programa=nome, eq=brl(v.cpm_equilibrio), compra=brl(v.cpm_compra_atual), sim=sim)
