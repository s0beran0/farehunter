from datetime import date

import pytest

from infra.cache import Cache, chave_busca
from infra.historico import comparar_com_anterior, gravar, ler
from infra.limites import Contadores, LimiteExcedido
from normalizacao.schema import Opcao, Perna


def test_cache_respeita_ttl(tmp_path):
    t = [1000.0]
    c = Cache(tmp_path, agora=lambda: t[0])
    k = chave_busca("GRU", "REC", "2026-12-10")
    c.set("kiwi", k, {"x": 1})
    assert c.get("kiwi", k) == {"x": 1}
    t[0] += 2 * 3600 + 1  # TTL kiwi = 2h
    assert c.get("kiwi", k) is None
    c.set("seats_aero", k, [1])
    t[0] += 5 * 3600
    assert c.get("seats_aero", k) == [1]  # TTL seats = 6h
    assert c.limpar_expirados() == 1  # the kiwi one


def test_limite_diario_e_por_execucao(tmp_path):
    dia = [date(2026, 10, 2)]
    c = Contadores(tmp_path / "c.json", {"seats_aero_chamadas_dia": 2, "playwright_paginas_por_execucao": 1}, hoje=lambda: dia[0])
    assert c.consumir("seats_aero_chamadas_dia") == 1
    assert c.consumir("seats_aero_chamadas_dia") == 0
    with pytest.raises(LimiteExcedido):
        c.consumir("seats_aero_chamadas_dia")
    dia[0] = date(2026, 10, 3)
    assert c.consumir("seats_aero_chamadas_dia") == 1  # resets the next day
    c.consumir("playwright_paginas_por_execucao", execucao="run1")
    with pytest.raises(LimiteExcedido):
        c.consumir("playwright_paginas_por_execucao", execucao="run1")
    assert c.consumir("playwright_paginas_por_execucao", execucao="run2") == 0


def _op(preco, ts):
    return Opcao(fonte="kiwi", tipo="dinheiro", preco=preco, coletado_em=ts,
                 pernas=[Perna("GRU", "REC", "2026-12-10", cia="G3", voos=["G3 1"])])


def test_historico_grava_e_compara(tmp_path):
    arq = tmp_path / "h.csv"
    gravar([_op(500, "2026-09-20T10:00:00+00:00"), _op(520, "2026-09-20T10:00:00+00:00")], arq)
    atuais = [_op(450, "2026-10-02T10:00:00+00:00")]
    msgs = comparar_com_anterior(atuais, arq)
    assert len(msgs) == 1 and "desceu" in msgs[0] and "500" in msgs[0] and "450" in msgs[0]
    gravar(atuais, arq)
    assert len(ler(arq)) == 3


def test_extrair_promos_dos_titulos():
    from fontes.promos import extrair

    a = extrair("Último dia! Smiles oferece até 80% de bônus na transferência de pontos Livelo")
    assert a["tipo"] == "transferencia" and a["bonus_pct_max"] == 80 and set(a["programas"]) >= {"smiles", "livelo"}
    assert a["ultimo_dia"]
    b = extrair("LATAM Pass: compre milhas com até 65% de desconto, milheiro a partir de R$ 24,50")
    assert b["tipo"] == "compra" and b["desconto_pct_max"] == 65 and b["cpm_citado"] == 24.5


def test_coleta_datas_cai_no_sweep_quando_grade_falha(tmp_path, monkeypatch):
    import json

    from fontes import coleta, google_flights, kiwi
    from infra import runs

    run = tmp_path / "run"
    (run / "opcoes").mkdir(parents=True)
    (run / "pedido.json").write_text(json.dumps({
        "origens": ["GRU"], "destinos": ["REC"], "data_ida": "2026-12-10", "data_volta": None,
        "flex_dias": 1, "passageiros": 1, "cabine": "economy"}))

    def grade_quebrada(*a, **k):
        raise google_flights.FonteIndisponivel("grade vazia")

    chamadas = []

    def busca(origem, destino, data, volta, pax, cab, **locale):
        chamadas.append(data)
        return [Opcao(fonte="google_flights", tipo="dinheiro", preco=500,
                      pernas=[Perna(origem, destino, data, cia="G3", voos=["G3 1"])])]

    def kiwi_fora(*a, **k):
        raise kiwi.FonteIndisponivel("kiwi fora do ar")

    monkeypatch.setattr(google_flights, "grade", grade_quebrada)
    monkeypatch.setattr(google_flights, "buscar_data", busca)
    monkeypatch.setattr(kiwi, "buscar", kiwi_fora)
    monkeypatch.setattr(coleta, "carregar_perfil", lambda: __import__("infra.config", fromlist=["x"]).perfil_de_dict({}))
    coleta.coletar_datas(run)
    st = runs.status(run)
    assert chamadas == ["2026-12-09", "2026-12-10", "2026-12-11"]
    assert st["google_flights"]["ok"] and "sweep" in st["google_flights"]["motivo"]
    assert st["kiwi"]["ok"] is False and "kiwi fora do ar" in st["kiwi"]["motivo"]


class _FxFalso:
    def taxa(self, de, para):
        return {("USD", "BRL"): 5.0, ("BRL", "BRL"): 1.0, ("GBP", "BRL"): 6.5}[(de.upper(), para.upper())]

    def converter(self, v, de, para):
        return round(v * self.taxa(de, para), 2)


