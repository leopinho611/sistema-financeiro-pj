import io
from datetime import datetime
from html import escape

import importlib
import sys

import altair as alt
import pandas as pd
import streamlit as st

# Depois de uma atualização, o Streamlit Cloud recarrega este arquivo mas pode
# manter na memória a versão antiga de financeiro.py e regras.py, e o app quebra
# com ImportError até alguém reiniciar. Recarregá-los aqui evita isso.
for _modulo in ("financeiro", "regras"):   # nessa ordem: regras importa financeiro
    if _modulo in sys.modules:
        importlib.reload(sys.modules[_modulo])

from financeiro import (
    CATEGORIA_APLICACAO,
    aplicar_regras,
    carregar_arquivo,
    categoria_do_cnae,
    categorias_editaveis,
    chave_fornecedor,
    consolidar,
    detectar_colunas,
    eh_empresa,
    extrair_cnpj,
    formatar_reais,
    montar_transacoes,
    subcategorias_de,
    resumo_categorias,
    resumo_fornecedores,
    resumo_mensal,
    resumo_subcategorias,
)
from regras import RepositorioRegras, consultar_cnpj, juntar, nova_regra, regras_vazias

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Sistema de Controle Financeiro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Identidade visual: azul-marinho, dourado e branco-osso. Os temas claro e escuro
# ficam em .streamlit/config.toml; o CSS abaixo herda a cor do texto do tema
# (currentColor) para funcionar nos dois.
DOURADO = "#c9a227"        # detalhes (linhas, bordas); não usado em dados
# Cores dos gráficos: validadas para contraste >= 3:1 e separação para daltonismo
# tanto no fundo branco-osso quanto no azul-marinho escuro
COR_ENTRADAS = "#3d6bc4"   # azul
COR_SAIDAS = "#a8801f"     # dourado escuro

