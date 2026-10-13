import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from financeiro import (
    detectar_colunas,
    formatar_reais,
    ler_extrato,
    montar_transacoes,
    resumo_categorias,
    resumo_mensal,
)

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Sistema Financeiro PJ",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cores dos gráficos (paleta categórica validada para daltonismo: slots 1 e 2)
COR_ENTRADAS = "#2a78d6"   # azul
COR_SAIDAS = "#eb6834"     # laranja

st.title("💰 Sistema de Controle Financeiro - PJ/Autônomo")
st.markdown("Importe o extrato bancário e veja para onde vai o seu dinheiro")


# Eixos em formato brasileiro: 1.500 em vez de 1,500
EIXO_REAIS = alt.Axis(labelExpr="replace(format(datum.value, ',.0f'), ',', '.')",
                      title=None, grid=True, gridOpacity=0.4)
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def rotulo_mes(mes):
    """'2026-07' -> 'jul/26'"""
    ano, m = mes.split("-")
    return f"{MESES[int(m) - 1]}/{ano[2:]}"


def grafico_categorias(cats):
    dados = cats.assign(Valor=cats["Total"].map(formatar_reais),
                        Pct=cats["% das saídas"].map(lambda v: f"{v:.1f}%".replace(".", ",")))
    return (
        alt.Chart(dados)
        .mark_bar(color=COR_SAIDAS, cornerRadiusEnd=4)
        .encode(
            x=alt.X("Total:Q", axis=EIXO_REAIS),
            y=alt.Y("Categoria:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            tooltip=[alt.Tooltip("Categoria:N"), alt.Tooltip("Valor:N", title="Total"),
                     alt.Tooltip("Pct:N", title="% das saídas"),
                     alt.Tooltip("Transações:Q")],
        )
        .properties(height=max(160, 32 * len(dados)))
    )


def grafico_mensal(mensal):
    longo = mensal.melt(id_vars="Mês", value_vars=["Entradas", "Saídas"],
                        var_name="Tipo", value_name="Total")
    longo["Rótulo"] = longo["Mês"].map(rotulo_mes)
    longo["Valor"] = longo["Total"].map(formatar_reais)
    ordem = [rotulo_mes(m) for m in mensal["Mês"]]
    return (
        alt.Chart(longo)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Rótulo:N", sort=ordem, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("Tipo:N", sort=["Entradas", "Saídas"]),
            y=alt.Y("Total:Q", axis=EIXO_REAIS),
            color=alt.Color("Tipo:N", sort=["Entradas", "Saídas"],
                            scale=alt.Scale(domain=["Entradas", "Saídas"],
                                            range=[COR_ENTRADAS, COR_SAIDAS]),
                            legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("Rótulo:N", title="Mês"), alt.Tooltip("Tipo:N"),
                     alt.Tooltip("Valor:N", title="Total")],
        )
        .properties(height=320)
    )


def tabela_em_reais(df, colunas_reais, colunas_pct=()):
    """Cópia do DataFrame com valores formatados em R$ para exibição."""
    exibir = df.copy()
    for c in colunas_reais:
        exibir[c] = exibir[c].map(formatar_reais)
    for c in colunas_pct:
        exibir[c] = exibir[c].map(lambda v: f"{v:.1f}%".replace(".", ","))
    return exibir


# ============================================================================
# SIDEBAR - UPLOAD
# ============================================================================
with st.sidebar:
    st.header("📁 Importar Dados")
    arquivo = st.file_uploader(
        "Escolha seu extrato bancário",
        type=["csv", "xlsx"],
        help="CSV ou XLSX de qualquer banco"
    )

# ============================================================================
# PROCESSAMENTO
# ============================================================================
if not arquivo:
    st.info("👈 Clique em 'Importar Dados' no menu")
    st.markdown("""
    ## 🚀 Como Usar
    1. Exporte seu extrato bancário (CSV ou XLSX) no app ou site do banco
    2. Clique em 'Importar Dados' e selecione o arquivo
    3. Confira se as colunas foram identificadas certo
    4. Veja o resumo, o mês a mês e as transações categorizadas
    """)
    st.stop()

try:
    bruto = ler_extrato(arquivo.name, arquivo.getvalue())
except Exception as e:
    st.error(f"Não foi possível ler o arquivo: {e}")
    st.stop()

sugestao = detectar_colunas(bruto)
opcoes = ["—"] + list(bruto.columns)


def indice(coluna):
    return opcoes.index(coluna) if coluna in opcoes else 0


with st.expander("⚙️ Colunas do extrato", expanded=not (sugestao["data"] and sugestao["descricao"]
                                                       and (sugestao["valor"] or sugestao["credito"]))):
    st.caption("Identificadas automaticamente. Ajuste se algo estiver errado.")
    c1, c2 = st.columns(2)
    col_data = c1.selectbox("Data", opcoes, index=indice(sugestao["data"]))
    col_desc = c2.multiselect("Descrição", list(bruto.columns), default=sugestao["descricao"],
                              help="Pode escolher mais de uma coluna; o texto é juntado.")
    modo = st.radio("Como o banco mostra os valores?",
                    ["Uma coluna de valor (negativo = saída)",
                     "Colunas separadas de crédito e débito"],
                    index=1 if sugestao["credito"] else 0, horizontal=True)
    if modo.startswith("Uma"):
        col_valor = st.selectbox("Valor", opcoes, index=indice(sugestao["valor"]))
        col_cred = col_deb = "—"
    else:
        c3, c4 = st.columns(2)
        col_cred = c3.selectbox("Crédito (entradas)", opcoes, index=indice(sugestao["credito"]))
        col_deb = c4.selectbox("Débito (saídas)", opcoes, index=indice(sugestao["debito"]))
        col_valor = "—"
    st.dataframe(bruto.head(5), width="stretch")

