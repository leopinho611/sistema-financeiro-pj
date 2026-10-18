import io
from datetime import datetime
from html import escape
from urllib.parse import quote

import hmac
import importlib
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# Depois de uma atualização, o Streamlit Cloud recarrega este arquivo mas pode
# manter na memória a versão antiga de financeiro.py e regras.py, e o app quebra
# com ImportError até alguém reiniciar. Recarregá-los aqui evita isso.
for _modulo in ("financeiro", "regras", "plus"):   # nessa ordem: os outros importam financeiro
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
    expandir_zip,
    extrair_cnpj,
    formatar_reais,
    montar_transacoes,
    subcategorias_de,
    coluna_pct,
    resumo_categorias,
    resumo_fornecedores,
    resumo_mensal,
    resumo_subcategorias,
)
from regras import RepositorioRegras, consultar_cnpj, juntar, nova_regra, regras_vazias
import plus

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Contas em Dia",
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
  .cabecalho .sistema {{ text-align: right; font-size: .95rem; margin: 0; opacity: .8;
                         letter-spacing: .04em; }}
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
  .tabcat.entradas .pct .trilho i {{ background: {COR_ENTRADAS}; }}
  .rodape {{ margin-top: 2.5rem; padding: .9rem 0 .4rem 0; text-align: center;
             border-top: 1px solid color-mix(in srgb, {DOURADO} 45%, transparent);
             font-size: .82rem; opacity: .75; line-height: 1.5; }}
  .rodape b {{ color: {DOURADO}; font-weight: 600; }}
  .tabcat .pct b {{ font-weight: inherit; min-width: 3.2em; text-align: right;
                    font-variant-numeric: tabular-nums; }}
  /* Área Plus */
  .cartoes {{ display: grid; gap: .8rem; margin: .4rem 0 1rem 0;
              grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr)); }}
  .cartao {{ border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
             border-left: 5px solid var(--cor); border-radius: 8px; padding: .7rem .9rem; }}
  .cartao .titulo {{ font-size: .85rem; opacity: .75; }}
  .cartao .valor {{ font-size: 1.5rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .cartao .status {{ font-size: .85rem; font-weight: 600; }}
  .cartao .status::before {{ content: ""; display: inline-block; width: .65em; height: .65em;
                             border-radius: 50%; background: var(--cor); margin-right: .35em; }}
  .cartao .explica {{ font-size: .8rem; opacity: .75; margin-top: .3rem; line-height: 1.35; }}
  .vitrine {{ border: 1px solid color-mix(in srgb, {DOURADO} 55%, transparent);
              border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: 1rem;
              background: color-mix(in srgb, {DOURADO} 7%, transparent); }}
  .vitrine h3 {{ margin-top: 0; }}
  /* Área grande de envio na tela inicial */
  .chamada {{ text-align: center; font-weight: 700; margin: .8rem 0 1rem 0; }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzone"] {{
      min-height: 230px; display: flex; flex-direction: column; justify-content: center;
      align-items: center; gap: .7rem; padding: 1.5rem;
      border: 2px dashed color-mix(in srgb, {DOURADO} 70%, transparent); border-radius: 14px;
      background: color-mix(in srgb, {DOURADO} 6%, transparent); cursor: pointer; }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzone"]:hover {{
      background: color-mix(in srgb, {DOURADO} 12%, transparent); }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzone"]::before {{
      content: "📄\A Arraste seus extratos para cá\A ou"; white-space: pre; text-align: center;
      font-size: 1.15rem; font-weight: 600; line-height: 1.7; }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzone"] > span {{ order: 1; }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzoneInstructions"] {{ order: 2; }}
  .st-key-upload_grande [data-testid="stBaseButton-secondary"] {{
      background: {COR_ENTRADAS}; color: #ffffff; border: none; border-radius: 999px;
      padding: .7rem 1.6rem; font-size: 1.05rem; font-weight: 600; }}
  .st-key-upload_grande [data-testid="stBaseButton-secondary"]:hover {{
      background: #2f5aa8; color: #ffffff; }}
  .st-key-upload_grande [data-testid="stBaseButton-secondary"] p {{ font-size: 1.05rem; }}
  /* Textos do envio em português */
  [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] p {{
      font-size: 0; }}
  [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] p::after {{
      content: "Escolher arquivos"; font-size: .9rem; }}
  .st-key-upload_grande [data-testid="stBaseButton-secondary"] p::after {{ font-size: 1.05rem; }}
  [data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: 0; }}
  [data-testid="stFileUploaderDropzoneInstructions"] span::after {{
      content: "Até 200 MB por arquivo · CSV, Excel, OFX, PDF ou ZIP"; font-size: .8rem; }}
  /* Botões fixos no canto inferior direito */
  .flutuantes {{ position: fixed; right: 1.2rem; bottom: 1.2rem; z-index: 999990;
                 display: flex; flex-direction: column; align-items: flex-end; gap: .55rem; }}
  .flutuantes a {{ display: inline-flex; align-items: center; gap: .5rem; text-decoration: none;
                   font-weight: 600; font-size: .9rem; border-radius: 999px;
                   padding: .6rem 1.05rem; box-shadow: 0 3px 12px rgba(0, 0, 0, .25);
                   transition: transform .15s; }}
  .flutuantes a:hover {{ transform: translateY(-2px); text-decoration: none; }}
  .flutuantes .plus {{ background: {DOURADO}; color: #0f1a2e !important; }}
  .flutuantes .whats {{ background: #25d366; color: #0b2e17 !important; }}
  .flutuantes svg {{ width: 1.35rem; height: 1.35rem; flex: none; }}
  .flutuantes .curto {{ display: none; }}
  /* Espaço no fim da página para os botões não cobrirem o rodapé */
  [data-testid="stMainBlockContainer"] {{ padding-bottom: 8rem; }}
  @media (max-width: 640px) {{
    .flutuantes {{ right: .8rem; bottom: .8rem; }}
    .flutuantes a {{ font-size: .8rem; padding: .5rem .85rem; }}
    .flutuantes .longo {{ display: none; }}
    .flutuantes .curto {{ display: inline; }}
    .tabcat .linha {{ grid-template-columns: minmax(0, 1.6fr) 1.2fr 1fr; }}
    .tabcat .qtd {{ display: none; }}
  }}
</style>
<div class="cabecalho">
  <h1>Contas em Dia</h1>
  <p class="sistema">Sistema de Controle Financeiro</p>
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


def grafico_categorias(cats, tipo="Saída"):
    pct = coluna_pct(tipo)
    dados = cats.assign(Valor=cats["Total"].map(formatar_reais),
                        Pct=cats[pct].map(lambda v: f"{v:.1f}%".replace(".", ",")))
    return (
        alt.Chart(dados)
        .mark_bar(color=COR_SAIDAS if tipo == "Saída" else COR_ENTRADAS, cornerRadiusEnd=4)
        .encode(
            x=alt.X("Total:Q", axis=EIXO_REAIS),
            y=alt.Y("Categoria:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            tooltip=[alt.Tooltip("Categoria:N", title="Categoria" if tipo == "Saída" else "Tipo"),
                     alt.Tooltip("Valor:N", title="Total"),
                     alt.Tooltip("Pct:N", title=pct),
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


def _linhas_fornecedores(df, categoria, subcategoria=None, tipo="Saída"):
    partes = []
    for _, f in resumo_fornecedores(df, categoria, subcategoria=subcategoria,
                                    tipo=tipo).iterrows():
        classe = "forn outros" if f["Fornecedor"].startswith(("Outros fornecedores",
                                                              "Outras fontes")) else "forn"
        partes.append(_linha_html(classe, f["Fornecedor"], f["Total"], f["Transações"],
                                  f["% da categoria"]))
    return partes


def tabela_categorias_html(cats, df, tipo="Saída", rotulo="Categoria"):
    """Categoria → subcategoria → 10 maiores fornecedores, abrindo logo abaixo da linha.

    Categorias sem subcategorias abrem direto nos fornecedores. O % de cada linha
    aberta é sobre o grupo de cima (subcategoria sobre a categoria, fornecedor
    sobre a subcategoria).
    """
    pct = coluna_pct(tipo)
    classe = "tabcat" if tipo == "Saída" else "tabcat entradas"
    partes = [f'<div class="{classe}">',
              f'<div class="linha cab"><span>{rotulo}</span><span class="num">Total</span>'
              f'<span class="num qtd">Transações</span><span>{pct}</span></div>']
    for _, c in cats.iterrows():
        partes.append("<details>")
        partes.append(_linha_html("", c["Categoria"], c["Total"], c["Transações"],
                                  c[pct], tag="summary"))
        partes.append('<div class="detalhe">')
        subs = resumo_subcategorias(df, c["Categoria"], tipo=tipo)
        if subs.empty:
            partes += _linhas_fornecedores(df, c["Categoria"], tipo=tipo)
        else:
            for _, sc in subs.iterrows():
                partes.append('<details class="sub">')
                partes.append(_linha_html("", sc["Subcategoria"], sc["Total"], sc["Transações"],
                                          sc["% da categoria"], tag="summary"))
                partes.append('<div class="detalhe">')
                partes += _linhas_fornecedores(df, c["Categoria"], sc["Subcategoria"], tipo=tipo)
                partes.append("</div></details>")
        partes.append("</div></details>")
    partes.append("</div>")
    return "".join(partes)


def grafico_entradas_mes(mensal):
    dados = mensal.assign(Rótulo=mensal["Mês"].map(rotulo_mes),
                          Valor=mensal["Entradas"].map(formatar_reais))
    ordem = dados["Rótulo"].tolist()
    return (
        alt.Chart(dados)
        .mark_bar(color=COR_ENTRADAS, cornerRadiusEnd=4)
        .encode(
            x=alt.X("Rótulo:N", sort=ordem, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Entradas:Q", axis=EIXO_REAIS),
            tooltip=[alt.Tooltip("Rótulo:N", title="Mês"), alt.Tooltip("Valor:N", title="Entradas")],
        )
        .properties(height=280)
    )


# Uma cor por despesa nas linhas: paleta categórica validada (contraste e daltonismo)
# nos dois fundos; a ordem é fixa e vai do maior para o menor. O total é cinza tracejado.
CORES_SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9",
                "#e66767"]
COR_TOTAL = "#8c8c8c"
ALTURA_LINHAS = 380
LARGURA_NOMES = 190    # espaço à direita para o nome no fim de cada linha
DISTANCIA_NOMES = 15   # px mínimos entre dois nomes, para não se sobreporem


def cor_do_texto():
    """Cor do texto do tema aberto (os nomes no gráfico seguem o texto, não a série)."""
    try:
        escuro = st.context.theme.type == "dark"
    except Exception:
        escuro = False
    return "#f2ece0" if escuro else "#14213d"


def _topo_do_eixo(maximo):
    """Topo "redondo" do eixo y (1, 2, 2,5 ou 5 × 10ⁿ), para saber onde cai cada valor."""
    if maximo <= 0:
        return 1.0
    passo = 10 ** np.floor(np.log10(maximo / 5))
    for m in (1, 2, 2.5, 5, 10):
        if maximo / (passo * m) <= 5:
            return float(np.ceil(maximo * 1.04 / (passo * m)) * passo * m)
    return float(maximo)


def _posicoes_dos_nomes(valores, topo, altura=ALTURA_LINHAS):
    """Afasta os nomes que terminam no mesmo mês e ficariam um em cima do outro.

    Recebe os valores finais e devolve o valor (na escala do eixo) onde cada nome vai.
    """
    px = {k: altura * (1 - v / topo) for k, v in valores.items()}
    ordem = sorted(px, key=px.get)
    for a, b in zip(ordem, ordem[1:]):
        px[b] = max(px[b], px[a] + DISTANCIA_NOMES)
    excesso = px[ordem[-1]] - (altura + 6) if ordem else 0
    if excesso > 0:   # passou do eixo: sobe todos e volta a afastar de baixo para cima
        px[ordem[-1]] -= excesso
        for a, b in zip(reversed(ordem), list(reversed(ordem))[1:]):
            px[b] = min(px[b], px[a] - DISTANCIA_NOMES)
    return {k: topo * (1 - y / altura) for k, y in px.items()}


def grafico_linhas(longo, nome_total="Total", max_series=7, rotulo="Despesa",
                   altura=ALTURA_LINHAS, largura_nomes=LARGURA_NOMES):
    """Uma linha por série (Mês, Fornecedor, Valor) e uma linha tracejada com o total.

    As max_series maiores ganham linha própria; as demais se juntam em "Outros". O nome
    de cada série fica no fim da linha. Passando o mouse, uma linha vertical mostra os
    valores de todas as séries do mês.
    """
    ordem = longo.groupby("Fornecedor")["Valor"].sum().sort_values(ascending=False).index
    if len(ordem) > max_series:
        resto = set(ordem[max_series:])
        nome_outros = f"Outros ({len(resto)})"
        longo = longo.assign(Fornecedor=longo["Fornecedor"].where(
            ~longo["Fornecedor"].isin(resto), nome_outros))
        longo = longo.groupby(["Mês", "Fornecedor"], as_index=False)["Valor"].sum()
        ordem = list(ordem[:max_series]) + [nome_outros]
    series = list(ordem)
    meses = sorted(longo["Mês"].unique())
    total = longo.groupby("Mês", as_index=False)["Valor"].sum().assign(Fornecedor=nome_total)
    dados = pd.concat([longo, total], ignore_index=True)
    dados["Rótulo"] = dados["Mês"].map(rotulo_mes)
    dados["Texto"] = dados["Valor"].map(formatar_reais)
    rotulos = [rotulo_mes(m) for m in meses]
    nomes = [nome_total] + series
    topo = _topo_do_eixo(dados["Valor"].max())

    # Nome no fim de cada linha (no último mês em que a série aparece)
    fins = dados.sort_values("Mês").groupby("Fornecedor").tail(1)
    nomes_fim = []
    for rot, grupo in fins.groupby("Rótulo"):
        pos = _posicoes_dos_nomes(dict(zip(grupo["Fornecedor"], grupo["Valor"])), topo,
                                  altura)
        nomes_fim += [{"Rótulo": rot, "Fornecedor": f, "Valor": v} for f, v in pos.items()]
    nomes_fim = pd.DataFrame(nomes_fim)

    # Tabela larga para a dica da linha vertical: um campo por série (c0, c1...)
    largo = dados.pivot_table(index="Rótulo", columns="Fornecedor", values="Valor",
                              aggfunc="sum").reindex(columns=nomes)
    campos = {n: f"c{i}" for i, n in enumerate(nomes)}
    largo = largo.map(lambda v: "—" if pd.isna(v) else formatar_reais(v)) \
        .rename(columns=campos).reset_index()

    x = alt.X("Rótulo:N", sort=rotulos, title=None,
              axis=alt.Axis(labelAngle=0, labelOverlap=True))
    y = alt.Y("Valor:Q", axis=EIXO_REAIS, scale=alt.Scale(domain=[0, topo], nice=False))
    cor = alt.Color("Fornecedor:N", sort=nomes, legend=None,
                    scale=alt.Scale(domain=nomes, range=[COR_TOTAL] + CORES_SERIES[:len(series)]))
    tracejado = alt.condition(alt.datum.Fornecedor == nome_total, alt.value([6, 4]),
                              alt.value([1, 0]))
    espessura = alt.condition(alt.datum.Fornecedor == nome_total, alt.value(3), alt.value(2))
    base = alt.Chart(dados).encode(x=x, y=y, color=cor)
    linhas = base.mark_line().encode(strokeDash=tracejado, strokeWidth=espessura)
    pontos = base.mark_point(filled=True, size=64, opacity=1).encode(
        tooltip=[alt.Tooltip("Fornecedor:N", title=rotulo),
                 alt.Tooltip("Rótulo:N", title="Mês"), alt.Tooltip("Texto:N", title="Valor")])
    estilo = dict(align="left", baseline="middle", dx=9, fontSize=12,
                  limit=largura_nomes - 14, color=cor_do_texto())
    eh_total = nomes_fim["Fornecedor"] == nome_total
    textos = (alt.Chart(nomes_fim[~eh_total]).mark_text(**estilo)
              .encode(x=x, y=y, text="Fornecedor:N")
              + alt.Chart(nomes_fim[eh_total]).mark_text(fontWeight="bold", **estilo)
              .encode(x=x, y=y, text="Fornecedor:N"))
    passa = alt.selection_point(nearest=True, on="pointerover", fields=["Rótulo"], empty=False,
                                clear="pointerout")
    regua = alt.Chart(largo).mark_rule(color=COR_TOTAL, strokeWidth=1).encode(
        x=x,
        opacity=alt.condition(passa, alt.value(0.7), alt.value(0)),
        tooltip=[alt.Tooltip("Rótulo:N", title="Mês")]
        + [alt.Tooltip(f"{campos[n]}:N", title=n) for n in nomes],
    ).add_params(passa)
    # "fit": o gráfico ocupa a largura toda, já descontando o espaço dos nomes à direita
    return (linhas + pontos + textos + regua).properties(
        width="container", height=altura, padding={"left": 5, "top": 10, "bottom": 5, "right": 8},
        autosize=alt.AutoSizeParams(type="fit", contains="padding"))


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
st.session_state.setdefault("regras_sessao", regras_vazias())   # só até fechar o app


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
TIPOS_EXTRATO = ["csv", "xlsx", "xls", "excel", "pdf", "ofx", "zip"]
# Arquivos enviados pela área grande da tela inicial: guardados na sessão (só na memória)
# porque aquela área some depois do envio
st.session_state.setdefault("arquivos_principal", [])

with st.sidebar:
    st.header("📁 Importar Dados")
    arquivos_lateral = st.file_uploader(
        "Escolha seus extratos",
        type=TIPOS_EXTRATO,
        accept_multiple_files=True,
        help="Extratos em CSV, Excel ou OFX de qualquer banco, de vários meses e contas. "
             "Em PDF: extrato da conta Nubank e fatura do cartão BB. Pode mandar o mesmo "
             "mês em mais de um formato: as repetições são descartadas. Pode mandar "
             "uma pasta compactada (.zip)."
    )
    if st.session_state["arquivos_principal"]:
        st.caption(f"📎 {len(st.session_state['arquivos_principal'])} arquivo(s) enviado(s) "
                   "pela tela principal")
        if st.button("Remover esses arquivos"):
            st.session_state["arquivos_principal"] = []
            st.rerun()
    arquivos = list(arquivos_lateral or []) + st.session_state["arquivos_principal"]
    st.caption("🌓 Tema claro ou escuro: menu ⋮ no canto superior direito → Settings")
    nome_titular = st.text_input(
        "Seu nome (opcional)",
        placeholder="Ex: Maria Silva",
        help="Pix e TED para você mesmo em outro banco viram transferência entre "
             "contas, e não gasto. Use nome e sobrenome como aparecem no extrato."
    )

# ============================================================================
# ÁREA PLUS (código de acesso)
# ============================================================================
def _lista_segredo(nome):
    """Segredo que pode ser lista (TOML) ou texto separado por vírgulas."""
    valor = ler_segredo(nome)
    if not valor:
        return []
    if isinstance(valor, str):
        valor = valor.split(",")
    return [str(v).strip() for v in valor if str(v).strip()]


def codigo_valido(codigo):
    codigo = (codigo or "").strip()
    return bool(codigo) and any(hmac.compare_digest(codigo.encode(), c.encode())
                                for c in _lista_segredo("PLUS_CODIGOS"))


LINK_ASSINATURA = ler_segredo("PLUS_LINK")
LINK_CONSULTORIA = ler_segredo("CONTATO_CONSULTORIA")
st.session_state.setdefault("plus", False)

with st.sidebar:
    st.divider()
    if st.session_state["plus"]:
        st.markdown("⭐ **Plus ativo**")
        if st.button("Sair do Plus"):
            st.session_state["plus"] = False
            st.rerun()
    else:
        with st.expander("⭐ Tenho um código Plus"):
            with st.form("form_plus", clear_on_submit=True, border=False):
                codigo = st.text_input("Código de acesso", type="password")
                if st.form_submit_button("Entrar"):
                    if codigo_valido(codigo):
                        st.session_state["plus"] = True
                        st.rerun()
                    else:
                        st.error("Código inválido.")
            if LINK_ASSINATURA:
                st.link_button("Quero o Plus", LINK_ASSINATURA)
PLUS = st.session_state["plus"]

# ============================================================================
# PROCESSAMENTO
# ============================================================================
def rodape():
    st.markdown(
        '<div class="rodape">🔒 <b>Privacidade</b> · Seus extratos não são armazenados: '
        'ficam só na memória enquanto o app está aberto.<br>Ao fechar o app, todas as '
        'informações são apagadas — é isso que garante a sua privacidade.</div>',
        unsafe_allow_html=True)


ICONE_WHATSAPP = (
    '<svg viewBox="0 0 32 32" aria-hidden="true"><path fill="none" stroke="currentColor" '
    'stroke-width="2.4" stroke-linejoin="round" d="M16 3.5C9.1 3.5 3.5 9 3.5 15.8c0 2.4.7 '
    '4.6 1.9 6.5L4 28l5.9-1.5a12.6 12.6 0 0 0 6.1 1.6c6.9 0 12.5-5.5 12.5-12.3S22.9 3.5 16 '
    '3.5z"/><path fill="currentColor" d="M11.6 9.6c.4 0 .8 0 1.1.8l1.2 2.8c.1.3.1.6-.1.9l-.8 '
    '1c-.2.2-.2.5 0 .8.9 1.6 2.3 3 4 3.9.3.2.6.1.8-.1l1-1.2c.2-.3.5-.3.8-.2l2.8 1.3c.3.2.5.4'
    '.5.7 0 1.6-1.3 3-3 3-4.9-.4-9.4-4.9-9.8-9.8 0-1.7 1.4-2.9 1.5-2.9z"/></svg>')


def _whatsapp_com_texto(link, texto):
    """Link do WhatsApp (wa.me) com a mensagem já escrita."""
    if not link or "wa.me" not in link:
        return link
    return f"{link}{'&' if '?' in link else '?'}text={quote(texto)}"


def botoes_flutuantes():
    """Assinar o Plus e falar com um especialista: sempre à vista, no canto da tela."""
    botoes = []
    assinar = LINK_ASSINATURA or _whatsapp_com_texto(
        LINK_CONSULTORIA, "Olá! Quero assinar a área Plus do Contas em Dia.")
    if assinar and not PLUS:
        botoes.append(f'<a class="plus" href="{escape(assinar)}" target="_blank" '
                      'rel="noopener">⭐ Assinar área Plus</a>')
    if LINK_CONSULTORIA:
        falar = _whatsapp_com_texto(LINK_CONSULTORIA, "Olá! Quero falar com um especialista "
                                                      "financeiro/contábil.")
        botoes.append(f'<a class="whats" href="{escape(falar)}" target="_blank" rel="noopener">'
                      f'{ICONE_WHATSAPP}<span class="longo">Falar com um especialista financeiro/contábil'
                      '</span><span class="curto">Falar com especialista</span></a>')
    if botoes:
        st.markdown(f'<div class="flutuantes">{"".join(botoes)}</div>', unsafe_allow_html=True)


# O conteúdo vai num container e o rodapé é desenhado logo depois: assim ele aparece
# embaixo de qualquer aba, e também quando a tela para antes (st.stop)
corpo = st.container()
rodape()
botoes_flutuantes()

with corpo:
    if not arquivos:
        st.markdown('<h2 class="chamada">Organize suas contas em segundos</h2>',
                    unsafe_allow_html=True)
        with st.container(key="upload_grande"):
            enviados = st.file_uploader("Envie seus extratos", type=TIPOS_EXTRATO,
                                        accept_multiple_files=True, key="uploader_principal",
                                        label_visibility="collapsed")
        if enviados:
            st.session_state["arquivos_principal"] = list(enviados)
            st.rerun()
        st.markdown("""
        ## 🚀 Como usar
        1. No app ou no site do banco, baixe o **extrato** da conta (CSV, Excel ou OFX) ou
           a **fatura do cartão**. Pode enviar vários meses e várias contas de uma vez.
        2. Arraste os arquivos para a área acima, ou clique em **Escolher arquivos**.
           Também dá para usar o menu lateral (📁 Importar Dados).
        3. Em PDF: extrato da conta Nubank e fatura do cartão BB. Se mandar o mesmo mês
           em mais de um formato, as repetições são descartadas
        4. Pronto: veja o resumo, o mês a mês e as transações já separadas por categoria

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
    class ArquivoEmMemoria:
        """Arquivo tirado de um .zip, com a mesma interface do arquivo enviado."""

        def __init__(self, name, dados):
            self.name, self._dados = name, dados

        def getvalue(self):
            return self._dados


    expandidos = []
    for arquivo in arquivos:
        if arquivo.name.lower().endswith(".zip"):
            try:
                internos = expandir_zip(arquivo.getvalue())
                expandidos += [ArquivoEmMemoria(f"{n}", d) for n, d in internos]
                leitura.append({"Arquivo": arquivo.name, "Conta": "—",
                                "Situação": f"📦 {len(internos)} arquivo(s) dentro"})
            except ValueError as e:
                leitura.append({"Arquivo": arquivo.name, "Conta": "—", "Situação": f"⚠️ ignorado: {e}"})
        else:
            expandidos.append(arquivo)
    arquivos = sorted(expandidos,
                      key=lambda a: ORDEM_FORMATO.get(a.name.lower().rsplit(".", 1)[-1], 3))
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
    regras_todas = juntar(juntar(juntar(regras_comp, regras_privadas),
                                 st.session_state["regras_sessao"]),
                          st.session_state["regras_pessoais"])
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

    meses = max(1, df["Mês"].nunique())
    nomes_abas = ["📊 Resumo", "💰 Entradas", "💸 Saídas", "📅 Mês a Mês", "📋 Transações",
                  "📥 Download"]
    nomes_abas += (["⭐ Imposto de Renda", "⭐ Fixos e parcelas", "⭐ Saúde financeira",
                    "⭐ Classificar"] if PLUS else ["🔎 Consultar CNPJ", "⭐ Plus"])
    abas = st.tabs(nomes_abas)
    tab_resumo, tab_entradas, tab_saidas, tab_mes, tab_transacoes, tab_download = abas[:6]

    # Entradas agrupadas por tipo (recebido de empresas, de pessoas, salário...)
    df_entradas = df[df["Tipo"] == "Entrada"].assign(
        Categoria=lambda d: d["Subcategoria"].replace("", "Outras entradas"), Subcategoria="")
    tipos_entrada = resumo_categorias(df_entradas, tipo="Entrada")
    cats = resumo_categorias(df)

    def ranking_html(tabela, tipo, n=5):
        """Os n maiores itens com barra de %, para o Resumo."""
        pct = coluna_pct(tipo)
        classe = "tabcat" if tipo == "Saída" else "tabcat entradas"
        linhas = [f'<div class="{classe}">']
        linhas += [_linha_html("", r["Categoria"], r["Total"], r["Transações"], r[pct])
                   for _, r in tabela.head(n).iterrows()]
        resto = tabela.iloc[n:]
        if not resto.empty:
            linhas.append(_linha_html("forn outros", f"Demais ({len(resto)})", resto["Total"].sum(),
                                      resto["Transações"].sum(), resto[pct].sum()))
        return "".join(linhas + ["</div>"])

    # ----------------------------------------------------------------------------
    with tab_resumo:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Entradas", formatar_reais(entradas))
        m2.metric("Saídas", formatar_reais(saidas))
        m3.metric("Saldo do período", formatar_reais(entradas - saidas))
        m4.metric("Aplicado (líquido)", formatar_reais(aplicado),
                  help="Aplicações menos resgates no período (Rende Fácil, caixinhas, fundos...). "
                       "Não entra em entradas nem saídas.")

        # Ranking e, logo abaixo, a evolução mês a mês (as 5 maiores, o resto em "Outros",
        # e o total), cada um embaixo do seu par
        varios_meses = df["Mês"].nunique() > 1
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("De onde vem")
            if tipos_entrada.empty:
                st.info("Não há entradas no período.")
            else:
                st.markdown(ranking_html(tipos_entrada, "Entrada"), unsafe_allow_html=True)
                if varios_meses:
                    ent_mes = (df_entradas.groupby(["Mês", "Categoria"], as_index=False)["Valor"]
                               .sum().rename(columns={"Categoria": "Fornecedor"}))
                    st.altair_chart(grafico_linhas(ent_mes, "Total", max_series=5, rotulo="Tipo",
                                                   altura=260, largura_nomes=135),
                                    width="stretch")
        with c2:
            st.subheader("Para onde vai")
            if cats.empty:
                st.info("Não há saídas no período.")
            else:
                st.markdown(ranking_html(cats, "Saída"), unsafe_allow_html=True)
                if varios_meses:
                    sai_mes = (df[df["Tipo"] == "Saída"].assign(Valor=lambda d: -d["Valor"])
                               .groupby(["Mês", "Categoria"], as_index=False)["Valor"].sum()
                               .rename(columns={"Categoria": "Fornecedor"}))
                    st.altair_chart(grafico_linhas(sai_mes, "Total", max_series=5,
                                                   rotulo="Categoria", altura=260,
                                                   largura_nomes=135), width="stretch")
        if varios_meses:
            dica("Passe o mouse sobre os gráficos para ver os valores de cada mês")
        dica("Os detalhes, com as fontes e os fornecedores, estão nas abas 💰 Entradas e 💸 Saídas")

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
    with tab_entradas:
        if tipos_entrada.empty:
            st.info("Não há entradas no período.")
        else:
            fontes = df_entradas.assign(_k=df_entradas["Fornecedor"].map(chave_fornecedor))
            por_fonte = fontes.groupby("_k")["Valor"].sum().sort_values(ascending=False)
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Total de entradas", formatar_reais(entradas))
            e2.metric("Média por mês", formatar_reais(entradas / meses))
            e3.metric("Fontes diferentes", f"{len(por_fonte)}")
            e4.metric("Maior fonte", f"{por_fonte.iloc[0] / entradas * 100:.0f}%".replace(".", ","),
                      help="Quanto das entradas veio de quem mais pagou. Quanto maior, mais "
                           "você depende de uma fonte só.")

            st.subheader("Entradas por mês")
            dica("Passe o mouse sobre as barras para ver os valores")
            st.altair_chart(grafico_entradas_mes(resumo_mensal(df)), width="stretch")

            st.subheader("Entradas por tipo")
            st.altair_chart(grafico_categorias(tipos_entrada, "Entrada"), width="stretch")
            dica("Clique num tipo para ver quem mais pagou · nas linhas abertas, o % é sobre "
                 "o tipo")
            st.markdown(tabela_categorias_html(tipos_entrada, df_entradas, tipo="Entrada",
                                               rotulo="Tipo de entrada"),
                        unsafe_allow_html=True)

    # ----------------------------------------------------------------------------
    with tab_saidas:
        if cats.empty:
            st.info("Não há saídas no período.")
        else:
            s1, s2, s3 = st.columns(3)
            s1.metric("Total de saídas", formatar_reais(saidas))
            s2.metric("Média por mês", formatar_reais(saidas / meses))
            s3.metric(f"Maior categoria ({_pct(cats.iloc[0]['% das saídas'])} das saídas)",
                      cats.iloc[0]["Categoria"].capitalize())

            st.subheader("Saídas por categoria")
            dica("Passe o mouse sobre as barras para ver os valores")
            st.altair_chart(grafico_categorias(cats), width="stretch")
            dica("Clique numa categoria para abrir as subcategorias e os maiores fornecedores · "
                 "nas linhas abertas, o % é sobre o grupo de cima")
            st.markdown(tabela_categorias_html(cats, df), unsafe_allow_html=True)

            outros = cats.loc[cats["Categoria"] == "OUTRO", "% das saídas"]
            if not outros.empty and outros.iloc[0] > 20:
                st.caption(f"ℹ️ {outros.iloc[0]:.0f}% das saídas ficaram em OUTRO. "
                           + ("Classifique na aba ⭐ Classificar." if PLUS else
                              "Veja a aba 🔎 Consultar CNPJ."))

    # ----------------------------------------------------------------------------
    with tab_mes:
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
    with tab_transacoes:
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
    with tab_download:
        st.subheader("Exportar")
        exportar = df.copy()
        exportar["Data"] = exportar["Data"].dt.strftime("%d/%m/%Y")
        hoje = datetime.now().strftime("%Y%m%d")

        # CSV no padrão do Excel brasileiro: ponto e vírgula e vírgula decimal
        exportar = exportar.drop(columns=["DataCompra", "FornecedorOriginal"], errors="ignore")
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


    # ============================================================================
    # CLASSIFICAÇÃO E ÁREA PLUS
    # ============================================================================
    SEM_SUB = "—"  # categoria sem subcategorias
    todas_subs = [SEM_SUB] + sorted({x for c in categorias_editaveis()
                                     for x in subcategorias_de(c) if x})
    saidas_forn = todos[todos["Tipo"] == "Saída"].assign(
        chave=lambda d: d["FornecedorOriginal"].map(chave_fornecedor))
    # Recorrentes, parcelas e IR olham todo o histórico das contas escolhidas (o filtro
    # de período cortaria parcelas e meses); a saúde financeira segue o período
    df_contas = todos[todos["Conta"].isin(filtro_contas)]
    recorrentes = plus.gastos_recorrentes(df_contas)
    parcelas, cronograma = plus.parcelas_futuras(df_contas)
    compromissos = plus.compromissos_mensais(recorrentes)
    parcelas_proximo = float(cronograma["Valor"].iloc[0]) if not cronograma.empty else 0.0
    anos_ir = sorted(df_contas["Data"].dt.year.unique(), reverse=True)

    def subcategoria_valida(categoria, sub):
        validas = subcategorias_de(categoria)
        return sub if sub in validas else validas[-1]

    def secao_cnpj(lembrar):
        """Consulta pública do CNPJ. lembrar=True (Plus) grava as regras; senão, valem só
        até fechar o app."""
        if st.session_state.get("aviso_regras"):
            st.success(st.session_state.pop("aviso_regras"), icon="✅")
        conhecidas = set(regras_todas["chave"])
        pend = saidas_forn[saidas_forn["Categoria"].isin(["OUTRO", "TRANSFERÊNCIA"])
                           & ~saidas_forn["chave"].isin(conhecidas)].copy()
        pend["CNPJ"] = pend["Descrição"].map(extrair_cnpj)
        pend = (pend.dropna(subset=["CNPJ"]).groupby(["chave", "CNPJ"])
                .agg(Fornecedor=("Fornecedor", "first"), Total=("Valor", lambda v: -v.sum()))
                .sort_values("Total", ascending=False).reset_index())
        if pend.empty:
            st.caption("Nenhum fornecedor pendente com CNPJ no extrato.")
            return
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
                    "cnae": info["cnae"] if info else "", "mei": bool(info and info["mei"]),
                    "Total": formatar_reais(r.Total),
                })
                barra.progress(n / len(pend), text=f"Consultando a Receita... {n}/{len(pend)}")
            barra.empty()
            st.session_state["sugestoes_cnpj"] = pd.DataFrame(linhas)

        sug = st.session_state.get("sugestoes_cnpj")
        if sug is None or sug.empty:
            return
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
        if not st.button(f"✅ Aplicar {len(marcadas)} sugestão(ões)", disabled=marcadas.empty):
            return
        novas, pessoais_mei = [], []
        for _, r in marcadas.iterrows():
            sub = subcategoria_valida(r["Categoria"], r["Subcategoria"])
            nome = r["Nome na Receita"] if not r["Nome na Receita"].startswith("(") \
                else r["Fornecedor"]
            regra = nova_regra(r["chave"], nome, r["Categoria"], sub, "cnpj", r["CNPJ"], r["cnae"])
            # MEI tem o nome da pessoa no CNPJ: não vai para o arquivo público
            (pessoais_mei if r.get("mei") else novas).append(regra)
        st.session_state.pop("sugestoes_cnpj", None)
        if lembrar:
            try:
                salvar_regras(pd.concat(novas) if novas else regras_vazias(),
                              pd.concat(pessoais_mei) if pessoais_mei else regras_vazias(),
                              "CNPJ " + ", ".join(marcadas["Fornecedor"].head(5)))
            except Exception as e:
                st.error(f"Não foi possível salvar as regras: {e}")
                return
        else:
            st.session_state["regras_sessao"] = juntar(st.session_state["regras_sessao"],
                                                       pd.concat(novas + pessoais_mei))
            st.session_state["versao_regras"] += 1
            st.session_state["aviso_regras"] = (f"{len(marcadas)} fornecedor(es) "
                                                "classificado(s) até você fechar o app")
        st.rerun()

    if not PLUS:
        tab_cnpj, tab_vitrine = abas[6:]

        with tab_cnpj:
            st.subheader("Consultar CNPJ na Receita")
            st.markdown("Pix feitos a empresas trazem o CNPJ na descrição. O app consulta a "
                        "**atividade principal** da empresa nos dados públicos da Receita "
                        "Federal e sugere a categoria — você confere e aplica.")
            secao_cnpj(lembrar=False)
            st.caption("🔒 Nada é guardado: as classificações valem até você fechar o app. "
                       "Para corrigir qualquer fornecedor e o app lembrar nas próximas vezes, "
                       "use a versão ⭐ Plus.")

        with tab_vitrine:
            st.markdown('<div class="vitrine"><h3>⭐ Contas em Dia Plus</h3>'
                        'Análises prontas a partir dos mesmos extratos — continua sem guardar '
                        'nada.</div>', unsafe_allow_html=True)
            st.markdown("**O que o Plus já encontrou nos seus extratos:**")
            v1, v2, v3 = st.columns(3)
            v1.metric("Contas que se repetem todo mês", formatar_reais(compromissos),
                      help="Assinaturas, mensalidades e contas mensais ainda ativas.")
            v2.metric(f"{len(parcelas)} compra(s) parcelada(s) a pagar",
                      formatar_reais(parcelas["Total restante"].sum()),
                      help="Parcelas do cartão que ainda vão vencer.")
            if anos_ir:
                dedu = plus.relatorio_ir(df_contas, anos_ir[0])["deducoes"]
                v3.metric(f"Possíveis deduções do IR ({anos_ir[0]})",
                          formatar_reais(dedu["Total"].sum()),
                          help="Saúde, educação, previdência privada e pensão.")
            st.markdown("""
            - **⭐ Imposto de Renda** — despesas que podem ser deduzidas (saúde, educação,
              PGBL, pensão) com o CNPJ de quem recebeu, e os rendimentos recebidos de empresas
              e de pessoas. Pronto para levar ao contador, em planilha.
            - **⭐ Fixos e parcelas** — o que se repete todo mês, a data prevista do
              próximo, e as parcelas do cartão que ainda faltam (quantas e quanto, mês a mês).
            - **⭐ Saúde financeira** — indicadores com semáforo: quanto sobra, meses no
              vermelho, dependência de uma fonte de renda, compromissos e reserva de emergência.
            - **⭐ Classificar** — corrija a categoria de qualquer fornecedor e o app lembra
              nas próximas vezes.
            """)
            st.markdown("**Como ter acesso:** digite seu código em *⭐ Tenho um código Plus*, "
                        "no menu lateral.")
            b1, b2 = st.columns(2)
            if LINK_ASSINATURA:
                b1.link_button("⭐ Quero o Plus", LINK_ASSINATURA, type="primary")
            if LINK_CONSULTORIA:
                b2.link_button("💬 Falar com um especialista", LINK_CONSULTORIA)
            if not LINK_ASSINATURA and not LINK_CONSULTORIA:
                st.caption("As assinaturas abrem em breve.")
        st.stop()

    tab_ir, tab_recorrentes, tab_saude, tab_classificar = abas[6:]

    # ----------------------------------------------------------------------------
    with tab_ir:
        if not anos_ir:
            st.info("Não há transações.")
        else:
            ano = st.selectbox("Ano-calendário", anos_ir,
                               help="O ano em que os pagamentos aconteceram. A declaração é "
                                    "entregue no ano seguinte.")
            st.caption(f"Para a declaração entregue em {ano + 1}.")
            st.warning("Esta é uma lista para **conferir com seu contador**, não a declaração. "
                       "Só se deduz o que tem comprovação (notas fiscais ou recibo com "
                       "CPF/CNPJ). **Educação:** possui limite anual por pessoa e vale só para "
                       "ensino regular; remédios de farmácia, academia e cursos livres não são "
                       "dedutíveis; **plano de saúde:** só do titular e dependentes declarados.",
                       icon="⚠️")
            ir = plus.relatorio_ir(df_contas, ano)
            dedu, rend_pj, rend_pf = ir["deducoes"], ir["rendimentos_pj"], ir["rendimentos_pf"]

            st.subheader("Possíveis deduções")
            if dedu.empty:
                st.info("Nenhum pagamento de saúde, educação, previdência privada ou pensão "
                        "encontrado neste ano.")
            else:
                por_grupo = dedu.groupby("Grupo")["Total"].sum()
                for col, (grupo, total) in zip(st.columns(len(por_grupo)), por_grupo.items()):
                    col.metric(grupo, formatar_reais(total))
                st.dataframe(tabela_em_reais(dedu, ["Total"]), hide_index=True, width="stretch",
                             column_order=["Grupo", "Fornecedor", "CNPJ", "Total", "Pagamentos"])
                st.caption("O CNPJ aparece quando está no extrato (Pix). Para os outros, pegue no "
                           "recibo ou na nota fiscal.")

            st.subheader("Rendimentos")
            r1, r2 = st.columns(2)
            with r1:
                st.markdown("**Recebidos de empresas**")
                if rend_pj.empty:
                    st.caption("Nenhum neste ano.")
                else:
                    st.dataframe(tabela_em_reais(rend_pj, ["Total"]), hide_index=True,
                                 width="stretch",
                                 column_order=["Fornecedor", "CNPJ", "Total", "Pagamentos"])
                    st.caption("Confira com o informe de rendimentos que cada empresa envia.")
            with r2:
                st.markdown("**Recebidos de pessoas, por mês**")
                if rend_pf.empty:
                    st.caption("Nenhum neste ano.")
                else:
                    st.dataframe(tabela_em_reais(rend_pf.assign(Mês=rend_pf["Mês"].map(rotulo_mes)),
                                                 ["Total"]), hide_index=True, width="stretch")
                    st.caption("Se for pagamento por serviço, pode precisar de Carnê-Leão. Entre "
                               "os recebidos podem estar transferências de família e reembolsos: "
                               "separe com o contador.")

            planilha_ir = io.BytesIO()
            with pd.ExcelWriter(planilha_ir, engine="openpyxl") as planilha:
                dedu.to_excel(planilha, sheet_name="Deduções", index=False)
                rend_pj.to_excel(planilha, sheet_name="Rendimentos de empresas", index=False)
                rend_pf.to_excel(planilha, sheet_name="Recebidos de pessoas", index=False)
            st.download_button("📥 Baixar para o contador (XLSX)", planilha_ir.getvalue(),
                               f"imposto_de_renda_{ano}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ----------------------------------------------------------------------------
    with tab_recorrentes:
        p1, p2, p3 = st.columns(3)
        p1.metric("Contas que se repetem, por mês", formatar_reais(compromissos),
                  help="Valor fixo e contas mensais ainda ativas.")
        p2.metric("Parcelas no próximo mês", formatar_reais(parcelas_proximo))
        p3.metric("Total de parcelas a pagar", formatar_reais(parcelas["Total restante"].sum()))

        st.subheader("Parcelas do cartão a vencer")
        if parcelas.empty:
            st.info("Nenhuma compra parcelada com parcelas a vencer. As parcelas são lidas da "
                    "fatura do cartão em PDF (BB), onde aparecem como \"PARC 03/10\".")
        else:
            dica("Passe o mouse sobre o gráfico para ver as parcelas de cada mês")
            st.altair_chart(grafico_linhas(plus.cronograma_por_compra(parcelas),
                                           "Total das parcelas"), width="stretch")
            ver = parcelas.assign(**{"Parcela": parcelas["Parcela atual"].astype(str) + "/"
                                     + parcelas["Parcelas"].astype(str),
                                     "Última parcela": parcelas["Última parcela"].map(rotulo_mes)})
            st.dataframe(tabela_em_reais(ver, ["Valor da parcela", "Total restante"]),
                         hide_index=True, width="stretch",
                         column_order=["Fornecedor", "Conta", "Valor da parcela", "Parcela",
                                       "Restam", "Total restante", "Última parcela"])
            st.caption("Parcela = a última paga. Se faltar a fatura de algum mês recente, ela é "
                       "estimada pelos meses que se passaram.")

        st.subheader("Gastos que se repetem")
        if recorrentes.empty:
            st.info("Envie extratos de pelo menos 3 meses para encontrar os gastos que se repetem.")
        else:
            st.caption("**Valor fixo:** mesmo valor todo mês (assinatura, seguro). **Conta "
                       "mensal:** uma vez por mês, valor varia (luz, plano de saúde). **Gasto "
                       "frequente:** quase todo mês, várias vezes (padaria, mercado).")
            mensais = recorrentes[recorrentes["Tipo"].isin([plus.FIXO, plus.CONTA_MENSAL])]
            frequentes = recorrentes[recorrentes["Tipo"] == plus.FREQUENTE]
            if not mensais.empty:
                st.markdown("**Valor fixo e contas mensais**")
                dica("Passe o mouse sobre o gráfico para ver os valores de cada mês")
                st.altair_chart(grafico_linhas(plus.historico_recorrentes(df_contas, mensais),
                                               "Total por mês"), width="stretch")
                with st.expander("📋 Ver em tabela, com a data prevista do próximo"):
                    st.dataframe(tabela_em_reais(mensais, ["Por mês"]), hide_index=True,
                                 width="stretch",
                                 column_config={"Por mês": st.column_config.TextColumn(
                                     "Por mês", help="O valor típico de um mês.")})
                    st.caption("A data prevista repete o dia de costume.")
            if not frequentes.empty:
                st.markdown("**Gastos frequentes**")
                st.dataframe(tabela_em_reais(frequentes.drop(columns="Próxima prevista"),
                                             ["Por mês"]), hide_index=True, width="stretch",
                             column_config={"Por mês": st.column_config.TextColumn(
                                 "Por mês", help="Média por mês.")})

    # ----------------------------------------------------------------------------
    with tab_saude:
        guardado = st.number_input(
            "Quanto você tem guardado hoje, em reais? (opcional)", min_value=0, step=1000,
            help="Poupança, investimentos e caixinhas que você pode resgatar. "
                                "Serve só para calcular a reserva de emergência e não é salvo.")
        itens = plus.indicadores(df, compromissos, parcelas_proximo, guardado or None)
        SINAL = {plus.BOM: ("#0ca30c", "Bom"), plus.ATENCAO: ("#fab219", "Atenção"),
                 plus.ALERTA: ("#d03b3b", "Alerta")}
        cartoes = ['<div class="cartoes">']
        for i in itens:
            cor, rotulo = SINAL[i["status"]]
            cartoes.append(
                f'<div class="cartao" style="--cor:{cor}"><div class="titulo">{escape(i["nome"])}'
                f'</div><div class="valor">{escape(i["valor"])}</div>'
                f'<div class="status">{rotulo}</div>'
                f'<div class="explica">{escape(i["explicacao"])}</div></div>')
        cartoes.append("</div>")
        st.markdown("".join(cartoes), unsafe_allow_html=True)
        st.caption(f"Período: {periodo}. Os limites são referências de educação financeira, "
                   "não regras: cada situação é única. Meses só com a fatura do cartão (sem o "
                   "extrato da conta) ficam de fora.")
        if any(i["status"] != plus.BOM for i in itens):
            st.markdown("**Quer ajuda para virar o jogo?** Um consultor olha esses números com "
                        "você e monta um plano.")
            if LINK_CONSULTORIA:
                st.link_button("💬 Falar com um especialista", LINK_CONSULTORIA, type="primary")

    # ----------------------------------------------------------------------------
    with tab_classificar:
        if st.session_state.get("aviso_regras"):
            st.success(st.session_state.pop("aviso_regras"), icon="✅")

        with st.expander("❓ Como funciona esta aba", expanded=True):
            st.markdown("""
            Aqui **você mesmo** corrige a categoria dos gastos — direto na tabela. O app
            aprende e, nos próximos extratos, já classifica esse fornecedor sozinho.

            1. A tabela mostra cada **fornecedor** (por padrão, só os que ficaram em OUTRO ou
               TRANSFERÊNCIA). Desligue o botão acima da tabela para ver todos.
            2. **Dê dois cliques** na célula **Categoria** (e, se quiser, em **Subcategoria**)
               e escolha a opção certa na lista.
            3. Clique em **💾 Salvar e lembrar**. Pronto: a regra vale para todos os
               lançamentos desse fornecedor, hoje e nos próximos meses.

            **Onde fica guardado:** empresas vão para a base compartilhada (dados públicos,
            ajudam todo mundo). Pix para pessoas nunca vai para a base: fica nas suas regras
            pessoais, que você baixa em arquivo e recarrega na próxima vez.
            """)

        st.subheader("Corrigir categorias por fornecedor")
        dica("Escolha a categoria e a subcategoria na tabela e clique em Salvar · "
             "o app lembra nas próximas vezes, para todos os lançamentos desse fornecedor")
        so_pendentes = st.toggle("Mostrar só OUTRO e TRANSFERÊNCIA", value=True)

        grupo = (saidas_forn.groupby("chave")
                 .agg(Fornecedor=("Fornecedor", lambda v: max(v.unique(), key=len)),
                      Categoria=("Categoria", lambda v: v.mode().iat[0]),
                      Subcategoria=("Subcategoria", lambda v: v.mode().iat[0]),
                      Total=("Valor", lambda v: -v.sum()),
                      Transações=("Valor", "count"))
                 .sort_values("Total", ascending=False).reset_index())
        if so_pendentes:
            grupo = grupo[grupo["Categoria"].isin(["OUTRO", "TRANSFERÊNCIA"])].reset_index(drop=True)
        grupo["Subcategoria"] = grupo["Subcategoria"].replace("", SEM_SUB).fillna(SEM_SUB)
        grupo["Valor"] = grupo["Total"].map(formatar_reais)

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
                sub = subcategoria_valida(r["Categoria"], r["Subcategoria"])
                linhas = saidas_forn[saidas_forn["chave"] == r["chave"]]
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

        st.subheader("Consultar CNPJ na Receita")
        secao_cnpj(lembrar=True)

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
                st.markdown("**Guardar de vez:** baixe o arquivo abaixo e recarregue na próxima "
                            "vez. Se o app é seu, também pode colar o texto em Settings → Secrets "
                            "do Streamlit Cloud" + (" (acrescente as linhas dentro do "
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
