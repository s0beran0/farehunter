from datetime import date

import pytest

from calculo.custo import cpm_equilibrio, custo_combinacao, financiar_milhas
from calculo.ranking import Pedido, analisar, comparar_com_dinheiro
from calculo.relatorio import gerar_relatorio
from infra.config import milheiro_de_dict, perfil_de_dict
from normalizacao.schema import Opcao, Perna, carregar_opcoes

HOJE = date(2026, 10, 2)


def perfil(**kw):
    base = {
        "passageiros_padrao": 1,
        "aeroportos_origem": ["GRU"],
        "programas": {"smiles": {"saldo": 0}, "latam_pass": {"saldo": 0}, "azul": {"saldo": 0}},
        "pontos_transferiveis": {"livelo": 0, "esfera": 0},
        "valor_minimo_economia": 50,
    }
    base.update(kw)
    return perfil_de_dict(base)


def milheiro(**kw):
    base = {
        "smiles": {"cpm_compra_atual": 16.0, "cpm_valor_uso": 14.0, "atualizado_em": "2026-10-01"},
        "latam_pass": {"cpm_compra_atual": 25.0, "cpm_valor_uso": 22.0, "atualizado_em": "2026-10-01"},
        "azul": {"cpm_compra_atual": 15.0, "cpm_valor_uso": 13.0, "atualizado_em": "2026-10-01"},
        "pontos": {"livelo": {"cpm_valor_uso": 30.0, "atualizado_em": "2026-10-01"}},
        "transferencias": {"livelo_smiles": {"bonus_pct": 100, "ate": "2026-10-31", "minimo": 0}},
    }
    base.update(kw)
    return milheiro_de_dict(base)


def ida(data="2026-12-10", origem="GRU", destino="REC", cia="G3", voo="G3 1000", dur=200, conexoes=0, **kw):
    return Perna(origem=origem, destino=destino, data=data, cia=cia, voos=[voo], duracao_min=dur, conexoes=conexoes, **kw)


def op_dinheiro(preco, trecho="ida", pernas=None, **kw):
    return Opcao(fonte="kiwi", tipo="dinheiro", trecho=trecho, pernas=pernas or [ida()], preco=preco, **kw)


def op_milhas(milhas, taxas=40.0, programa="smiles", trecho="ida", pernas=None, **kw):
    return Opcao(
        fonte="seats_aero", tipo="milhas", programa=programa, trecho=trecho,
        pernas=pernas or [ida()], milhas=milhas, taxas=taxas, **kw,
    )


# --- effective cost ---------------------------------------------------------------------------

def test_dinheiro_multiplica_passageiros():
    c = custo_combinacao([op_dinheiro(500)], perfil(), milheiro(), passageiros=2, hoje=HOJE)
    assert c.custo == 1000
    assert c.estrategias == {"dinheiro"}


def test_dinheiro_com_bagagem_quando_perfil_pede():
    p = perfil(bagagem_despachada=True, custo_bagagem_trecho={"G3": 150, "padrao": 180})
    c = custo_combinacao([op_dinheiro(500)], p, milheiro(), passageiros=2, hoje=HOJE)
    assert c.custo == 500 * 2 + 150 * 2
    c2 = custo_combinacao([op_dinheiro(500, bagagem_inclusa=True)], p, milheiro(), passageiros=1, hoje=HOJE)
    assert c2.custo == 500


def test_milhas_proprias():
    p = perfil(programas={"smiles": {"saldo": 50_000}})
    c = custo_combinacao([op_milhas(10_000, taxas=40)], p, milheiro(), passageiros=1, hoje=HOJE)
    # 10k × R$14 per 1,000 + R$40 tax
    assert c.custo == pytest.approx(140 + 40)
    assert c.estrategias == {"milhas_proprias"}
    assert any("cache" in r for r in c.riscos)


