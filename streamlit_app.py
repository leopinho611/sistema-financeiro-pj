import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from financeiro import (
    CATEGORIA_APLICACAO,
    carregar_arquivo,
    consolidar,
    detectar_colunas,
    formatar_reais,
    montar_transacoes,
    resumo_categorias,
    resumo_fornecedores,
    resumo_mensal,
)

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Sistema de Controle Financeiro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Identidade visual: azul-marinho, dourado e branco-osso (tema em .streamlit/config.toml)
MARINHO = "#1b2a4a"
DOURADO = "#c9a227"        # detalhes (linhas, bordas); não usado em dados
# Cores dos gráficos: marinho e dourado ajustados para contraste >= 3:1 no
# branco-osso e separação para daltonismo (validados)
COR_ENTRADAS = "#24529e"   # azul-marinho
COR_SAIDAS = "#a8801f"     # dourado escuro

st.markdown(f"""
<style>
  .cabecalho {{ border-bottom: 2px solid {DOURADO}; padding-bottom: .4rem; margin-bottom: 1.2rem; }}
  .cabecalho h1 {{ color: {MARINHO}; font-weight: 700; margin: 0; padding: 0; }}
  .cabecalho .slogan {{ text-align: right; color: #8a6d1d; font-style: italic;
                        font-size: 1.05rem; margin: 0; letter-spacing: .02em; }}
  [data-testid="stMetric"] {{ background: #fffdf8; border: 1px solid #e3d9c3;
                              border-left: 4px solid {DOURADO}; border-radius: 8px;
                              padding: .7rem 1rem; }}
  [data-testid="stMetricLabel"] p {{ color: #5b6478; }}
  [data-testid="stMetricValue"] {{ font-size: 1.55rem; }}
  h2, h3 {{ color: {MARINHO}; }}
  .dica {{ color: #7a6a45; font-size: .85rem; margin: -.3rem 0 .6rem 0; }}
  .dica::before {{ content: "☝ "; color: {DOURADO}; }}
  [data-testid="stSidebar"] {{ border-right: 2px solid {DOURADO}; }}
</style>
<div class="cabecalho">
  <h1>Sistema de Controle Financeiro</h1>
  <p class="slogan">Seus gastos na palma da mão</p>
</div>
""", unsafe_allow_html=True)


def dica(texto):
    """Observação discreta indicando que o elemento é interativo."""
    st.markdown(f'<p class="dica">{texto}</p>', unsafe_allow_html=True)


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
    arquivos = st.file_uploader(
        "Escolha seus extratos",
        type=["csv", "xlsx", "xls", "excel", "pdf", "ofx"],
        accept_multiple_files=True,
        help="Extratos em CSV ou Excel de qualquer banco, de vários meses e contas. "
             "Faturas do cartão BB também em PDF."
    )
    nome_titular = st.text_input(
        "Seu nome (opcional)",
        placeholder="Ex: Maria Silva",
        help="Pix e TED para você mesmo em outro banco viram transferência entre "
             "contas, e não gasto. Use nome e sobrenome como aparecem no extrato."
    )

# ============================================================================
# PROCESSAMENTO
# ============================================================================
if not arquivos:
    st.info("👈 Clique em 'Importar Dados' no menu")
    st.markdown("""
    ## 🚀 Como Usar
    1. Exporte seus extratos (CSV ou Excel) no app ou site do banco.
       Pode enviar vários meses e várias contas de uma vez.
    2. Fatura do cartão BB: pode enviar o PDF
    3. Confira se as colunas foram identificadas certo
    4. Veja o resumo, o mês a mês e as transações categorizadas

    **Movimentações internas** (aplicação/resgate automático, transferência entre
    suas contas e pagamento de fatura do cartão) não contam como entrada nem saída.
    """)
    st.stop()

tabelas = []
leitura = []
layouts = {}   # extratos com as mesmas colunas compartilham a identificação
for arquivo in arquivos:
    try:
        r = carregar_arquivo(arquivo.name, arquivo.getvalue())
    except Exception as e:
        leitura.append({"Arquivo": arquivo.name, "Conta": "—", "Situação": f"⚠️ ignorado: {e}"})
        continue
    r["nome"] = arquivo.name
    if r["tipo"] == "transacoes":
        tabelas.append(r["dados"])
        leitura.append({"Arquivo": arquivo.name, "Conta": r["conta"],
                        "Situação": f"✅ {len(r['dados'])} lançamentos"})
    else:
        layouts.setdefault(tuple(r["bruto"].columns), []).append(r)