st.markdown(f"""
<style>
  .cabecalho {{ border-bottom: 2px solid {DOURADO}; padding-bottom: .4rem; margin-bottom: 1.2rem; }}
  .cabecalho h1 {{ font-weight: 700; margin: 0; padding: 0; }}
  .cabecalho .slogan {{ text-align: right; color: {DOURADO}; font-style: italic;
                        font-size: 1.05rem; margin: 0; letter-spacing: .02em; }}
  [data-testid="stMetric"] {{ background: color-mix(in srgb, currentColor 4%, transparent);
                              border: 1px solid color-mix(in srgb, {DOURADO} 35%, transparent);
                              border-left: 4px solid {DOURADO}; border-radius: 8px;
                              padding: .7rem 1rem; }}
  [data-testid="stMetricLabel"] p {{ opacity: .75; }}
  [data-testid="stMetricValue"] {{ font-size: 1.55rem; }}
  .dica {{ font-size: .85rem; margin: -.3rem 0 .6rem 0; opacity: .7; }}
  .dica::before {{ content: "☝ "; color: {DOURADO}; }}
  [data-testid="stSidebar"] {{ border-right: 2px solid {DOURADO}; }}

  /* Tabela de categorias que abre os fornecedores na própria linha */
  .tabcat {{ border: 1px solid color-mix(in srgb, {DOURADO} 40%, transparent);
             border-radius: 8px; overflow: hidden; font-size: .92rem; margin-bottom: 1rem; }}
  .tabcat .linha {{ display: grid; gap: .75rem; align-items: center; padding: .55rem .9rem;
                    grid-template-columns: minmax(0, 2.2fr) 1.2fr .8fr 1.5fr; }}
  .tabcat .cab {{ font-size: .8rem; opacity: .7;
                  border-bottom: 1px solid color-mix(in srgb, {DOURADO} 40%, transparent); }}
  .tabcat details {{ border-bottom: 1px solid color-mix(in srgb, currentColor 10%, transparent); }}
  .tabcat details:last-child {{ border-bottom: none; }}
  .tabcat summary {{ cursor: pointer; list-style: none; }}
  .tabcat summary::-webkit-details-marker {{ display: none; }}
  .tabcat summary:hover {{ background: color-mix(in srgb, {DOURADO} 12%, transparent); }}
  .tabcat summary .nome::before {{ content: "▸"; color: {DOURADO}; display: inline-block;
                                   width: 1.1em; transition: transform .15s; }}
  .tabcat details[open] > summary {{ background: color-mix(in srgb, {DOURADO} 9%, transparent);
                                     font-weight: 600; }}
  .tabcat details[open] > summary .nome::before {{ transform: rotate(90deg); }}
  /* Linhas abertas ganham fundo azul claro; cada nível aberto escurece um pouco mais */
  .tabcat .detalhe {{ background: color-mix(in srgb, {COR_ENTRADAS} 13%, transparent); }}
  .tabcat .sub {{ border-bottom: none;
                  border-top: 1px solid color-mix(in srgb, currentColor 8%, transparent); }}
  .tabcat .sub > summary {{ font-size: .9rem; }}
  .tabcat .sub > summary .nome {{ padding-left: 1.4rem; }}
  .tabcat .sub[open] > summary {{ background: color-mix(in srgb, {COR_ENTRADAS} 8%, transparent);
                                  font-weight: 600; }}
  .tabcat .sub .forn .nome {{ padding-left: 2.8rem; }}
  .tabcat .forn .nome {{ padding-left: 1.4rem; }}
  .tabcat .forn {{ font-size: .88rem;
                   border-top: 1px dashed color-mix(in srgb, currentColor 10%, transparent); }}
  .tabcat .forn.outros {{ opacity: .75; font-style: italic; }}
  .tabcat .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .tabcat .pct {{ display: flex; align-items: center; gap: .5rem; }}
  .tabcat .pct .trilho {{ flex: 1; height: 6px; border-radius: 3px; overflow: hidden;
                          background: color-mix(in srgb, currentColor 12%, transparent); }}
  .tabcat .pct .trilho i {{ display: block; height: 100%; border-radius: 3px;
                            background: {COR_SAIDAS}; }}
  .tabcat .pct b {{ font-weight: inherit; min-width: 3.2em; text-align: right;
                    font-variant-numeric: tabular-nums; }}
  @media (max-width: 640px) {{
    .tabcat .linha {{ grid-template-columns: minmax(0, 1.6fr) 1.2fr 1fr; }}
    .tabcat .qtd {{ display: none; }}
  }}
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


def _pct(v):
    return f"{v:.1f}%".replace(".", ",")


def _linha_html(classe, nome, total, qtd, pct, tag="div"):
    largura = max(0.0, min(100.0, pct))
    return (f'<{tag} class="linha {classe}"><span class="nome">{escape(str(nome))}</span>'
            f'<span class="num">{formatar_reais(total)}</span>'
            f'<span class="num qtd">{int(qtd)}</span>'
            f'<span class="pct"><span class="trilho"><i style="width:{largura:.1f}%"></i></span>'
            f'<b>{_pct(pct)}</b></span></{tag}>')


def _linhas_fornecedores(df, categoria, subcategoria=None):
    partes = []
    for _, f in resumo_fornecedores(df, categoria, subcategoria=subcategoria).iterrows():
        classe = "forn outros" if f["Fornecedor"].startswith("Outros fornecedores") else "forn"
        partes.append(_linha_html(classe, f["Fornecedor"], f["Total"], f["Transações"],
                                  f["% da categoria"]))
    return partes


def tabela_categorias_html(cats, df):
    """Categoria → subcategoria → 10 maiores fornecedores, abrindo logo abaixo da linha.

    Categorias sem subcategorias abrem direto nos fornecedores. O % de cada linha
    aberta é sobre o grupo de cima (subcategoria sobre a categoria, fornecedor
    sobre a subcategoria).
    """
    partes = ['<div class="tabcat">',
              '<div class="linha cab"><span>Categoria</span><span class="num">Total</span>'
              '<span class="num qtd">Transações</span><span>% das saídas</span></div>']
    for _, c in cats.iterrows():
        partes.append("<details>")
        partes.append(_linha_html("", c["Categoria"], c["Total"], c["Transações"],
                                  c["% das saídas"], tag="summary"))
        partes.append('<div class="detalhe">')
        subs = resumo_subcategorias(df, c["Categoria"])
        if subs.empty:
            partes += _linhas_fornecedores(df, c["Categoria"])
        else:
            for _, sc in subs.iterrows():
                partes.append('<details class="sub">')
                partes.append(_linha_html("", sc["Subcategoria"], sc["Total"], sc["Transações"],
                                          sc["% da categoria"], tag="summary"))
                partes.append('<div class="detalhe">')
                partes += _linhas_fornecedores(df, c["Categoria"], sc["Subcategoria"])
                partes.append("</div></details>")
        partes.append("</div></details>")
    partes.append("</div>")
    return "".join(partes)


def tabela_em_reais(df, colunas_reais, colunas_pct=()):
    """Cópia do DataFrame com valores formatados em R$ para exibição."""
    exibir = df.copy()
    for c in colunas_reais:
        exibir[c] = exibir[c].map(formatar_reais)
    for c in colunas_pct:
        exibir[c] = exibir[c].map(lambda v: f"{v:.1f}%".replace(".", ","))
    return exibir


# ============================================================================
# REGRAS LEMBRADAS
# ============================================================================
def ler_segredo(nome):
    """Segredo do Streamlit; st.secrets falha quando não existe secrets.toml."""
    try:
        return st.secrets.get(nome)
    except Exception:
        return None


repo_regras = RepositorioRegras(ler_segredo("GITHUB_TOKEN"), ler_segredo("GITHUB_REPO"),
                                ler_segredo("GITHUB_BRANCH") or "main")
st.session_state.setdefault("versao_regras", 0)


def _regras_dos_secrets():
    """Regras pessoais guardadas no segredo REGRAS_PESSOAIS (CSV): Pix para pessoas que
    não podem ir para o arquivo público. Valem sempre, mas não são exibidas."""
    texto = ler_segredo("REGRAS_PESSOAIS")
    if not texto:
        return regras_vazias()
    try:
        return juntar(regras_vazias(), pd.read_csv(io.StringIO(texto.strip()), dtype=str)
                      .fillna("").reindex(columns=regras_vazias().columns, fill_value=""))
    except Exception:
        st.warning("O segredo REGRAS_PESSOAIS não está num formato válido e foi ignorado.")
        return regras_vazias()


regras_privadas = _regras_dos_secrets()
st.session_state.setdefault("regras_pessoais", regras_vazias())


@st.cache_data(ttl=60, show_spinner=False)
def regras_compartilhadas(_versao):
    """Lidas no máximo a cada minuto (para ver as regras salvas por outras pessoas)."""
    return repo_regras.carregar()


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def consultar_cnpj_cache(cnpj):
    return consultar_cnpj(cnpj)


def salvar_regras(novas_comp, novas_pess, descricao):
    """Grava as regras novas; empresas no arquivo compartilhado, pessoas só na sessão."""
    destino = None
    if not novas_comp.empty:
        atuais = repo_regras.carregar()  # sem cache: não apagar regra salva por outra pessoa
        destino = repo_regras.salvar(juntar(atuais, novas_comp), f"Regras: {descricao}")
    if not novas_pess.empty:
        st.session_state["regras_pessoais"] = juntar(st.session_state["regras_pessoais"],
                                                     novas_pess)
    st.session_state["versao_regras"] += 1
    regras_compartilhadas.clear()
    partes = []
    if not novas_comp.empty:
        onde = "no GitHub (vale para todos)" if destino == "github" else \
            "neste servidor (configure o GitHub para guardar de vez)"
        partes.append(f"{len(novas_comp)} regra(s) de empresa salva(s) {onde}")
    if not novas_pess.empty:
        partes.append(f"{len(novas_pess)} regra(s) pessoal(is) guardada(s) nesta sessão")
    st.session_state["aviso_regras"] = " · ".join(partes)


# ============================================================================
# SIDEBAR - UPLOAD
# ============================================================================
with st.sidebar:
    st.header("📁 Importar Dados")
    arquivos = st.file_uploader(
        "Escolha seus extratos",
        type=["csv", "xlsx", "xls", "excel", "pdf", "ofx"],
        accept_multiple_files=True,
        help="Extratos em CSV, Excel ou OFX de qualquer banco, de vários meses e contas. "
             "Em PDF: extrato da conta Nubank e fatura do cartão BB. Pode mandar o mesmo "
             "mês em mais de um formato: as repetições são descartadas."
    )
    st.caption("🌓 Tema claro ou escuro: menu ⋮ no canto superior direito → Settings")
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
    1. Exporte seus extratos (CSV, Excel ou OFX) no app ou site do banco.
       Pode enviar vários meses e várias contas de uma vez.
    2. Em PDF: extrato da conta Nubank e fatura do cartão BB. Se mandar o mesmo mês
       em mais de um formato, as repetições são descartadas
    3. Confira se as colunas foram identificadas certo
    4. Veja o resumo, o mês a mês e as transações categorizadas

    **Movimentações internas** (aplicação/resgate automático, transferência entre
    suas contas e pagamento de fatura do cartão) não contam como entrada nem saída.
    """)
    st.stop()