def test_milhas_proprias_sem_cpm_valor_uso_usa_cpm_compra():
    m = milheiro(smiles={"cpm_compra_atual": 16.0, "atualizado_em": "2026-10-01"})
    p = perfil(programas={"smiles": {"saldo": 50_000}})
    c = custo_combinacao([op_milhas(10_000, taxas=0)], p, m, passageiros=1, hoje=HOJE)
    assert c.custo == pytest.approx(160)


def test_compra_parcial_usa_saldo_e_compra_o_resto():
    p = perfil(programas={"smiles": {"saldo": 4_000}})
    c = custo_combinacao([op_milhas(10_000, taxas=40)], p, milheiro(transferencias={}), passageiros=1, hoje=HOJE)
    # 4k from balance × 14 + 6k bought × 16 + 40
    assert c.custo == pytest.approx(56 + 96 + 40)
    assert c.estrategias == {"milhas_proprias", "comprar_milhas"}


def test_compra_respeita_minimo_e_multiplo():
    m = milheiro(smiles={"cpm_compra_atual": 16.0, "compra_minima": 2000, "compra_passo": 1000}, transferencias={})
    fin = financiar_milhas("smiles", 1_500, perfil(), m, HOJE)
    assert fin.milhas_compradas == 2000
    fin = financiar_milhas("smiles", 2_500, perfil(), m, HOJE)
    assert fin.milhas_compradas == 3000
    assert fin.custo == pytest.approx(48)


def test_transferencia_com_bonus():
    # Livelo at R$30 per 1,000 with a 100% bonus → a Smiles mile costs R$15, cheaper than buying at R$16.
    p = perfil(pontos_transferiveis={"livelo": 100_000})
    fin = financiar_milhas("smiles", 10_000, p, milheiro(), HOJE)
    assert fin.transferencias[0].pontos == 5_000
    assert fin.transferencias[0].milhas == 10_000
    assert fin.custo == pytest.approx(150)
    assert fin.estrategias == {"transferir_pontos"}


def test_transferencia_limitada_pelo_saldo_de_pontos_completa_com_compra():
    p = perfil(pontos_transferiveis={"livelo": 2_000})
    fin = financiar_milhas("smiles", 10_000, p, milheiro(), HOJE)
    assert fin.transferencias[0].pontos == 2_000
    assert fin.transferencias[0].milhas == 4_000
    assert fin.milhas_compradas == 6_000
    assert fin.custo == pytest.approx(60 + 96)


def test_bonus_expirado_nao_conta():
    m = milheiro(transferencias={"livelo_smiles": {"bonus_pct": 100, "ate": "2026-09-30"}})
    p = perfil(pontos_transferiveis={"livelo": 100_000})
    fin = financiar_milhas("smiles", 10_000, p, m, HOJE)
    # without a bonus a mile via Livelo costs R$30; buying at R$16 is better
    assert fin.estrategias == {"comprar_milhas"}


def test_transferencia_sem_bonus_compensa_so_se_mais_barata():
    m = milheiro(transferencias={"livelo_smiles": {"bonus_pct": 0}})
    p = perfil(pontos_transferiveis={"livelo": 100_000})
    assert financiar_milhas("smiles", 10_000, p, m, HOJE).estrategias == {"comprar_milhas"}


def test_sem_cpm_compra_e_sem_saldo_fica_sem_custo():
    m = milheiro(smiles={"cpm_compra_atual": None}, transferencias={})
    fin = financiar_milhas("smiles", 10_000, perfil(), m, HOJE)
    assert fin.custo is None
    assert fin.avisos


def test_misto_ida_dinheiro_volta_milhas_compartilha_saldo():
    p = perfil(programas={"smiles": {"saldo": 15_000}})
    ida_m = op_milhas(10_000, taxas=40)
    volta_m = op_milhas(10_000, taxas=40, trecho="volta", pernas=[ida("2026-12-17", "REC", "GRU", voo="G3 2000")])
    c = custo_combinacao([ida_m, volta_m], p, milheiro(transferencias={}), passageiros=1, hoje=HOJE)
    # 20k miles in total: 15k from balance (×14) + 5k bought (×16) + 80 taxes
    assert c.custo == pytest.approx(210 + 80 + 80)

    volta_d = op_dinheiro(300, trecho="volta", pernas=[ida("2026-12-17", "REC", "GRU", cia="AD", voo="AD 4000")])
    c2 = custo_combinacao([ida_m, volta_d], p, milheiro(), passageiros=1, hoje=HOJE)
    assert c2.custo == pytest.approx(140 + 40 + 300)
    assert c2.estrategias == {"milhas_proprias", "dinheiro"}
    assert any("bilhetes separados" in r for r in c2.riscos)