for n, (cols, grupo) in enumerate(layouts.items()):
    bruto0 = grupo[0]["bruto"]
    sugestao = detectar_colunas(bruto0)
    opcoes = ["—"] + list(cols)

    def indice(coluna):
        return opcoes.index(coluna) if coluna in opcoes else 0

    completo = sugestao["data"] and sugestao["descricao"] and (sugestao["valor"] or sugestao["credito"])
    nomes = ", ".join(r["nome"] for r in grupo)
    with st.expander(f"⚙️ Colunas — {grupo[0]['conta']} ({len(grupo)} arquivo(s))",
                     expanded=not completo):
        st.caption(f"Identificadas automaticamente. Ajuste se algo estiver errado. Arquivos: {nomes}")
        c1, c2 = st.columns(2)
        col_data = c1.selectbox("Data", opcoes, index=indice(sugestao["data"]), key=f"data{n}")
        col_desc = c2.multiselect("Descrição", list(cols), default=sugestao["descricao"],
                                  help="Pode escolher mais de uma coluna; o texto é juntado.",
                                  key=f"desc{n}")
        modo = st.radio("Como o banco mostra os valores?",
                        ["Uma coluna de valor (negativo = saída)",
                         "Colunas separadas de crédito e débito"],
                        index=1 if sugestao["credito"] else 0, horizontal=True, key=f"modo{n}")
        if modo.startswith("Uma"):
            col_valor = st.selectbox("Valor", opcoes, index=indice(sugestao["valor"]), key=f"valor{n}")
            col_cred = col_deb = "—"
        else:
            c3, c4 = st.columns(2)
            col_cred = c3.selectbox("Crédito (entradas)", opcoes,
                                    index=indice(sugestao["credito"]), key=f"cred{n}")
            col_deb = c4.selectbox("Débito (saídas)", opcoes,
                                   index=indice(sugestao["debito"]), key=f"deb{n}")
            col_valor = "—"
        st.dataframe(bruto0.head(5), width="stretch")

    colunas = {k: (None if v == "—" else v) for k, v in
               {"data": col_data, "valor": col_valor,
                "credito": col_cred, "debito": col_deb}.items()}
    colunas["descricao"] = col_desc
    for r in grupo:
        try:
            t = montar_transacoes(r["bruto"], colunas, r["conta"])
            tabelas.append(t)
            leitura.append({"Arquivo": r["nome"], "Conta": r["conta"],
                            "Situação": f"✅ {len(t)} lançamentos"})
        except ValueError as e:
            leitura.append({"Arquivo": r["nome"], "Conta": r["conta"],
                            "Situação": f"⚠️ {e} (ajuste em ⚙️ Colunas)"})

todos = consolidar(tabelas, nome_titular)

with st.expander(f"📂 Arquivos lidos ({len(arquivos)})",
                 expanded=any("Colunas" in x["Situação"] for x in leitura)):
    st.dataframe(pd.DataFrame(leitura), hide_index=True, width="stretch")

if todos.empty:
    st.warning("Nenhuma transação encontrada. Confira os arquivos e as colunas acima.")
    st.stop()

# Filtros de conta e período
with st.sidebar:
    st.divider()
    contas = sorted(todos["Conta"].unique())
    filtro_contas = st.multiselect("Contas", contas, default=contas)
    inicio, fim = todos["Data"].min().date(), todos["Data"].max().date()
    periodo_sel = st.date_input("Período", value=(inicio, fim), min_value=inicio,
                                max_value=fim, format="DD/MM/YYYY")

df = todos[todos["Conta"].isin(filtro_contas)]
if isinstance(periodo_sel, tuple) and len(periodo_sel) == 2:
    df = df[(df["Data"].dt.date >= periodo_sel[0]) & (df["Data"].dt.date <= periodo_sel[1])]
if df.empty:
    st.warning("Nenhuma transação com esses filtros.")
    st.stop()

internas = df[df["Tipo"] == "Interna"]
periodo = f"{df['Data'].min():%d/%m/%Y} a {df['Data'].max():%d/%m/%Y}"
st.success(f"✅ {len(df) - len(internas)} transações de {periodo} "
           f"({len(internas)} movimentações internas à parte)")

entradas = df.loc[df["Tipo"] == "Entrada", "Valor"].sum()
saidas = -df.loc[df["Tipo"] == "Saída", "Valor"].sum()
aplicado = -internas.loc[internas["Categoria"] == CATEGORIA_APLICACAO, "Valor"].sum()

tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumo", "📅 Mês a Mês", "📋 Transações", "📥 Download"])