tabelas = []
leitura = []
layouts = {}   # extratos com as mesmas colunas compartilham a identificação
# CSV/Excel primeiro, depois OFX e PDF: quando o mesmo mês vem em mais de um formato,
# fica a versão do primeiro (o CSV tem a descrição mais completa)
ORDEM_FORMATO = {"csv": 0, "xlsx": 0, "xls": 0, "excel": 0, "ofx": 1, "pdf": 2}
arquivos = sorted(arquivos, key=lambda a: ORDEM_FORMATO.get(a.name.lower().rsplit(".", 1)[-1], 3))
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
# Regras lembradas (compartilhadas + pessoais) vencem as palavras-chave
regras_comp = regras_compartilhadas(st.session_state["versao_regras"])
regras_todas = juntar(juntar(regras_comp, regras_privadas), st.session_state["regras_pessoais"])
todos = aplicar_regras(todos, regras_todas)

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

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Resumo", "📅 Mês a Mês", "📋 Transações",
                                        "📥 Download", "🏷️ Classificar"])

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
        dica("Clique numa categoria para abrir as subcategorias e os maiores fornecedores · "
             "nas linhas abertas, o % é sobre o grupo de cima")
        st.markdown(tabela_categorias_html(cats, df), unsafe_allow_html=True)

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
        visao[["Data", "Conta", "Fornecedor", "Descrição", "Valor", "Tipo", "Categoria",
               "Subcategoria"]],
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