def test_aeroporto_alternativo_soma_deslocamento():
    p = perfil(aeroportos_alternativos_origem=[{"iata": "VCP", "custo_deslocamento": 150}])
    op = op_dinheiro(400, pernas=[ida(origem="VCP", cia="AD", voo="AD 1")])
    c = custo_combinacao([op], p, milheiro(), passageiros=2, hoje=HOJE)
    assert c.custo == 800 + 300
    assert "aeroporto_alternativo" in c.estrategias
    assert c.trabalhosa


def test_assentos_insuficientes_descarta():
    c = custo_combinacao([op_milhas(10_000, assentos_disponiveis=1)], perfil(), milheiro(), passageiros=2, hoje=HOJE)
    assert c.custo is None


def test_conexao_curta_vira_risco():
    op = op_dinheiro(500, pernas=[ida(conexoes=1, escalas_min=[40])])
    c = custo_combinacao([op], perfil(), milheiro(), passageiros=1, hoje=HOJE)
    assert any("conexão curta" in r for r in c.riscos)


# --- metrics --------------------------------------------------------------------------------

def test_cpm_equilibrio():
    assert cpm_equilibrio(540, 40, 20_000) == 25.0
    assert cpm_equilibrio(540, 40, 0) is None


def test_comparacao_prefere_mesmo_voo():
    m = op_milhas(10_000)
    mesmo = op_dinheiro(600)
    outra_cia = op_dinheiro(300, pernas=[ida(cia="AD", voo="AD 9")])
    preco, base = comparar_com_dinheiro(m, [mesmo, outra_cia])
    assert (preco, base) == (600, "mesmo voo")
    preco, base = comparar_com_dinheiro(m, [outra_cia])
    assert base == "mesma rota e data (outra cia)"


# --- ranking ---------------------------------------------------------------------------------

def pedido(**kw):
    base = dict(origens=["GRU"], destinos=["REC"], data_ida="2026-12-10", data_volta=None, flex_dias=3, passageiros=1)
    base.update(kw)
    return Pedido(**base)


def test_ranking_ordena_por_custo_e_desempata_por_duracao_e_conexoes():
    a = op_dinheiro(500, pernas=[ida(voo="G3 1", dur=300, conexoes=1)])
    b = op_dinheiro(500, pernas=[ida(voo="G3 2", dur=180, conexoes=0)])
    c = op_dinheiro(500, pernas=[ida(voo="G3 3", dur=180, conexoes=1)])
    d = op_dinheiro(450, pernas=[ida(voo="G3 4", dur=600, conexoes=2)])
    r = analisar([a, b, c, d], pedido(), perfil(), milheiro(), HOJE)
    assert [x.opcoes[0] for x in r.ranking] == [d, b, c, a]


def test_referencia_e_economia_e_tambem_possivel():
    ref = op_dinheiro(500)
    outra_data = op_dinheiro(300, pernas=[ida("2026-12-12", voo="G3 5")])
    # Buying miles that saves only R$20: goes to "also possible".
    pouco = op_milhas(30_000, taxas=0, pernas=[ida(voo="G3 6")])  # 30k × 16 = 480
    r = analisar([ref, outra_data, pouco], pedido(), perfil(), milheiro(transferencias={}), HOJE)
    assert r.referencia.opcoes == [ref]
    assert r.economia(r.ranking[0]) == 200
    assert [c.opcoes[0] for c in r.tambem_possivel] == [pouco]
    assert pouco not in [c.opcoes[0] for c in r.principais]