colunas = {k: (None if v == "—" else v) for k, v in
           {"data": col_data, "valor": col_valor,
            "credito": col_cred, "debito": col_deb}.items()}
colunas["descricao"] = col_desc

try:
    df = montar_transacoes(bruto, colunas)
except ValueError as e:
    st.warning(f"⚠️ {e} (em '⚙️ Colunas do extrato', acima)")
    st.stop()

if df.empty:
    st.warning("Nenhuma transação encontrada com essas colunas. Confira em '⚙️ Colunas do extrato'.")
    st.stop()

periodo = f"{df['Data'].min():%d/%m/%Y} a {df['Data'].max():%d/%m/%Y}"
st.success(f"✅ {len(df)} transações de {periodo}")

entradas = df.loc[df["Valor"] > 0, "Valor"].sum()
saidas = -df.loc[df["Valor"] < 0, "Valor"].sum()

tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumo", "📅 Mês a Mês", "📋 Transações", "📥 Download"])

# ----------------------------------------------------------------------------
with tab1:
    m1, m2, m3 = st.columns(3)
    m1.metric("Entradas", formatar_reais(entradas))
    m2.metric("Saídas", formatar_reais(saidas))
    m3.metric("Saldo do período", formatar_reais(entradas - saidas))

    cats = resumo_categorias(df)
    if cats.empty:
        st.info("Não há saídas no período.")
    else:
        st.subheader("Saídas por categoria")
        st.altair_chart(grafico_categorias(cats), width="stretch")
        st.dataframe(tabela_em_reais(cats, ["Total"], ["% das saídas"]),
                     hide_index=True, width="stretch")

        outros = cats.loc[cats["Categoria"] == "OUTRO", "% das saídas"]
        if not outros.empty and outros.iloc[0] > 20:
            st.caption(f"ℹ️ {outros.iloc[0]:.0f}% das saídas ficaram em OUTRO. "
                       "Veja quais são na aba 📋 Transações.")

# ----------------------------------------------------------------------------
with tab2:
    mensal = resumo_mensal(df)
    st.subheader("Entradas × Saídas por mês")
    st.altair_chart(grafico_mensal(mensal), width="stretch")
    st.dataframe(tabela_em_reais(mensal.assign(Mês=mensal["Mês"].map(rotulo_mes)),
                                 ["Entradas", "Saídas", "Saldo"]),
                 hide_index=True, width="stretch")

    if len(mensal) > 1:
        st.subheader("Saídas por categoria em cada mês")
        por_mes = (df[df["Valor"] < 0].assign(Total=lambda d: -d["Valor"])
                   .pivot_table(index="Categoria", columns="Mês", values="Total",
                                aggfunc="sum", fill_value=0))
        por_mes = por_mes.loc[por_mes.sum(axis=1).sort_values(ascending=False).index]
        por_mes.columns = [rotulo_mes(m) for m in por_mes.columns]
        st.dataframe(por_mes.map(formatar_reais), width="stretch")

# ----------------------------------------------------------------------------
with tab3:
    f1, f2 = st.columns(2)
    filtro_cat = f1.multiselect("Categoria", sorted(df["Categoria"].unique()))
    busca = f2.text_input("Buscar na descrição")
    visao = df
    if filtro_cat:
        visao = visao[visao["Categoria"].isin(filtro_cat)]
    if busca:
        visao = visao[visao["Descrição"].str.contains(busca, case=False, regex=False)]
    st.caption(f"{len(visao)} transações — total {formatar_reais(visao['Valor'].sum())}")
    st.dataframe(
        visao[["Data", "Descrição", "Valor", "Tipo", "Categoria"]],
        hide_index=True, width="stretch",
        column_config={
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        },
    )

# ----------------------------------------------------------------------------
with tab4:
    st.subheader("Exportar")
    exportar = df.copy()
    exportar["Data"] = exportar["Data"].dt.strftime("%d/%m/%Y")
    hoje = datetime.now().strftime("%Y%m%d")

    # CSV no padrão do Excel brasileiro: ponto e vírgula e vírgula decimal
    csv = exportar.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("📥 Download CSV", csv, f"extrato_{hoje}.csv", "text/csv")

    xlsx = io.BytesIO()
    with pd.ExcelWriter(xlsx, engine="openpyxl") as planilha:
        exportar.to_excel(planilha, sheet_name="Transações", index=False)
        resumo_categorias(df).to_excel(planilha, sheet_name="Por categoria", index=False)
        resumo_mensal(df).to_excel(planilha, sheet_name="Mês a mês", index=False)
    st.download_button(
        "📥 Download XLSX", xlsx.getvalue(), f"extrato_{hoje}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
