"""Testes da área Plus. Todos os dados são inventados."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import plus  # noqa: E402
from financeiro import ler_fatura_bb  # noqa: E402
from test_financeiro import TEXTO_FATURA  # noqa: E402


def _t(linhas):
    """linhas: (data, fornecedor, valor, tipo, categoria, subcategoria, descricao,
    conta, parcela, parcelas)"""
    t = pd.DataFrame(linhas, columns=["Data", "Fornecedor", "Valor", "Tipo", "Categoria",
                                      "Subcategoria", "Descrição", "Conta", "Parcela",
                                      "Parcelas"])
    t["Data"] = pd.to_datetime(t["Data"])
    t["Mês"] = t["Data"].dt.to_period("M").astype(str)
    return t


def _gasto(data, fornecedor, valor, categoria="OUTRO", sub="", descricao=None,
           conta="Conta", parcela=None, parcelas=None):
    return (data, fornecedor, -valor, "Saída", categoria, sub, descricao or fornecedor.upper(),
            conta, parcela, parcelas)


def _entrada(data, fonte, valor, sub="Recebido de empresas", descricao=None):
    return (data, fonte, valor, "Entrada", "RECEITA", sub, descricao or fonte.upper(),
            "Conta", None, None)


# ----------------------------------------------------------------------------
# Parcelas
# ----------------------------------------------------------------------------
def test_fatura_guarda_numero_da_parcela():
    t = ler_fatura_bb(TEXTO_FATURA)
    parc = t[t["Descrição"].str.contains("PARC")].iloc[0]
    assert (parc["Parcela"], parc["Parcelas"]) == (9, 10)
    assert parc["DataCompra"] == pd.Timestamp("2025-09-30")   # compra original
    assert parc["Data"] == pd.Timestamp("2026-06-30")         # o gasto entra no fechamento
    assert t["Parcela"].isna().sum() == len(t) - 1


def test_mesma_compra_em_varias_faturas_vira_uma_linha():
    c = "BB Cartão"
    t = _t([
        _gasto("2026-01-30", "Loja Exemplo", 100.00, conta=c, parcela=2, parcelas=5),
        _gasto("2026-02-28", "Loja Exemplo", 100.01, conta=c, parcela=3, parcelas=5),
        # anuidade: cada mês traz uma data impressa diferente, mas é a mesma série
        _gasto("2026-01-30", "Anuidade Exemplo", 20.0, conta=c, parcela=1, parcelas=12),
        _gasto("2026-02-28", "Anuidade Exemplo", 20.0, conta=c, parcela=2, parcelas=12),
        # já terminou: não aparece
        _gasto("2026-02-28", "Loja Paga", 50.0, conta=c, parcela=4, parcelas=4),
    ])
    tabela, cronograma = plus.parcelas_futuras(t)
    assert len(tabela) == 2
    loja = tabela.set_index("Fornecedor").loc["Loja Exemplo"]
    assert (loja["Parcela atual"], loja["Restam"]) == (3, 2)
    assert round(loja["Total restante"], 2) == 200.02
    assert loja["Última parcela"] == "2026-04"
    anuidade = tabela.set_index("Fornecedor").loc["Anuidade Exemplo"]
    assert (anuidade["Parcela atual"], anuidade["Restam"]) == (2, 10)
    assert cronograma.iloc[0].tolist() == ["2026-03", 120.01]
    assert len(cronograma) == 10


def test_duas_compras_iguais_em_meses_diferentes_ficam_separadas():
    c = "BB Cartão"
    t = _t([
        _gasto("2026-02-28", "Loja Exemplo", 100.0, conta=c, parcela=1, parcelas=3),
        _gasto("2026-02-28", "Loja Exemplo", 100.0, conta=c, parcela=2, parcelas=3),
    ])
    tabela, _ = plus.parcelas_futuras(t)
    assert sorted(tabela["Restam"]) == [1, 2]


def test_parcela_estimada_quando_falta_fatura_recente():
    c = "BB Cartão"
    t = _t([
        _gasto("2026-01-30", "Loja Exemplo", 100.0, conta=c, parcela=2, parcelas=5),
        _gasto("2026-03-30", "Mercado", 10.0, conta=c),   # fatura de março sem a parcela
    ])
    tabela, _ = plus.parcelas_futuras(t)
    assert (tabela.iloc[0]["Parcela atual"], tabela.iloc[0]["Restam"]) == (4, 1)


def test_sem_parcelas():
    t = _t([_gasto("2026-01-10", "Mercado", 10.0)])
    tabela, cronograma = plus.parcelas_futuras(t)
    assert tabela.empty and cronograma.empty
    tabela, _ = plus.parcelas_futuras(t.drop(columns=["Parcela", "Parcelas"]))
    assert tabela.empty


# ----------------------------------------------------------------------------
# Recorrentes
# ----------------------------------------------------------------------------
def test_gastos_recorrentes():
    linhas = []
    for m in range(1, 6):
        linhas.append(_gasto(f"2026-0{m}-10", "Streaming", 39.90, "ASSINATURAS"))
        linhas.append(_gasto(f"2026-0{m}-05", "Luz Exemplo", 100 + 40 * m, "CASA"))
        linhas.append(_gasto(f"2026-0{m}-18", "Lanchonete", 30 + 20 * m, "ALIMENTAÇÃO"))
        for d in (3, 12, 20):
            linhas.append(_gasto(f"2026-0{m}-{d:02d}", "Padaria", 10 + d, "ALIMENTAÇÃO"))
    for m in range(1, 4):   # parou em março
        linhas.append(_gasto(f"2026-0{m}-15", "Academia", 90.0, "SAÚDE"))
    linhas.append(_gasto("2026-02-01", "Loja Uma Vez", 500.0))
    linhas.append(_gasto("2026-03-30", "Loja Parcelada", 50.0, parcela=1, parcelas=3))
    r = plus.gastos_recorrentes(_t(linhas)).set_index("Fornecedor")

    assert "Loja Uma Vez" not in r.index and "Loja Parcelada" not in r.index
    assert r.loc["Streaming", "Tipo"] == plus.FIXO
    assert r.loc["Streaming", "Próxima prevista"] == "10/06/2026"
    assert r.loc["Luz Exemplo", "Tipo"] == plus.CONTA_MENSAL
    assert r.loc["Padaria", "Tipo"] == plus.FREQUENTE
    assert r.loc["Lanchonete", "Tipo"] == plus.FREQUENTE   # uma vez por mês, mas não é conta
    assert r.loc["Padaria", "Próxima prevista"] == ""
    assert r.loc["Academia", "Situação"] == "Parou (03/2026)"
    assert r.loc["Academia", "Próxima prevista"] == ""
    # Só o que é fixo ou conta mensal e continua ativo
    esperado = 39.90 + r.loc["Luz Exemplo", "Por mês"]
    assert round(plus.compromissos_mensais(r.reset_index()), 2) == round(esperado, 2)


# ----------------------------------------------------------------------------
# Imposto de Renda
# ----------------------------------------------------------------------------
def test_relatorio_ir():
    t = _t([
        _gasto("2025-03-10", "Clinica Exemplo", 300.0, "SAÚDE", "Clínicas, consultas e exames",
               "PIX ENVIADO CLINICA EXEMPLO 12.345.678/0001-90"),
        _gasto("2025-04-10", "Clinica Exemplo", 200.0, "SAÚDE", "Clínicas, consultas e exames"),
        _gasto("2025-04-12", "Plano Exemplo", 500.0, "SAÚDE", "Plano de saúde"),
        _gasto("2025-04-15", "Drogaria Exemplo", 80.0, "SAÚDE", "Drogaria"),   # não deduz
        _gasto("2025-05-01", "Escola Exemplo", 900.0, "EDUCAÇÃO"),
        _gasto("2025-06-01", "Seguradora", 400.0, "OUTRO", "",
               "DEBITO PREVIDENCIA PRIVADA PGBL"),
        _gasto("2024-12-20", "Clinica Exemplo", 999.0, "SAÚDE",
               "Clínicas, consultas e exames"),                           # outro ano
        _entrada("2025-02-05", "Empresa Exemplo", 5000.0,
                 descricao="TED RECEBIDA EMPRESA EXEMPLO 98765432000110"),
        _entrada("2025-02-20", "Pessoa Exemplo", 300.0, "Recebido de pessoas"),
    ])
    ir = plus.relatorio_ir(t, 2025)
    d = ir["deducoes"].set_index("Fornecedor")
    assert "Drogaria Exemplo" not in d.index
    assert d.loc["Clinica Exemplo", "Total"] == 500.0
    assert d.loc["Clinica Exemplo", "Pagamentos"] == 2
    assert d.loc["Clinica Exemplo", "CNPJ"] == "12.345.678/0001-90"
    assert d.loc["Plano Exemplo", "Grupo"] == plus.GRUPO_SAUDE
    assert d.loc["Escola Exemplo", "Grupo"] == plus.GRUPO_EDUCACAO
    assert d.loc["Seguradora", "Grupo"] == plus.GRUPO_PREVIDENCIA
    pj = ir["rendimentos_pj"].iloc[0]
    assert (pj["Fornecedor"], pj["Total"], pj["CNPJ"]) == \
        ("Empresa Exemplo", 5000.0, "98.765.432/0001-10")
    assert ir["rendimentos_pf"].iloc[0].tolist() == ["2025-02", 300.0, 1]


def test_formatar_cnpj():
    assert plus.formatar_cnpj("12345678000190") == "12.345.678/0001-90"
    assert plus.formatar_cnpj(None) == ""
    assert plus.formatar_cnpj("123") == ""


# ----------------------------------------------------------------------------
# Saúde financeira
# ----------------------------------------------------------------------------
def test_indicadores():
    t = _t([
        _entrada("2026-01-05", "Empresa A", 6000.0),
        _entrada("2026-01-06", "Empresa B", 4000.0),
        _gasto("2026-01-10", "Mercado", 7000.0),
        _entrada("2026-02-05", "Empresa A", 6000.0),
        _entrada("2026-02-06", "Empresa B", 4000.0),
        _gasto("2026-02-10", "Mercado", 11000.0),
        _gasto("2026-03-10", "Mercado", 3000.0),   # só cartão neste mês: fica de fora
    ])
    itens = {i["nome"]: i for i in plus.indicadores(t, fixos_por_mes=4000.0,
                                                    parcelas_proximo_mes=500.0,
                                                    guardado=36000.0)}
    assert itens["Quanto sobra das entradas"]["valor"] == "10%"
    assert itens["Quanto sobra das entradas"]["status"] == plus.ATENCAO
    assert itens["Meses no vermelho"]["valor"] == "1 de 2"
    assert itens["Meses no vermelho"]["status"] == plus.ALERTA
    assert itens["Dependência da maior fonte"]["valor"] == "60%"
    assert itens["Dependência da maior fonte"]["status"] == plus.ALERTA
    assert itens["Compromissos mensais"]["status"] == plus.BOM          # 40%
    assert itens["Parcelas do próximo mês"]["status"] == plus.BOM       # 5%
    assert itens["Reserva de emergência"]["valor"] == "4,0 meses"
    assert itens["Reserva de emergência"]["status"] == plus.ATENCAO


def test_indicadores_sem_dados_opcionais():
    t = _t([_entrada("2026-01-05", "Empresa A", 1000.0), _gasto("2026-01-10", "Mercado", 500.0)])
    nomes = [i["nome"] for i in plus.indicadores(t)]
    assert "Reserva de emergência" not in nomes and "Compromissos mensais" not in nomes
    assert plus.indicadores(t)[0]["status"] == plus.BOM   # sobra 50%


def test_dados_dos_graficos_de_linha():
    linhas = []
    for m in range(1, 5):
        linhas.append(_gasto(f"2026-0{m}-10", "Streaming", 39.90, "ASSINATURAS"))
        linhas.append(_gasto(f"2026-0{m}-05", "Luz Exemplo", 100 + 40 * m, "CASA"))
        for d in (3, 12, 20):
            linhas.append(_gasto(f"2026-0{m}-{d:02d}", "Padaria", 10.0, "ALIMENTAÇÃO"))
    t = _t(linhas)
    h = plus.historico_recorrentes(t, plus.gastos_recorrentes(t))
    assert set(h["Fornecedor"]) == {"Streaming", "Luz Exemplo"}   # frequente fica de fora
    assert h[h["Fornecedor"] == "Luz Exemplo"]["Valor"].tolist() == [140, 180, 220, 260]

    parcelas = pd.DataFrame([{"Fornecedor": "Loja", "Valor da parcela": 50.0, "Restam": 3,
                              "Última parcela": "2026-12"}])
    c = plus.cronograma_por_compra(parcelas)
    assert c["Mês"].tolist() == ["2026-10", "2026-11", "2026-12"]
    assert c["Valor"].tolist() == [50.0] * 3