def test_janela_de_datas_filtra():
    fora = op_dinheiro(100, pernas=[ida("2026-12-20", voo="G3 7")])
    dentro = op_dinheiro(400, pernas=[ida("2026-12-13", voo="G3 8")])
    r = analisar([fora, dentro], pedido(), perfil(), milheiro(), HOJE)
    assert [c.opcoes[0] for c in r.ranking] == [dentro]


def test_ida_e_volta_gera_combinacoes_e_matriz():
    p = pedido(data_volta="2026-12-17")
    idas = [op_dinheiro(400, pernas=[ida("2026-12-10", voo="G3 1")]),
            op_dinheiro(350, pernas=[ida("2026-12-11", voo="G3 2")])]
    voltas = [op_dinheiro(300, trecho="volta", pernas=[ida("2026-12-17", "REC", "GRU", voo="G3 3")]),
              op_dinheiro(250, trecho="volta", pernas=[ida("2026-12-18", "REC", "GRU", cia="AD", voo="AD 3")])]
    rt = op_dinheiro(650, trecho="ida_volta",
                     pernas=[ida("2026-12-10", voo="G3 1"), ida("2026-12-17", "REC", "GRU", voo="G3 3")])
    resgate = op_milhas(8_000, taxas=30, trecho="volta", pernas=[ida("2026-12-17", "REC", "GRU", voo="G3 3")])
    r = analisar([*idas, *voltas, rt, resgate], p, perfil(programas={"smiles": {"saldo": 10_000}}), milheiro(), HOJE)

    assert r.referencia.custo == 650  # round trip on the exact dates, in cash
    assert r.matriz[("2026-12-11", "2026-12-18")].custo == 600
    # return with own miles: 8k × 14 + 30 = 142 → 350 + 142
    assert r.matriz[("2026-12-11", "2026-12-17")].custo == pytest.approx(492)
    assert r.ranking[0].custo == pytest.approx(492)
    assert len(r.matriz) == 4

    texto = gerar_relatorio(r, ["kiwi"], {"google_flights": "timeout"})
    assert "Matriz de datas" in texto and "google_flights indisponível" in texto
    assert "⭐" in texto


def test_veredito_compensa_comprar():
    m = op_milhas(20_000, taxas=40)
    d = op_dinheiro(540)
    r = analisar([m, d], pedido(), perfil(), milheiro(), HOJE)
    v = r.vereditos[0]
    assert v.cpm_equilibrio == 25.0 and v.compensa_comprar is True  # 25 > 16
    r2 = analisar([m, op_dinheiro(300)], pedido(), perfil(), milheiro(), HOJE)
    assert r2.vereditos[0].compensa_comprar is False  # (300-40)/20 = 13 < 16


def test_milheiro_desatualizado_gera_aviso():
    m = milheiro(smiles={"cpm_compra_atual": 16, "atualizado_em": "2026-09-01"})
    r = analisar([op_dinheiro(500)], pedido(), perfil(), m, HOJE)
    assert any("atualizado há 31 dias" in a for a in r.avisos)


def test_carregar_opcoes_descarta_invalidas():
    ops, avisos = carregar_opcoes([
        {"fonte": "kiwi", "tipo": "dinheiro", "pernas": [{"origem": "gru", "destino": "rec", "data": "2026-12-10"}], "preco": 500},
        {"fonte": "kiwi", "tipo": "dinheiro", "pernas": [], "preco": 500},
        {"fonte": "seats_aero", "tipo": "milhas", "programa": "smiles", "pernas": [{"origem": "GRU", "destino": "REC", "data": "2026-12-10"}]},
    ])
    assert len(ops) == 1 and ops[0].pernas[0].origem == "GRU"
    assert len(avisos) == 2


def test_deduplica_mesmo_voo_de_fontes_diferentes():
    from calculo.ranking import deduplicar

    kiwi = op_dinheiro(767, pernas=[ida(voo="LA3676", cia="LA")])
    google = Opcao(fonte="google_flights", tipo="dinheiro", preco=618, pernas=[ida(voo="LA 3676", cia="LA")])
    grade = Opcao(fonte="google_flights", tipo="dinheiro", preco=600,
                  pernas=[Perna(origem="GRU", destino="REC", data="2026-12-10")])
    out = deduplicar([kiwi, google, grade])
    assert google in out and grade in out and kiwi not in out