# ----------------------------------------------------------------------------
with tab5:
    if st.session_state.get("aviso_regras"):
        st.success(st.session_state.pop("aviso_regras"), icon="✅")

    st.subheader("Corrigir categorias por fornecedor")
    dica("Escolha a categoria e a subcategoria na tabela e clique em Salvar · "
         "o app lembra nas próximas vezes, para todos os lançamentos desse fornecedor")
    so_pendentes = st.toggle("Mostrar só OUTRO e TRANSFERÊNCIA", value=True)

    saidas = todos[todos["Tipo"] == "Saída"].assign(
        chave=lambda d: d["FornecedorOriginal"].map(chave_fornecedor))
    grupo = (saidas.groupby("chave")
             .agg(Fornecedor=("Fornecedor", lambda v: max(v.unique(), key=len)),
                  Categoria=("Categoria", lambda v: v.mode().iat[0]),
                  Subcategoria=("Subcategoria", lambda v: v.mode().iat[0]),
                  Total=("Valor", lambda v: -v.sum()),
                  Transações=("Valor", "count"))
             .sort_values("Total", ascending=False).reset_index())
    if so_pendentes:
        grupo = grupo[grupo["Categoria"].isin(["OUTRO", "TRANSFERÊNCIA"])].reset_index(drop=True)
    SEM_SUB = "—"  # categoria sem subcategorias
    grupo["Subcategoria"] = grupo["Subcategoria"].replace("", SEM_SUB).fillna(SEM_SUB)
    grupo["Valor"] = grupo["Total"].map(formatar_reais)

    todas_subs = [SEM_SUB] + sorted({x for c in categorias_editaveis()
                                     for x in subcategorias_de(c) if x})
    editado = st.data_editor(
        grupo, hide_index=True, width="stretch", key=f"editor_regras_{so_pendentes}",
        column_order=["Fornecedor", "Categoria", "Subcategoria", "Valor", "Transações"],
        disabled=["chave", "Fornecedor", "Valor", "Transações"],
        column_config={
            "Categoria": st.column_config.SelectboxColumn(options=categorias_editaveis(),
                                                          required=True),
            "Subcategoria": st.column_config.SelectboxColumn(
                options=todas_subs, help="Se não combinar com a categoria, vira \"Outros\""),
            "Valor": st.column_config.TextColumn("Total"),
        },
    )
    mudou = editado[(editado["Categoria"] != grupo["Categoria"])
                    | (editado["Subcategoria"].fillna(SEM_SUB) != grupo["Subcategoria"])]
    if st.button(f"💾 Salvar e lembrar ({len(mudou)})", type="primary", disabled=mudou.empty):
        comp, pess = [], []
        for _, r in mudou.iterrows():
            validas = subcategorias_de(r["Categoria"])
            sub = r["Subcategoria"] if r["Subcategoria"] in validas else validas[-1]
            linhas = saidas[saidas["chave"] == r["chave"]]
            cnpj = next((c for c in map(extrair_cnpj, linhas["Descrição"]) if c), "")
            regra = nova_regra(r["chave"], r["Fornecedor"], r["Categoria"], sub, "usuario", cnpj)
            (comp if eh_empresa(linhas["Descrição"], linhas["Conta"]) else pess).append(regra)
        try:
            salvar_regras(pd.concat(comp) if comp else regras_vazias(),
                          pd.concat(pess) if pess else regras_vazias(),
                          ", ".join(mudou["Fornecedor"].head(5)))
            st.rerun()
        except Exception as e:
            st.error(f"Não foi possível salvar as regras: {e}")
    st.caption("🔒 Empresas (cartão, boleto, débito ou CNPJ) vão para as regras compartilhadas. "
               "Pix para pessoas fica só nas suas regras pessoais, para não expor nomes.")

    # ---- Consulta de CNPJ
    st.subheader("Consultar CNPJ na Receita")
    conhecidas = set(regras_todas["chave"])
    pend = saidas[saidas["Categoria"].isin(["OUTRO", "TRANSFERÊNCIA"])
                  & ~saidas["chave"].isin(conhecidas)].copy()
    pend["CNPJ"] = pend["Descrição"].map(extrair_cnpj)
    pend = (pend.dropna(subset=["CNPJ"]).groupby(["chave", "CNPJ"])
            .agg(Fornecedor=("Fornecedor", "first"), Total=("Valor", lambda v: -v.sum()))
            .sort_values("Total", ascending=False).reset_index())
    if pend.empty:
        st.caption("Nenhum fornecedor pendente com CNPJ no extrato.")
    else:
        dica(f"{len(pend)} fornecedor(es) sem categoria têm CNPJ na descrição (Pix para empresas). "
             "A consulta usa os dados públicos da Receita Federal (BrasilAPI, gratuita).")
        if st.button(f"🔎 Consultar {len(pend)} CNPJ(s)"):
            linhas = []
            barra = st.progress(0.0, text="Consultando a Receita...")
            for n, r in enumerate(pend.itertuples(), start=1):
                info = consultar_cnpj_cache(r.CNPJ)
                sugestao = categoria_do_cnae(info["cnae"]) if info else None
                linhas.append({
                    "Aplicar": sugestao is not None, "chave": r.chave, "Fornecedor": r.Fornecedor,
                    "CNPJ": r.CNPJ, "Nome na Receita": info["nome"] if info else "(não encontrado)",
                    "Atividade principal (CNAE)": f"{info['cnae']} · {info['atividade']}" if info else "",
                    "Categoria": sugestao[0] if sugestao else "OUTRO",
                    "Subcategoria": (sugestao[1] or SEM_SUB) if sugestao else SEM_SUB,
                    "cnae": info["cnae"] if info else "", "Total": formatar_reais(r.Total),
                })
                barra.progress(n / len(pend), text=f"Consultando a Receita... {n}/{len(pend)}")
            barra.empty()
            st.session_state["sugestoes_cnpj"] = pd.DataFrame(linhas)

        sug = st.session_state.get("sugestoes_cnpj")
        if sug is not None and not sug.empty:
            dica("Confira as sugestões; ajuste a categoria se precisar e desmarque o que não quiser")
            sug_edit = st.data_editor(
                sug, hide_index=True, width="stretch", key="editor_cnpj",
                column_order=["Aplicar", "Fornecedor", "Nome na Receita",
                              "Atividade principal (CNAE)", "Categoria", "Subcategoria", "Total"],
                disabled=["Fornecedor", "Nome na Receita", "Atividade principal (CNAE)", "Total"],
                column_config={
                    "Categoria": st.column_config.SelectboxColumn(options=categorias_editaveis()),
                    "Subcategoria": st.column_config.SelectboxColumn(options=todas_subs),
                })
            marcadas = sug_edit[sug_edit["Aplicar"]]
            if st.button(f"✅ Aplicar {len(marcadas)} sugestão(ões)", disabled=marcadas.empty):
                novas = []
                for _, r in marcadas.iterrows():
                    validas = subcategorias_de(r["Categoria"])
                    sub = r["Subcategoria"] if r["Subcategoria"] in validas else validas[-1]
                    nome = r["Nome na Receita"] if not r["Nome na Receita"].startswith("(") \
                        else r["Fornecedor"]
                    novas.append(nova_regra(r["chave"], nome, r["Categoria"], sub, "cnpj",
                                            r["CNPJ"], r["cnae"]))
                try:
                    salvar_regras(pd.concat(novas), regras_vazias(),
                                  "CNPJ " + ", ".join(marcadas["Fornecedor"].head(5)))
                    st.session_state.pop("sugestoes_cnpj", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Não foi possível salvar as regras: {e}")

    # ---- Regras salvas
    pessoais = st.session_state["regras_pessoais"]
    with st.expander(f"📚 Regras salvas ({len(regras_comp)} compartilhadas, "
                     f"{len(pessoais) + len(regras_privadas)} pessoais)"):
        if not repo_regras.no_github:
            st.info("As regras compartilhadas estão sendo guardadas só neste servidor e se perdem "
                    "quando o app reinicia. Para guardar de vez no GitHub, veja "
                    "\"Regras compartilhadas\" no README.", icon="ℹ️")
        colunas_ver = ["fornecedor", "categoria", "subcategoria", "origem", "cnpj",
                       "atualizado_em"]
        st.dataframe(regras_comp[colunas_ver], hide_index=True, width="stretch")
        st.markdown("**Suas regras pessoais** (Pix para pessoas — ficam só com você)")
        if not regras_privadas.empty:
            st.caption(f"🔒 Mais {len(regras_privadas)} regra(s) pessoal(is) guardada(s) nos "
                       "Secrets do app (não aparecem aqui para ninguém).")
        st.dataframe(pessoais[colunas_ver], hide_index=True, width="stretch")
        if not pessoais.empty:
            st.markdown("**Guardar de vez:** copie o texto abaixo e cole em Settings → Secrets "
                        "do app no Streamlit Cloud" + (" (acrescente as linhas dentro do "
                        "REGRAS_PESSOAIS que já existe)" if not regras_privadas.empty else ""))
            linhas_csv = pessoais.to_csv(index=False).strip()
            if regras_privadas.empty:
                st.code(f'REGRAS_PESSOAIS = """\n{linhas_csv}\n"""', language="toml")
            else:
                st.code("\n".join(linhas_csv.splitlines()[1:]), language=None)
        c1, c2 = st.columns(2)
        c1.download_button("📥 Baixar minhas regras pessoais",
                           pessoais.to_csv(index=False).encode("utf-8-sig"),
                           "minhas_regras.csv", "text/csv", disabled=pessoais.empty)
        enviado = c2.file_uploader("Recarregar minhas regras pessoais", type=["csv"],
                                   key="upload_regras")
        if enviado is not None and st.session_state.get("regras_carregadas") != enviado.file_id:
            try:
                lidas = pd.read_csv(enviado, dtype=str).fillna("")
                st.session_state["regras_pessoais"] = juntar(pessoais, lidas[pessoais.columns])
                st.session_state["regras_carregadas"] = enviado.file_id
                st.session_state["versao_regras"] += 1
                st.rerun()
            except Exception as e:
                st.error(f"Arquivo de regras inválido: {e}")
