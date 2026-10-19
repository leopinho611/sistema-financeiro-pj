"""
Extratos 100% fictícios para o relatório de exemplo da vitrine do Plus.

Um ano de uma pessoa inventada: salário, contas fixas, mercado, uma viagem, parcelas no
cartão. Nada aqui vem de extrato real.
"""

import random
from datetime import datetime

import pandas as pd

import relatorio

CARTAO = "Banco Azul Cartão"


def transacoes_exemplo():
    """Transações fictícias já categorizadas (mesmo formato de financeiro.consolidar)."""
    random.seed(7)
    L = []

    def add(data, desc, forn, valor, cat, sub="", conta="Banco Azul", parc=None,
            parcs=None):
        L.append(dict(Data=pd.Timestamp(data), Descrição=desc, Fornecedor=forn, Valor=valor,
                      Categoria=cat, Subcategoria=sub, Conta=conta, Parcela=parc,
                      Parcelas=parcs))

    meses = pd.period_range("2025-10", "2026-09", freq="M")
    for i, m in enumerate(meses):
        a, mm = m.year, m.month

        def d(dia, a=a, mm=mm, m=m):
            return f"{a}-{mm:02d}-{min(dia, m.days_in_month):02d}"
        # Entradas
        add(d(5), "TED RECEBIDA EMPRESA EXEMPLO LTDA 11.222.333/0001-81", "Empresa Exemplo Ltda",
            6800.0, "RECEITA", "Recebido de empresas")
        if i % 3 == 1:
            add(d(18), "PIX RECEBIDO CLIENTE ALFA SERVICOS 44.555.666/0001-99",
                "Cliente Alfa Serviços", round(random.uniform(1500, 2600), 2), "RECEITA",
                "Recebido de empresas")
        if i % 2 == 0:
            add(d(22), "PIX RECEBIDO ***.123.456-** JOAO", "João (pessoa)", 450.0, "RECEITA",
                "Recebido de pessoas")
        # Contas fixas e mensais
        add(d(10), "ALUGUEL APTO", "Imobiliária Exemplo", -1800.0, "CASA", "Aluguel")
        add(d(10), "CONDOMINIO RESIDENCIAL EXEMPLO", "Condomínio Exemplo", -480.0, "CASA",
            "Condomínio")
        add(d(12), "ENERGIA ELETRICA EXEMPLO", "Energia Exemplo",
            -round(random.uniform(160, 260), 2), "CASA", "Luz")
        add(d(15), "INTERNET FIBRA EXEMPLO", "Internet Fibra Exemplo", -119.9, "CASA", "Internet")
        add(d(20), "PLANO DE SAUDE EXEMPLO 22.333.444/0001-55", "Plano de Saúde Exemplo",
            -620.0 - (40 if i > 6 else 0), "SAÚDE", "Plano de saúde")
        add(d(8), "MENSALIDADE ESCOLA EXEMPLO 33.444.555/0001-66", "Escola Exemplo", -950.0,
            "EDUCAÇÃO")
        add(d(3), "DEBITO PREVIDENCIA PRIVADA PGBL", "Previdência Exemplo", -300.0,
            "SERVIÇOS DE TERCEIROS", "Não identificados")
        add(d(25), "STREAMING EXEMPLO", "Streaming Exemplo", -39.9, "ASSINATURAS", conta=CARTAO)
        add(d(6), "TARIFA PACOTE DE SERVICOS", "Tarifa Pacote de Serviços", -32.9,
            "TARIFAS BANCÁRIAS", "Pacote de serviços")
        # Alimentação (sobe nos últimos 3 meses)
        fator = 1.25 if i >= 9 else 1.0
        for dia in (2, 9, 16, 23, 29):
            add(d(dia), "SUPERMERCADO EXEMPLO", "Supermercado Exemplo",
                -round(random.uniform(180, 320) * fator, 2), "ALIMENTAÇÃO", "Supermercado",
                conta=CARTAO)
        for dia in (4, 11, 19, 26):
            add(d(dia), "PADARIA EXEMPLO", "Padaria Exemplo", -round(random.uniform(20, 45), 2),
                "ALIMENTAÇÃO", "Padaria", conta=CARTAO)
        for dia in (7, 21):
            add(d(dia), "RESTAURANTE EXEMPLO", "Restaurante Exemplo",
                -round(random.uniform(90, 180) * fator, 2), "ALIMENTAÇÃO", "Restaurante",
                conta=CARTAO)
        # Transporte e outros
        for dia in (6, 20):
            add(d(dia), "POSTO EXEMPLO", "Posto Exemplo", -round(random.uniform(180, 240), 2),
                "TRANSPORTE", "Posto de gasolina", conta=CARTAO)
        add(d(14), "APP DE TRANSPORTE", "App de Transporte", -round(random.uniform(40, 110), 2),
            "TRANSPORTE", "Transporte por aplicativo", conta=CARTAO)
        add(d(17), "DROGARIA EXEMPLO", "Drogaria Exemplo", -round(random.uniform(60, 150), 2),
            "SAÚDE", "Drogaria", conta=CARTAO)
        if i % 4 == 2:
            add(d(13), "PIX CLINICA EXEMPLO 55.666.777/0001-88", "Clínica Exemplo", -350.0,
                "SAÚDE", "Clínicas, consultas e exames")
        add(d(24), "LOJA DE ROUPAS EXEMPLO", "Loja de Roupas Exemplo",
            -round(random.uniform(80, 350), 2), "SHOPPING", "Vestuário", conta=CARTAO)
        if i % 3 == 0:
            add(d(27), "PIX ENVIADO ***.987.654-** MARIA", "Maria (pessoa)",
                -round(random.uniform(150, 400), 2), "TRANSFERÊNCIA")
        if mm == 7:
            add(d(5), "HOTEL EXEMPLO", "Hotel Exemplo", -2400.0, "LAZER", "Viagens", conta=CARTAO)
            add(d(5), "COMPANHIA AEREA EXEMPLO", "Companhia Aérea Exemplo", -1650.0, "LAZER",
                "Viagens", conta=CARTAO)
        if mm == 1:
            add(d(28), "IPVA EXEMPLO", "IPVA", -1450.0, "IMPOSTOS E TAXAS", "Estaduais")
        if mm == 2:
            add(d(15), "MATERIAL ESCOLAR LIVRARIA", "Livraria Exemplo", -620.0, "EDUCAÇÃO")

    # Compras parceladas no cartão: celular em 10x (desde mai/26), sofá em 6x (desde jul/26)
    for k, m in enumerate(pd.period_range("2026-05", "2026-09", freq="M"), start=1):
        add(f"{m.year}-{m.month:02d}-28", f"LOJA ELETRO EXEMPLO PARC {k:02d}/10",
            "Loja Eletro Exemplo", -289.9, "SHOPPING", "Compras online", conta=CARTAO, parc=k,
            parcs=10)
    for k, m in enumerate(pd.period_range("2026-07", "2026-09", freq="M"), start=1):
        add(f"{m.year}-{m.month:02d}-28", f"MOVEIS EXEMPLO PARC {k:02d}/06", "Móveis Exemplo",
            -415.0, "CASA", "Manutenções", conta=CARTAO, parc=k, parcs=6)

    t = pd.DataFrame(L)
    t["Tipo"] = ["Entrada" if v > 0 else "Saída" for v in t["Valor"]]
    t["Mês"] = t["Data"].dt.to_period("M").astype(str)
    t["DataCompra"] = pd.NaT
    return t.sort_values("Data").reset_index(drop=True)


def relatorio_exemplo():
    """PDF do relatório com os dados fictícios (bytes)."""
    dados = relatorio.montar_relatorio(transacoes_exemplo(), guardado=18000.0,
                                       hoje=datetime(2026, 10, 1, 9, 0))
    return relatorio.gerar_pdf(dados)