def test_transferencia_respeita_minimo():
    m = milheiro(transferencias={"livelo_smiles": {"bonus_pct": 100, "minimo": 10_000}})
    # 25k miles missing: 12.5k points (above the minimum) at R$ 30 = R$ 375 < buying 25k at R$ 16 = R$ 400
    fin = financiar_milhas("smiles", 25_000, perfil(pontos_transferiveis={"livelo": 50_000}), m, HOJE)
    assert fin.transferencias[0].pontos == 12_500
    # 5k missing: the minimum forces a 10k-point transfer (R$ 300); buying 5k (R$ 80) is better
    fin = financiar_milhas("smiles", 5_000, perfil(pontos_transferiveis={"livelo": 50_000}), m, HOJE)
    assert fin.estrategias == {"comprar_milhas"}
    # points balance below the minimum: transfer skipped
    fin = financiar_milhas("smiles", 25_000, perfil(pontos_transferiveis={"livelo": 5_000}), m, HOJE)
    assert fin.estrategias == {"comprar_milhas"}


def test_top_agrupa_mesma_opcao_em_datas_diferentes():
    a = op_dinheiro(400, pernas=[ida("2026-12-10", voo="G3 1")])
    b = op_dinheiro(400, pernas=[ida("2026-12-11", voo="G3 1")])
    c = op_dinheiro(450, pernas=[ida("2026-12-12", voo="G3 1")])
    r = analisar([a, b, c], pedido(), perfil(), milheiro(), HOJE)
    assert len(r.principais) == 2
    assert r.principais[0].datas_alternativas == [("2026-12-11", None)]
    assert len(r.matriz) == 3


def test_links_programas():
    from normalizacao import links

    s = links.smiles("POA", "GRU", "2026-11-15")
    assert "originAirport=POA" in s and "departureDate=1794744000000" in s and "tripType=2" in s
    assert "redemption=true" in links.latam("POA", "GRU", "2026-11-15")
    assert "c[0].std=11/15/2026" in links.azul("POA", "GRU", "2026-11-15") and "cc=PTS" in links.azul("POA", "GRU", "2026-11-15")


def test_dedup_prefere_confirmado_ao_vivo_mesmo_mais_caro():
    from calculo.ranking import deduplicar

    cache = op_milhas(10_000)
    vivo = Opcao(fonte="playwright_smiles", tipo="milhas", programa="smiles", pernas=[ida()], milhas=12_000,
                 taxas=40, confirmado_ao_vivo=True)
    assert deduplicar([cache, vivo]) == [vivo]


def test_registry_supplies_transfer_ratio_and_minimum():
    m = milheiro_de_dict({"transferencias": {"esfera_iberia": {"bonus_pct": 30, "ate": "2026-12-31"}}})
    par = next(t for t in m.transferencias if (t.origem, t.destino) == ("esfera", "iberia"))
    assert (par.proporcao, par.minimo, par.bonus_pct) == (2, 30000, 30)
    assert any((t.origem, t.destino) == ("inter_loop", "azul") for t in m.transferencias)


def test_miles_table_converted_to_search_currency():
    class FakeFx:
        def taxa(self, de, para):
            return {("BRL", "USD"): 0.2, ("USD", "USD"): 1.0}[(de, para)]

    m = milheiro_de_dict({
        "programas": {"smiles": {"cpm_compra_atual": 16.5}, "united": {"cpm_valor_uso": 13.5}},
        "pontos": {"livelo": {"cpm_valor_uso": 23, "moeda": "BRL"}},
    })
    usd, avisos = m.na_moeda("USD", FakeFx())
    assert usd.programas["smiles"].cpm_compra_atual == pytest.approx(3.3)
    assert usd.programas["united"].cpm_valor_uso == 13.5
    assert usd.pontos["livelo"].cpm_valor_uso == pytest.approx(4.6) and not avisos


