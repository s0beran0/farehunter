from datetime import date

from calculo.ranking import Pedido
from infra.config import milheiro_de_dict, perfil_de_dict
from normalizacao.schema import Opcao, Perna


def cenario_ida_volta():
    def perna(d, o="GRU", de="REC", cia="G3", voo="G3 1"):
        return Perna(o, de, d, cia=cia, voos=[voo], duracao_min=200)

    opcoes = [
        Opcao(fonte="kiwi", tipo="dinheiro", preco=400, pernas=[perna("2026-12-10")]),
        Opcao(fonte="kiwi", tipo="dinheiro", trecho="volta", preco=300, pernas=[perna("2026-12-17", "REC", "GRU", voo="G3 2")]),
        Opcao(fonte="seats_aero", tipo="milhas", programa="smiles", trecho="volta", milhas=8000, taxas=30,
              pernas=[perna("2026-12-17", "REC", "GRU", voo="G3 2")]),
    ]
    pedido = Pedido(origens=["GRU"], destinos=["REC"], data_ida="2026-12-10", data_volta="2026-12-17", flex_dias=1)
    perfil = perfil_de_dict({"programas": {"smiles": {"saldo": 10000}}})
    milheiro = milheiro_de_dict({"smiles": {"cpm_compra_atual": 16, "cpm_valor_uso": 14, "atualizado_em": "2026-10-01"}})
    return opcoes, pedido, perfil, milheiro, date(2026, 10, 2)