def test_seats_taxes_parsed_and_converted_to_search_currency():
    from fontes.seats import ler_valor_moeda, normalizar_mcp

    assert ler_valor_moeda("R$62.14 BRL") == (62.14, "BRL")
    assert ler_valor_moeda("$5.60 USD") == (5.6, "USD")
    assert ler_valor_moeda("£54.20") == (54.2, "GBP")
    dados = {"flights": [
        {"origin": "GRU", "destination": "MIA", "departs_at": "2026-11-20 22:00", "arrives_at": "2026-11-21 06:00",
         "flights": "AA930", "miles_price": 30000, "mileage_program": "american", "operating_carriers": ["AA"],
         "taxes": "$5.60 USD", "stops": 0, "minutes_old": 60},
        {"origin": "GRU", "destination": "MIA", "departs_at": "2026-11-20 22:00", "flights": "XX1",
         "miles_price": 1000, "mileage_program": "some_new_program", "taxes": "$1 USD"},
    ]}
    ops = normalizar_mcp(dados, moeda="BRL", cambio=_FxFalso())
    assert len(ops) == 1 and ops[0].programa == "american" and ops[0].taxas == 28.0


def test_partner_api_record_from_a_foreign_program(tmp_path):
    import json
    from pathlib import Path

    from mcp_seats.cliente import normalizar_search

    regs = json.loads((Path(__file__).parent / "fixtures" / "seats_search_american.json").read_text())["data"]
    ops = normalizar_search(regs, cabine="economy", moeda="BRL", cambio=_FxFalso())
    assert ops and all(o.programa == "american" for o in ops)
    assert all(o.taxas >= 0 for o in ops)


def test_programs_to_query_include_transfer_partners():
    from fontes.coleta import programas_para_busca

    progs = programas_para_busca({"programas": {"united": {"tem_conta": True}, "smiles": {"tem_conta": False}},
                                  "pontos_programas": ["livelo"]})
    assert progs[0] == "united" and {"smiles", "latam_pass", "azul"} <= set(progs)
    assert programas_para_busca({}) is None


def test_extract_english_promotions_and_regions():
    from fontes.promos import extrair, regioes_para

    a = extrair("Last day: Chase Ultimate Rewards 30% transfer bonus to Flying Blue")
    assert a["tipo"] == "transferencia" and a["bonus_pct_max"] == 30 and a["ultimo_dia"]
    assert {"chase_ur", "flyingblue"} <= set(a["programas"])
    b = extrair("Buy Avianca LifeMiles with a 145% bonus — 1.35 cents per mile")
    assert b["tipo"] == "compra" and b["centavos_por_milha"] == 1.35 and "lifemiles" in b["programas"]
    assert regioes_para("BR") == ["br"] and regioes_para("GB") == ["uk", "us"] and regioes_para("MX") == ["us"]


def test_cents_each_format_from_a_real_feed_title():
    from fontes.promos import extrair

    r = extrair("Buy Alaska Atmos Rewards Points With 100% Bonus (1.88 Cents Each): Worth It?")
    assert r["centavos_por_milha"] == 1.88 and r["bonus_pct_max"] == 100 and r["programas"] == ["alaska"]


def test_google_rate_limit_pauses_further_calls(tmp_path, monkeypatch):
    import pytest as _pytest

    from fontes import google_flights as gf

    monkeypatch.setattr(gf, "ESTADO_FREIO", tmp_path / "freio.json")
    monkeypatch.setattr(gf, "INTERVALO_MIN_S", 0)
    gf._antes_de_chamar()  # no pause yet
    with _pytest.raises(gf.LimiteGoogle):
        gf._apos_erro(RuntimeError("Google Flights returned an error response (HTTP 429)"))
    with _pytest.raises(gf.LimiteGoogle, match="paused"):
        gf._antes_de_chamar()
    gf._apos_erro(RuntimeError("HTTP 500"))  # other errors don't trigger the pause logic


def test_served_hubs_keep_only_airports_with_flights(monkeypatch, tmp_path):
    from fontes import rotas
    from infra.cache import Cache

    monkeypatch.setattr(rotas, "aeroportos_do_pais", lambda pais, **k: [
        {"iata": "GRU", "nome": "", "voos_semanais": 852}, {"iata": "CNF", "nome": "", "voos_semanais": 329},
        {"iata": "FOR", "nome": "", "voos_semanais": 116}, {"iata": "XXX", "nome": "", "voos_semanais": 10}])

    def direto(hub, destino, data, moeda, pax, trecho):
        if hub != "GRU":
            return [], None
        return [Opcao(fonte="kiwi", tipo="dinheiro", trecho=trecho, preco=2000,
                      pernas=[Perna("GRU", "MIA", data, cia="AA", voos=["AA 930"])])], None

    monkeypatch.setattr(rotas, "_direto_kiwi", direto)
    monkeypatch.setattr(rotas, "_rota_seats", lambda h, d, c: ["american"] if h == "FOR" else [])
    hubs, ops = rotas.hubs_servidos("MIA", "BR", "2026-11-20", excluir={"BSB"}, cache=Cache(tmp_path))
    assert [h["iata"] for h in hubs] == ["GRU", "FOR"]  # CNF has nothing; XXX is too small to try
    assert hubs[0]["direto"] and not hubs[1]["direto"] and len(ops) == 1


def test_google_pause_can_be_released_after_the_user_browses(tmp_path, monkeypatch):
    from fontes import google_flights as gf

    monkeypatch.setattr(gf, "ESTADO_FREIO", tmp_path / "freio.json")
    try:
        gf._apos_erro(RuntimeError("HTTP 429"))
    except gf.LimiteGoogle:
        pass
    assert gf.estado_pausa()["pausado"]
    gf.liberar_pausa()
    assert not gf.estado_pausa()["pausado"]