def test_user_miles_table_wins_and_new_programs_come_from_the_shipped_table():
    from infra.config import mesclar_milheiro

    modelo = {"programas": {"smiles": {"cpm_compra_atual": 16.5}, "united": {"cpm_valor_uso": 12}},
              "transferencias": {"livelo_smiles": {"bonus_pct": 0}}}
    usuario = {"smiles": {"cpm_compra_atual": 14.0}, "transferencias": {"livelo_smiles": {"bonus_pct": 80}}}  # legacy layout
    m = milheiro_de_dict(mesclar_milheiro(modelo, usuario))
    assert m.programas["smiles"].cpm_compra_atual == 14.0
    assert m.programas["united"].cpm_valor_uso == 12
    assert next(t for t in m.transferencias if t.destino == "smiles" and t.origem == "livelo").bonus_pct == 80


# --- windows, trip length, separate tickets, validation --------------------------------------------------

def _voo(data, origem, destino, partida, chegada, voo, preco=None, trecho="ida", dur=None, **kw):
    perna = Perna(origem=origem, destino=destino, data=data, partida=partida, chegada=chegada, cia=voo[:2],
                  voos=[voo], duracao_min=dur)
    if preco is None:
        return Opcao(fonte="seats_aero", tipo="milhas", programa="smiles", trecho=trecho, pernas=[perna], **kw)
    return Opcao(fonte="google_flights", tipo="dinheiro", trecho=trecho, pernas=[perna], preco=preco, **kw)


def test_trip_length_window_is_enforced():
    p = Pedido(origens=["BSB"], destinos=["GIG"], data_ida="2026-11-02", ida_de="2026-11-02", ida_ate="2026-11-26",
               noites_min=5, noites_max=7)
    ida = _voo("2026-11-11", "BSB", "GIG", "12:30", "14:20", "G3 1806", 300)
    voltas = [_voo(d, "GIG", "BSB", "15:10", "17:00", "G3 1736", 280, trecho="volta")
              for d in ("2026-11-11", "2026-11-15", "2026-11-17", "2026-11-18", "2026-11-22")]
    r = analisar([ida, *voltas], p, perfil(), milheiro(), HOJE)
    assert sorted(c.data_volta for c in r.ranking) == ["2026-11-17", "2026-11-18"]  # 6 and 7 nights only


def test_separate_tickets_through_a_hub_need_a_feasible_connection():
    p = Pedido(origens=["BSB"], destinos=["MIA"], data_ida="2026-11-20")
    direto = _voo("2026-11-20", "BSB", "MIA", "23:00", "07:00", "AA 214", 3200, dur=480)
    pos_ok = _voo("2026-11-20", "BSB", "GRU", "12:00", "13:45", "G3 1000", 250, dur=105)
    pos_apertado = _voo("2026-11-20", "BSB", "GRU", "18:00", "19:45", "G3 1002", 200, dur=105)
    principal = _voo("2026-11-20", "GRU", "MIA", "21:30", "05:30", "LA 8180", 2100, dur=480)
    r = analisar([direto, pos_ok, pos_apertado, principal], p, perfil(), milheiro(), HOJE)
    melhor = r.ranking[0]
    assert [o.pernas[0].voos[0] for o in melhor.opcoes] == ["G3 1000", "LA 8180"]  # 7h45 connection; 1h45 is too short
    assert melhor.custo == 2350 and "bilhetes_separados" in melhor.estrategias
    assert any("GRU" in r_ for r_ in melhor.riscos) and melhor.hubs() == ["GRU"]
    assert all([o.pernas[0].voos[0] for o in c.opcoes] != ["G3 1002", "LA 8180"] for c in r.ranking)


def test_arrival_day_inferred_from_duration_across_midnight():
    perna = Perna("GRU", "MIA", "2026-11-20", partida="21:30", chegada="05:30", duracao_min=480)
    assert perna.chegada_dt().isoformat() == "2026-11-21T05:30:00"


