import pytest

from infra import perfil_io, runs
from infra.config import carregar_perfil


def test_salvar_mescla_valida_e_regrava(tmp_path):
    arq = tmp_path / "perfil.yaml"
    _, antigo = perfil_io.salvar({
        "aeroportos_origem": ["poa"],
        "aeroportos_alternativos_origem": [{"iata": "cxj", "custo_deslocamento_brl": 90, "observacao": "2h de carro"}],
        "passageiros_padrao": 2,
        "programas": {"smiles": {"tem_conta": True, "clube": True, "categoria": "Prata"}},
        "pontos_programas": ["Livelo", "Inter Loop"],
    }, arq)
    assert antigo == ""
    p = carregar_perfil(arq)
    assert p.aeroportos_origem == ["POA"]
    assert p.aeroportos_alternativos_origem[0].iata == "CXJ" and p.aeroportos_alternativos_origem[0].custo_deslocamento_brl == 90
    assert p.programas["smiles"].clube and p.programas["smiles"].saldo == 0  # saldo nunca vem do arquivo
    bruto = perfil_io.carregar_bruto(arq)
    assert bruto["pontos_programas"] == ["livelo", "inter_loop"]
    assert bruto["programas"]["smiles"]["tem_conta"] and not bruto["programas"]["azul"]["tem_conta"]
    assert perfil_io.faltando(bruto) == []
    assert "saldo" not in arq.read_text().split("SALDOS NÃO FICAM AQUI")[1]

    perfil_io.salvar({"programas": {"azul": {"tem_conta": True}}}, arq)  # atualização parcial
    bruto = perfil_io.carregar_bruto(arq)
    assert bruto["programas"]["azul"]["tem_conta"] and bruto["programas"]["smiles"]["categoria"] == "Prata"


def test_validacao_recusa_valores_ruins_e_saldo(tmp_path):
    arq = tmp_path / "perfil.yaml"
    with pytest.raises(perfil_io.PerfilInvalido, match="IATA"):
        perfil_io.salvar({"aeroportos_origem": ["Porto Alegre"]}, arq)
    with pytest.raises(perfil_io.PerfilInvalido, match="não ficam no perfil"):
        perfil_io.salvar({"programas": {"smiles": {"saldo": 45000}}}, arq)
    with pytest.raises(perfil_io.PerfilInvalido, match="desconhecido"):
        perfil_io.salvar({"programas": {"tap": {"tem_conta": True}}}, arq)
    assert not arq.exists()


def test_perfil_novo_pede_configuracao(tmp_path):
    assert "aeroportos_origem" in perfil_io.faltando(perfil_io.carregar_bruto(tmp_path / "nao_existe.yaml"))


def test_saldos_valem_so_para_a_execucao(tmp_path):
    from infra.config import perfil_de_dict

    perfil = perfil_de_dict({})
    assert runs.aplicar_saldos(perfil, None).startswith("Saldos não informados")
    runs.gravar_saldos(tmp_path, {"smiles": 45000, "livelo": 12000})
    reg = runs.ler_saldos(tmp_path)
    assert runs.aplicar_saldos(perfil, reg) is None
    assert perfil.programas["smiles"].saldo == 45000 and perfil.pontos_transferiveis["livelo"] == 12000
    assert reg["informados_em"]
