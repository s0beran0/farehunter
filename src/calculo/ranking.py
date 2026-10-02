"""Combinations, ranking, reference fare, date matrix and miles metrics (SPEC §5.2 and §5.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import product

from calculo.custo import NOMES_PROGRAMA, CustoCombinacao, cpm_equilibrio, custo_combinacao
from calculo.formato import brl
from i18n import t
from infra.config import Milheiro, Perfil
from normalizacao.schema import Opcao

MAX_POR_GRUPO = 25  # pruning: best standalone options per (leg, date, type, program)


@dataclass
class Pedido:
    origens: list[str]
    destinos: list[str]
    data_ida: str  # requested outbound date (or the start of the outbound window)
    data_volta: str | None = None  # None = one way
    flex_dias: int = 3
    passageiros: int = 1
    cabine: str = "economy"
    moeda: str = "BRL"  # ISO 4217; every amount in the search is in this currency
    pais: str = "BR"  # ISO 3166-1 alpha-2; point of sale for cash fares
    # Optional explicit windows ("leave between Nov 2 and Nov 26") and trip length ("5 to 7 nights").
    ida_de: str | None = None
    ida_ate: str | None = None
    noites_min: int | None = None
    noites_max: int | None = None
    hubs: list[str] = field(default_factory=list)  # connection airports allowed for separate tickets

    @property
    def so_ida(self) -> bool:
        return self.data_volta is None and self.noites_min is None

    def janela(self, centro: str) -> tuple[date, date]:
        c = date.fromisoformat(centro)
        return c - timedelta(days=self.flex_dias), c + timedelta(days=self.flex_dias)

    def janela_ida(self) -> tuple[date, date]:
        if self.ida_de:
            return date.fromisoformat(self.ida_de), date.fromisoformat(self.ida_ate or self.ida_de)
        return self.janela(self.data_ida)

    def janela_volta(self) -> tuple[date, date] | None:
        if self.so_ida:
            return None
        if self.noites_min is not None:
            ini, fim = self.janela_ida()
            return ini + timedelta(days=self.noites_min), fim + timedelta(days=self.noites_max or self.noites_min)
        return self.janela(self.data_volta)

    def duracao_ok(self, ida: str, volta: str) -> bool:
        noites = (date.fromisoformat(volta) - date.fromisoformat(ida)).days
        if noites < 0:
            return False
        if self.noites_min is not None and noites < self.noites_min:
            return False
        if self.noites_max is not None and noites > self.noites_max:
            return False
        return True

    def datas_exatas(self) -> bool:
        """True when the user asked for specific dates (the reference fare is then the one on those dates)."""
        return self.ida_de is None and self.noites_min is None


@dataclass
class VereditoPrograma:
    programa: str
    melhor_opcao: Opcao
    milhas: int
    taxas: float
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
        if self.referencia is None or self.referencia.custo is None or c.custo is None:
            return None
        return round(self.referencia.custo - c.custo, 2)


def _na_janela(d: str, ini: date, fim: date) -> bool:
    return ini <= date.fromisoformat(d) <= fim


def deduplicar(opcoes: list[Opcao]) -> list[Opcao]:
    """Same flight from different sources (e.g. Kiwi and Google): keep the cheapest."""
    melhores: dict[tuple, Opcao] = {}
    sem_chave: list[Opcao] = []
    for o in opcoes:
        if not all(p.voos for p in o.pernas):
            sem_chave.append(o)
            continue
        chave = (o.tipo, o.programa, o.trecho,
                 tuple((p.data, tuple(v.replace(" ", "").upper() for v in p.voos)) for p in o.pernas))
        valor = o.preco if o.tipo == "dinheiro" else (o.milhas, o.taxas)
        atual = melhores.get(chave)
        if atual is None:
            melhores[chave] = o
            continue
        valor_atual = atual.preco if atual.tipo == "dinheiro" else (atual.milhas, atual.taxas)
        if o.confirmado_ao_vivo != atual.confirmado_ao_vivo:
            if o.confirmado_ao_vivo:  # live data beats cached data, even if more expensive
                melhores[chave] = o
        elif valor < valor_atual:
            melhores[chave] = o
    return [*melhores.values(), *sem_chave]


def _podar(opcoes: list[Opcao], perfil: Perfil, milheiro: Milheiro, pedido: Pedido, hoje: date) -> list[Opcao]:
    grupos: dict[tuple, list[tuple[float, Opcao]]] = {}
    for o in opcoes:
        c = custo_combinacao([o], perfil, milheiro, pedido.passageiros, hoje)
        if c.custo is None:
            continue
        chave = (o.trecho, o.pernas[0].origem, o.pernas[-1].destino, o.data_ida, o.data_volta, o.tipo, o.programa)
        grupos.setdefault(chave, []).append((c.custo, o))
    podadas = []
    for itens in grupos.values():
        itens.sort(key=lambda x: x[0])
        podadas.extend(o for _, o in itens[:MAX_POR_GRUPO])
    return podadas


CONEXAO_BILHETES_SEPARADOS_MIN = 180  # minimum layover between separate tickets (re-check bags, possible delays)
CONEXAO_BILHETES_SEPARADOS_MAX = 24 * 60
MAX_POR_DATA = 6  # pruning: best options kept per date and direction (plus the best of each type/program)


def _compor(primeiras: list[Opcao], segundas: list[Opcao], minimo: int) -> list[tuple[Opcao, Opcao]]:
    """Pair a positioning flight with the main flight on separate tickets, when the connection is feasible."""
    pares = []
    por_aeroporto: dict[str, list[Opcao]] = {}
    for b in segundas:
        por_aeroporto.setdefault(b.pernas[0].origem, []).append(b)
    for a in primeiras:
        chegada = a.pernas[-1].chegada_dt()
        if chegada is None:
            continue
        for b in por_aeroporto.get(a.pernas[-1].destino, []):
            saida = b.pernas[0].partida_dt()
            if saida is None:
                continue
            espera = (saida - chegada).total_seconds() / 60
            if minimo <= espera <= CONEXAO_BILHETES_SEPARADOS_MAX:
                pares.append((a, b))
    return pares


def _melhores_por_data(itens: list[tuple[float, list[Opcao]]]) -> list[list[Opcao]]:
    """Keep, per departure date, the cheapest few plus the cheapest of each (type, program) signature."""
    por_data: dict[str, list[tuple[float, list[Opcao]]]] = {}
    for custo, grupo in itens:
        por_data.setdefault(grupo[0].pernas[0].data, []).append((custo, grupo))
    out = []
    for lista in por_data.values():
        lista.sort(key=lambda x: x[0])
        escolhidos, assinaturas = [], set()
        for custo, grupo in lista:
            assinatura = tuple((o.tipo, o.programa) for o in grupo)
            if len(escolhidos) < MAX_POR_DATA or assinatura not in assinaturas:
                escolhidos.append(grupo)
                assinaturas.add(assinatura)
        out.extend(escolhidos)
    return out


def gerar_combinacoes(opcoes: list[Opcao], pedido: Pedido, origens: set[str] | None = None,
                      destinos: set[str] | None = None, custo_avulso: dict[str, float] | None = None,
                      conexao_min: int = CONEXAO_BILHETES_SEPARADOS_MIN) -> list[list[Opcao]]:
    """Every way to make the trip: round-trip tickets, outbound × return, and separate tickets through a hub
    (origin→hub + hub→destination) in either direction. Honors date windows and trip length."""
    origens = origens or set(pedido.origens)
    destinos = destinos or set(pedido.destinos)
    custo_avulso = custo_avulso or {}
    ida_ini, ida_fim = pedido.janela_ida()

    def custo(grupo: list[Opcao]) -> float:
        return sum(custo_avulso.get(o.id, 0.0) for o in grupo)

    def direcao(trecho: str, de: set[str], para: set[str], ini: date, fim: date) -> list[list[Opcao]]:
        candidatas = [o for o in opcoes if o.trecho == trecho and _na_janela(o.data_ida, ini, fim)]
        completas = [[o] for o in candidatas if o.pernas[0].origem in de and o.pernas[-1].destino in para]
        primeiras = [o for o in candidatas if o.pernas[0].origem in de and o.pernas[-1].destino not in para]
        segundas = [o for o in candidatas if o.pernas[0].origem not in de and o.pernas[-1].destino in para]
        compostas = [[a, b] for a, b in _compor(primeiras, segundas, conexao_min)]
        return _melhores_por_data([(custo(g), g) for g in completas + compostas])

    # Positioning flights may leave the day before the window starts.
    idas = direcao("ida", origens, destinos, ida_ini - timedelta(days=1), ida_fim)
    idas = [g for g in idas if _na_janela(g[-1].pernas[0].data, ida_ini, ida_fim)]
    if pedido.so_ida:
        return idas

    vol_ini, vol_fim = pedido.janela_volta()
    voltas = direcao("volta", destinos, origens, vol_ini, vol_fim + timedelta(days=1))
    voltas = [g for g in voltas if _na_janela(g[0].pernas[0].data, vol_ini, vol_fim)]

    combos: list[list[Opcao]] = [
        [o] for o in opcoes
        if o.trecho == "ida_volta" and _na_janela(o.data_ida, ida_ini, ida_fim)
        and _na_janela(o.data_volta, vol_ini, vol_fim) and pedido.duracao_ok(o.data_ida, o.data_volta)
    ]
    for ida, volta in product(idas, voltas):
        data_ida = ida[-1].pernas[0].data  # main flight's date
        data_volta = volta[0].pernas[0].data
        chegada = ida[-1].pernas[-1].chegada_dt()
        saida = volta[0].pernas[0].partida_dt()
        if chegada and saida and saida <= chegada:
            continue
        if data_volta < data_ida or not pedido.duracao_ok(data_ida, data_volta):
            continue
        combos.append([*ida, *volta])
    return combos


def _chave_ordem(c: CustoCombinacao) -> tuple:
    return (c.custo, c.duracao_total_min or 10**9, c.conexoes_total)


def _so_dinheiro(c: CustoCombinacao) -> bool:
    return c.estrategias == {"dinheiro"}


def _mesmo_voo(a: Opcao, b: Opcao) -> bool:
    va = [v.replace(" ", "").upper() for p in a.pernas for v in p.voos]
    vb = [v.replace(" ", "").upper() for p in b.pernas for v in p.voos]
    return bool(va) and va == vb and [p.data for p in a.pernas] == [p.data for p in b.pernas]


def _mesma_rota_data(a: Opcao, b: Opcao) -> bool:
    return [(p.origem, p.destino, p.data) for p in a.pernas] == [(p.origem, p.destino, p.data) for p in b.pernas]


def comparar_com_dinheiro(op_milhas: Opcao, dinheiro: list[Opcao]) -> tuple[float | None, str]:
    """Find the cash fare comparable to an award: same flight > same airline/route/date > same route/date."""
    mesmos = [d for d in dinheiro if _mesmo_voo(op_milhas, d)]
    if mesmos:
        return min(d.preco for d in mesmos), t("base.mesmo_voo")
    mesma_rota = [d for d in dinheiro if _mesma_rota_data(op_milhas, d) and d.trecho == op_milhas.trecho]
    mesma_cia = [d for d in mesma_rota if d.cias & op_milhas.cias]
    if mesma_cia:
        return min(d.preco for d in mesma_cia), t("base.mesma_cia")
    if mesma_rota:
        return min(d.preco for d in mesma_rota), t("base.mesma_rota")
    return None, t("base.nenhuma")


def vereditos_milhas(opcoes: list[Opcao], milheiro: Milheiro) -> list[VereditoPrograma]:
    dinheiro = [o for o in opcoes if o.tipo == "dinheiro"]
    out = []
    for programa in dict.fromkeys(o.programa for o in opcoes if o.tipo == "milhas"):
        resgates = [o for o in opcoes if o.tipo == "milhas" and o.programa == programa]
        if not resgates:
            continue
        melhor_cpm: VereditoPrograma | None = None
        for r in resgates:
            preco, base = comparar_com_dinheiro(r, dinheiro)
            eq = cpm_equilibrio(preco, r.taxas, r.milhas) if preco is not None else None
            cpm = milheiro.programas.get(programa)
            compra = cpm.cpm_compra_atual if cpm else None
            v = VereditoPrograma(
                programa=programa,
                melhor_opcao=r,
                milhas=r.milhas,
                taxas=r.taxas,
                preco_dinheiro_comparado=preco,
                base_comparacao=base,
                cpm_equilibrio=eq,
                cpm_compra_atual=compra,
                compensa_comprar=(eq > compra) if (eq is not None and compra is not None) else None,
            )
            # "best award" = highest break-even CPM (each mile is worth more); without a comparison, fewest miles.
            if melhor_cpm is None:
                melhor_cpm = v
            elif (v.cpm_equilibrio or -1, -v.milhas) > (melhor_cpm.cpm_equilibrio or -1, -melhor_cpm.milhas):
                melhor_cpm = v
        out.append(melhor_cpm)
    return out


def agrupar_iguais(ordenadas: list[CustoCombinacao]) -> list[CustoCombinacao]:
    """Merge combinations with the same strategy, airlines and cost (only dates/flights differ): keep the first,
    with the other dates in `datas_alternativas`. Avoids a top 5 with the same option repeated."""
    vistos: dict[tuple, CustoCombinacao] = {}
    out = []
    for c in ordenadas:
        chave = (c.descricao(), tuple(c.cias), c.custo)
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
    somente_validadas: bool = False,
) -> Resultado:
    """Rank every combination. With `somente_validadas`, options that are not validated (Seats.aero cache not
    confirmed live, calendar prices without a specific flight) are left out: that is the mode for recommending."""
    hoje = hoje or date.today()
    avisos = milheiro.avisos_validade(hoje)
    base = deduplicar(opcoes)
    descartadas = [o for o in base if not o.validada] if somente_validadas else []
    if somente_validadas:
        base = [o for o in base if o.validada]
    podadas = _podar(base, perfil, milheiro, pedido, hoje)

    custo_avulso = {}
    for o in podadas:
        c = custo_combinacao([o], perfil, milheiro, pedido.passageiros, hoje)
        if c.custo is not None:
            custo_avulso[o.id] = c.custo
    origens = set(pedido.origens) | {a.iata for a in perfil.aeroportos_alternativos_origem}
    destinos = set(pedido.destinos) | {a.iata for a in perfil.aeroportos_alternativos_destino}

    avaliadas: list[CustoCombinacao] = []
    for combo in gerar_combinacoes(podadas, pedido, origens, destinos, custo_avulso,
                                   perfil.conexao_bilhetes_separados_min):
        c = custo_combinacao(combo, perfil, milheiro, pedido.passageiros, hoje)
        if c.custo is None:
            avisos.extend(c.avisos)
            continue
        avaliadas.append(c)
    avaliadas.sort(key=_chave_ordem)

    simples = [c for c in avaliadas if _so_dinheiro(c) and not c.estrategias & {"aeroporto_alternativo", "bilhetes_separados"}]
    if pedido.datas_exatas():
        simples = [c for c in simples if c.data_ida == pedido.data_ida and c.data_volta == pedido.data_volta]
    referencia = simples[0] if simples else None
    if referencia is None:
        avisos.append(t("aviso.sem_referencia"))
    if descartadas:
        avisos.append(t("aviso.nao_validadas", n=len(descartadas)))

    principais, tambem = [], []
    for c in agrupar_iguais(avaliadas):
        if referencia is not None and c.trabalhosa:
            economia = referencia.custo - c.custo
            if economia < perfil.valor_minimo_economia:
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
