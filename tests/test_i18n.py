import pytest

import i18n
from calculo.ranking import analisar
from calculo.relatorio import gerar_relatorio
from i18n.mensagens import MENSAGENS
from tests_helpers import cenario_ida_volta


@pytest.fixture(autouse=True)
def volta_para_pt():
    yield
    i18n.definir("pt")


def test_todos_os_idiomas_tem_as_mesmas_chaves():
    referencia = set(MENSAGENS["pt"])
    for idioma in i18n.IDIOMAS:
        assert set(MENSAGENS[idioma]) == referencia, idioma


def test_normalizacao_de_idioma():
    assert i18n.normalizar("pt-BR") == "pt"
    assert i18n.normalizar("es_AR") == "es"
    assert i18n.normalizar("EN-us") == "en"
    assert i18n.normalizar("fr") == "en"  # sem tradução: inglês
    assert i18n.normalizar(None) == "pt"


def test_formatos_por_idioma():
    i18n.definir("en")
    assert i18n.dinheiro(1147) == "R$1,147.00" and i18n.numero(28000) == "28,000"
    assert i18n.data_curta("2026-11-20") == "Nov 20 (Fri)"
    i18n.definir("es")
    assert i18n.dinheiro(1147) == "R$ 1.147,00" and i18n.data_curta("2026-11-20") == "20/11 (vie)"


@pytest.mark.parametrize("idioma,esperados", [
    ("en", ["# Flights", "## Date matrix", "## Miles", "break-even CPM", "with Smiles miles", "## Next steps"]),
    ("es", ["# Vuelos", "## Matriz de fechas", "## Millas", "CPM de equilibrio", "con millas Smiles", "## Próximos pasos"]),
    ("pt", ["# Passagens", "## Matriz de datas", "## Milhas", "CPM de equilíbrio", "em milhas Smiles", "## Próximos passos"]),
])
def test_relatorio_no_idioma(idioma, esperados):
    i18n.definir(idioma)
    opcoes, pedido, perfil, milheiro, hoje = cenario_ida_volta()
    texto = gerar_relatorio(analisar(opcoes, pedido, perfil, milheiro, hoje), ["kiwi"], {"google_flights": "timeout"},
                            milheiro=milheiro)
    for e in esperados:
        assert e in texto, (idioma, e)