# ----------------------------------------------------------------------------
with tab1:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Entradas", formatar_reais(entradas))
    m2.metric("Saídas", formatar_reais(saidas))
    m3.metric("Saldo do período", formatar_reais(entradas - saidas))
    m4.metric("Aplicado (líquido)", formatar_reais(aplicado),
              help="Aplicações menos resgates no período (Rende Fácil, caixinhas, fundos...). "
                   "Não entra em entradas nem saídas.")

    cats = resumo_categorias(df)
    if cats.empty:
        st.info("Não há saídas no período.")
    else:
        st.subheader("Saídas por categoria")
        dica("Passe o mouse sobre as barras para ver os valores")
        st.altair_chart(grafico_categorias(cats), width="stretch")
        dica("Clique numa categoria para ver os maiores fornecedores · "
             "clique no título de uma coluna para classificar")
        selecao = st.dataframe(tabela_em_reais(cats, ["Total"], ["% das saídas"]),
                               hide_index=True, width="stretch", key="tabela_categorias",
                               on_select="rerun", selection_mode="single-row")

        linhas = selecao.selection.rows if selecao else []
        if linhas:
            categoria = cats.iloc[linhas[0]]["Categoria"]
            forn = resumo_fornecedores(df, categoria)
            st.subheader(f"Fornecedores — {categoria.capitalize()}")
            st.caption(f"Os {min(10, len(forn))} que mais receberam nesta categoria; "
                       "os demais somados em \"Outros fornecedores\".")
            st.dataframe(tabela_em_reais(forn, ["Total"], ["% da categoria"]),
                         hide_index=True, width="stretch")

        outros = cats.loc[cats["Categoria"] == "OUTRO", "% das saídas"]
        if not outros.empty and outros.iloc[0] > 20:
            st.caption(f"ℹ️ {outros.iloc[0]:.0f}% das saídas ficaram em OUTRO. "
                       "Veja quais são na aba 📋 Transações.")

    if not internas.empty:
        st.subheader("Movimentações internas")
        st.caption("Dinheiro que só mudou de lugar: não conta como entrada nem saída.")
        resumo_int = (internas.groupby("Categoria")["Valor"]
                      .agg(Lançamentos="count",
                           Saiu=lambda v: -v[v < 0].sum(),
                           Entrou=lambda v: v[v > 0].sum())
                      .reset_index())
        st.dataframe(tabela_em_reais(resumo_int, ["Saiu", "Entrou"]),
                     hide_index=True, width="stretch")

# ----------------------------------------------------------------------------
with tab2:
    mensal = resumo_mensal(df)
    st.subheader("Entradas × Saídas por mês")
    dica("Passe o mouse sobre as barras para ver os valores")
    st.altair_chart(grafico_mensal(mensal), width="stretch")
    st.dataframe(tabela_em_reais(mensal.assign(Mês=mensal["Mês"].map(rotulo_mes)),
                                 ["Entradas", "Saídas", "Saldo"]),
                 hide_index=True, width="stretch")

    if len(mensal) > 1:
        st.subheader("Saídas por categoria em cada mês")
        por_mes = (df[df["Tipo"] == "Saída"].assign(Total=lambda d: -d["Valor"])
                   .pivot_table(index="Categoria", columns="Mês", values="Total",
                                aggfunc="sum", fill_value=0))
        por_mes = por_mes.loc[por_mes.sum(axis=1).sort_values(ascending=False).index]
        por_mes.columns = [rotulo_mes(m) for m in por_mes.columns]
        st.dataframe(por_mes.map(formatar_reais), width="stretch")

# ----------------------------------------------------------------------------
with tab3:
    f1, f2, f3 = st.columns([2, 2, 1])
    filtro_cat = f1.multiselect("Categoria", sorted(df["Categoria"].unique()))
    busca = f2.text_input("Buscar na descrição")
    ver_internas = f3.toggle("Mostrar internas", value=False)
    visao = df if ver_internas else df[df["Tipo"] != "Interna"]
    if filtro_cat:
        visao = visao[visao["Categoria"].isin(filtro_cat)]
    if busca:
        visao = visao[visao["Descrição"].str.contains(busca, case=False, regex=False)]
    st.caption(f"{len(visao)} transações — total {formatar_reais(visao['Valor'].sum())}")
    dica("Clique no título de uma coluna para classificar · use os filtros acima para refinar")
    st.dataframe(
        visao[["Data", "Conta", "Fornecedor", "Descrição", "Valor", "Tipo", "Categoria"]],
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