def test_recommendation_mode_ignores_unvalidated_options():
    p = Pedido(origens=["BSB"], destinos=["GIG"], data_ida="2026-11-11")
    cache = _voo("2026-11-11", "BSB", "SDU", "12:30", "14:20", "G3 1806", milhas=11_200, taxas=40)
    cache.pernas[0].destino = "GIG"
    grade = Opcao(fonte="google_flights", tipo="dinheiro", preco=150, pernas=[Perna("BSB", "GIG", "2026-11-11")])
    real = _voo("2026-11-11", "BSB", "GIG", "07:00", "08:50", "LA 3001", 520)
    tudo = analisar([cache, grade, real], p, perfil(), milheiro(), HOJE)
    assert tudo.ranking[0].opcoes[0] is grade  # exploratory mode still sees hints
    so_validas = analisar([cache, grade, real], p, perfil(), milheiro(), HOJE, somente_validadas=True)
    assert [c.opcoes[0] for c in so_validas.ranking] == [real]
    assert any("2" in a for a in so_validas.avisos)


def test_plan_is_complete_step_by_step_with_links_and_amounts():
    from calculo.relatorio import gerar_relatorio

    p = Pedido(origens=["GRU"], destinos=["REC"], data_ida="2026-12-10", data_volta="2026-12-17", flex_dias=0)
    ida = _voo("2026-12-10", "GRU", "REC", "07:00", "10:10", "G3 1612", milhas=20_000, taxas=40,
               confirmado_ao_vivo=True, link="https://smiles.example/emitir")
    volta = _voo("2026-12-17", "REC", "GRU", "15:00", "18:10", "LA 3676", 600, trecho="volta",
                 link="https://kiwi.example/book")
    ref = _voo("2026-12-10", "GRU", "REC", "09:00", "12:10", "AD 4000", 900, link="https://g.example")
    ref_v = _voo("2026-12-17", "REC", "GRU", "09:00", "12:10", "AD 4001", 900, trecho="volta", link="https://g.example")
    pf = perfil(programas={"smiles": {"saldo": 5_000}})
    r = analisar([ida, volta, ref, ref_v], p, pf, milheiro(transferencias={}), HOJE, somente_validadas=True)
    texto = gerar_relatorio(r, ["kiwi"], {})
    plano = texto.split("## Como fazer")[1].split("## Top")[0]
    assert "Confira a disponibilidade" in plano and "G3 1612" in plano and "https://smiles.example/emitir" in plano
    assert "Compre 15.000 milhas Smiles" in plano and "https://www.smiles.com.br/comprar-milhas" in plano
    assert "LA 3676" in plano and "https://kiwi.example/book" in plano
    assert "**Total:**" in plano and "taxa de embarque não confirmada" in plano
    # order: check → buy miles → book award → buy cash
    assert plano.index("Confira") < plano.index("Compre 15.000") < plano.index("Emita") < plano.index("Compre a passagem")


def test_timing_tips_early_trip_lists_sales_and_season():
    from calculo.dicas import gerar_dicas

    dicas = gerar_dicas("2027-10-08", "2027-10-15", "LIS", "BR", "PT", "BR", HOJE)  # a year ahead, Fri→Fri
    texto = " ".join(dicas)
    assert "Ainda é cedo" in texto and "60 a 180" in texto
    assert "Black Friday — 27/11" in texto and "Aniversário Smiles" in texto and "bônus de transferência" in texto
    assert "segunda a quarta" in texto


def test_timing_tips_close_trip_and_domestic_window():
    from calculo.dicas import gerar_dicas

    assert "Compre logo" in gerar_dicas("2026-10-12", None, "REC", "BR", "BR", "BR", HOJE)[0]
    assert "Boa hora" in gerar_dicas("2026-11-11", None, "REC", "BR", "BR", "BR", HOJE)[0]  # 40 days, domestic BR
    alta = " ".join(gerar_dicas("2026-12-20", "2027-01-05", "MIA", "BR", "US", "BR", HOJE))
    assert "Alta temporada" in alta
