"""Relatório PDF do Plus. Dados inventados."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import relatorio  # noqa: E402


def _t():
    linhas = []
    for m in range(1, 7):
        d = f"2026-{m:02d}"
        linhas += [
            (f"{d}-05", "Empresa Exemplo", 5000.0, "RECEITA", "Recebido de empresas"),
            (f"{d}-10", "Aluguel Exemplo", -1500.0, "CASA", "Aluguel"),
            (f"{d}-12", "Mercado Exemplo", -800.0 - (300 if m > 3 else 0), "ALIMENTAÇÃO",
             "Supermercado"),
            (f"{d}-20", "Clinica Exemplo", -200.0, "SAÚDE", "Clínicas, consultas e exames"),
        ]
    t = pd.DataFrame(linhas, columns=["Data", "Fornecedor", "Valor", "Categoria", "Subcategoria"])
    t["Data"] = pd.to_datetime(t["Data"])
    t["Descrição"] = t["Fornecedor"].str.upper()
    t["Tipo"] = ["Entrada" if v > 0 else "Saída" for v in t["Valor"]]
    t["Conta"] = "Banco Exemplo"
    t["Mês"] = t["Data"].dt.to_period("M").astype(str)
    return t


def test_montar_relatorio():
    d = relatorio.montar_relatorio(_t())
    assert round(d["entradas"], 2) == 30000.0
    assert d["n_meses"] == 6
    assert d["nota"] in ("bom", "atencao", "alerta")
    assert any("Alimentação" in f for f in d["destaques"])
    assert 1 <= len(d["sugestoes"]) <= 3
    assert len(d["comprometido"]) == 3


def test_gerar_pdf():
    pdf = relatorio.gerar_pdf(relatorio.montar_relatorio(_t(), guardado=10000.0))
    assert pdf.startswith(b"%PDF")


def test_relatorio_de_exemplo_usa_dados_ficticios():
    import exemplo
    t = exemplo.transacoes_exemplo()
    assert set(t["Conta"]) == {"Banco Azul", "Banco Azul Cartão"}
    assert t["Fornecedor"].str.contains("Exemplo|pessoa|IPVA|Tarifa|App de|Cliente Alfa").all()
    assert exemplo.relatorio_exemplo().startswith(b"%PDF")


def test_relatorio_sem_parcelas_e_com_um_mes():
    t = _t()
    um_mes = t[t["Mês"] == "2026-01"]
    assert relatorio.gerar_pdf(relatorio.montar_relatorio(um_mes)).startswith(b"%PDF")


def test_fornecedor_generico():
    assert relatorio.fornecedor_generico("Pagamento Pix")
    assert relatorio.fornecedor_generico("Debito Convenios")
    assert relatorio.fornecedor_generico("")
    assert not relatorio.fornecedor_generico("Padaria Exemplo")


def test_avisos_de_dados_faltando():
    t = _t()
    extra = pd.DataFrame({
        "Data": pd.to_datetime(["2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10"]),
        "Fornecedor": ["Pagamento Pix", "Pagamento Pix", "Pagto Cartão", "Pagto Cartão"],
        "Valor": [-900.0, -900.0, -1200.0, -1200.0],
        "Categoria": ["TRANSFERÊNCIA", "TRANSFERÊNCIA", "CARTÃO DE CRÉDITO", "CARTÃO DE CRÉDITO"],
        "Subcategoria": ["", "", "", ""]})
    extra["Descrição"] = extra["Fornecedor"].str.upper()
    extra["Tipo"], extra["Conta"] = "Saída", "Banco Exemplo"
    extra["Mês"] = extra["Data"].dt.to_period("M").astype(str)
    d = relatorio.montar_relatorio(pd.concat([t, extra], ignore_index=True))
    assert d["qualidade"]["faturas"] == 2400.0
    assert d["qualidade"]["sem_nome"][0]["conta"] == "Banco Exemplo"
    texto = " ".join(d["destaques"] + d["sugestoes"])
    assert "faturas" in texto and "sem o nome de quem recebeu" in texto
    assert any("Envie também as faturas" in s for s in d["sugestoes"])


def test_sem_sugestao_de_teto_para_gasto_pequeno():
    t = _t()
    t.loc[t["Categoria"] == "ALIMENTAÇÃO", "Valor"] = -10.0
    d = relatorio.montar_relatorio(t)
    assert not any("teto" in s for s in d["sugestoes"])
