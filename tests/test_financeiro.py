"""Testes do processamento de extratos. Rodar com: pytest"""

import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financeiro import (  # noqa: E402
    categorizar,
    converter_valor,
    detectar_colunas,
    formatar_reais,
    ler_extrato,
    montar_transacoes,
    resumo_categorias,
    resumo_mensal,
)


def processar(nome, conteudo):
    bruto = ler_extrato(nome, conteudo)
    return montar_transacoes(bruto, detectar_colunas(bruto))


@pytest.mark.parametrize("entrada, esperado", [
    ("1.234,56", 1234.56),
    ("-1.234,56", -1234.56),
    ("R$ -10,00", -10.0),
    ("(50,00)", -50.0),
    ("123,45 D", -123.45),
    ("123,45 C", 123.45),
    ("123,45-", -123.45),
    ("-45.90", -45.9),
    ("1,234.56", 1234.56),
    ("1.234", 1234.0),
    (1500.5, 1500.5),
    ("", None),
    ("abc", None),
])
def test_converter_valor(entrada, esperado):
    assert converter_valor(entrada) == esperado


@pytest.mark.parametrize("descricao, categoria", [
    ("COMPRA CARTAO FARMÁCIA PAGUE MENOS", "SAÚDE"),
    ("PIX ENVIADO RESTAURANTE CAMARÕES", "ALIMENTAÇÃO"),
    ("PIX ENVIADO JOAO SILVA", "TRANSFERÊNCIA"),
    ("POSTO IPIRANGA", "TRANSPORTE"),
    ("COSERN CONTA DE LUZ", "CASA"),
    ("TARIFA PACOTE SERVIÇOS", "TARIFAS BANCÁRIAS"),
    ("PAGAMENTO DARF", "IMPOSTO"),
    ("GASTOS DIVERSOS", "OUTRO"),        # "gas" não pode casar dentro de "gastos"
    ("APLICACAO CDB", "INVESTIMENTO"),
    ("ALGO QUALQUER", "OUTRO"),
])
def test_categorizar(descricao, categoria):
    assert categorizar(descricao, -10) == categoria


def test_entrada_vira_receita():
    assert categorizar("PIX RECEBIDO CLIENTE", 500) == "RECEITA"


def test_csv_banco_do_brasil_latin1():
    conteudo = (
        "Data;Lançamento;Detalhes;Nº documento;Valor;Tipo Lançamento\n"
        "01/09/2026;Saldo Anterior;;;1.000,00;\n"
        "02/09/2026;Pix - Recebido;CLIENTE X;123;2.500,00;Entrada\n"
        "05/09/2026;Compra com Cartão;FARMACIA PAGUE MENOS;124;-89,90;Saída\n"
        "10/10/2026;Pagamento de Boleto;COSERN;125;-210,35;Saída\n"
        "10/10/2026;S A L D O;;;3.200,00;\n"
    ).encode("latin-1")
    t = processar("extrato.csv", conteudo)
    assert len(t) == 3  # linhas de saldo ignoradas
    assert t["Valor"].tolist() == [2500.0, -89.9, -210.35]
    assert t["Mês"].tolist() == ["2026-09", "2026-09", "2026-10"]
    # "Lançamento" + "Detalhes" juntos: o nome da empresa entra na categorização
    assert t["Descrição"].iloc[2] == "Pagamento de Boleto - COSERN"
    assert t["Categoria"].tolist() == ["RECEITA", "SAÚDE", "CASA"]


def test_csv_nubank_virgula_e_ponto_decimal():
    conteudo = (
        "Data,Valor,Identificador,Descrição\n"
        "01/09/2026,-45.90,abc,Compra no débito - IFOOD\n"
        "03/09/2026,1500.00,def,Transferência recebida pelo Pix\n"
    ).encode("utf-8")
    t = processar("nubank.csv", conteudo)
    assert t["Valor"].tolist() == [-45.9, 1500.0]
    assert t["Categoria"].tolist() == ["ALIMENTAÇÃO", "RECEITA"]


def test_csv_credito_e_debito_separados():
    conteudo = (
        "Data Lançamento;Histórico;Crédito;Débito\n"
        "01/09/2026;SALARIO;5.000,00;\n"
        "02/09/2026;UBER TRIP;;32,50\n"
    ).encode("utf-8")
    bruto = ler_extrato("inter.csv", conteudo)
    colunas = detectar_colunas(bruto)
    assert colunas["credito"] == "Crédito" and colunas["debito"] == "Débito"
    t = montar_transacoes(bruto, colunas)
    assert t["Valor"].tolist() == [5000.0, -32.5]
    assert t["Categoria"].tolist() == ["RECEITA", "TRANSPORTE"]


def test_xlsx_com_linhas_de_titulo_antes_do_cabecalho():
    linhas = [
        ["Banco Exemplo S.A.", None, None],
        ["Extrato de conta corrente", None, None],
        [None, None, None],
        ["Data", "Histórico", "Valor (R$)"],
        [pd.Timestamp("2026-09-01"), "SUPERMERCADO NORDESTÃO", -350.0],
        [pd.Timestamp("2026-09-15"), "PIX RECEBIDO", 1200.0],
    ]
    buf = io.BytesIO()
    pd.DataFrame(linhas).to_excel(buf, header=False, index=False)
    t = processar("extrato.xlsx", buf.getvalue())
    assert t["Descrição"].tolist() == ["SUPERMERCADO NORDESTÃO", "PIX RECEBIDO"]
    assert t["Categoria"].tolist() == ["ALIMENTAÇÃO", "RECEITA"]


def test_resumos():
    t = pd.DataFrame({
        "Data": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-10-01"]),
        "Descrição": ["a", "b", "c"],
        "Valor": [1000.0, -300.0, -100.0],
        "Categoria": ["RECEITA", "CASA", "LAZER"],
        "Mês": ["2026-09", "2026-09", "2026-10"],
    })
    cats = resumo_categorias(t)
    assert cats["Categoria"].tolist() == ["CASA", "LAZER"]
    assert cats["% das saídas"].tolist() == [75.0, 25.0]
    mensal = resumo_mensal(t)
    assert mensal["Saldo"].tolist() == [700.0, -100.0]


def test_formatar_reais():
    assert formatar_reais(1234.5) == "R$ 1.234,50"
    assert formatar_reais(-10) == "-R$ 10,00"
