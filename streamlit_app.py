import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape
from urllib.parse import quote

import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import pickle
import importlib
import secrets
import sys
import zipfile

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# Depois de uma atualização, o Streamlit Cloud recarrega este arquivo mas pode
# manter na memória a versão antiga de financeiro.py e regras.py, e o app quebra
# com ImportError até alguém reiniciar. Recarregá-los aqui evita isso.
for _modulo in ("financeiro", "leitores_pdf", "regras", "codigos", "plus", "relatorio", "exemplo"):   # nessa ordem
    if _modulo in sys.modules:
        importlib.reload(sys.modules[_modulo])

from leitores_pdf import SemLancamentos
from financeiro import (
    CATEGORIA_APLICACAO,
    CATEGORIA_PADRAO,
    SUB_NAO_IDENTIFICADO,
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
    nao_identificado,
    subcategorias_de,
    coluna_pct,
    resumo_categorias,
    resumo_fornecedores,
    resumo_mensal,
    resumo_subcategorias,
)
from regras import RepositorioRegras, consultar_cnpj, juntar, nova_regra, regras_vazias
import exemplo
import codigos
import plus
import relatorio

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Contas em Dia",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state=210,   # barra lateral estreita (o visitante pode arrastar a borda)
)

# Na primeira visita o app abre no tema escuro; depois vale a escolha do visitante em ⋮
st.html("""<script>
(() => { try { if (!localStorage.getItem("contasEmDia-tema")) {
    localStorage.setItem("contasEmDia-tema", "1");
    localStorage.setItem(`stActiveTheme-${window.location.pathname}-v2`, '"Dark"');
    location.reload(); } } catch (e) {} })();
</script>""", unsafe_allow_javascript=True)

# Identidade visual: azul-marinho, dourado e branco-osso. Os temas claro e escuro
# ficam em .streamlit/config.toml; o CSS abaixo herda a cor do texto do tema
# (currentColor) para funcionar nos dois.
DOURADO = "#c9a227"        # detalhes (linhas, bordas); não usado em dados
CIANO = "#70ddff"          # destaques no tema escuro
MARINHO = "#1d2b42"
ARDOSIA = "#506585"        # bordas e textos discretos
OSSO = "#f7f3ea"
ESCURO = (st.context.theme.type or "dark") == "dark"
# Cores dos gráficos: validadas para contraste >= 3:1 e separação para daltonismo
# tanto no fundo branco-osso quanto no azul-marinho escuro
COR_ENTRADAS = CIANO if ESCURO else "#3d6bc4"   # ciano / azul
COR_SAIDAS = DOURADO if ESCURO else "#a8801f"   # dourado
# Cores dos gráficos: validadas para contraste >= 3:1 e separação para daltonismo
# tanto no fundo branco-osso quanto no azul-marinho escuro

# Cores que mudam com o tema: ciano no escuro, marinho no claro
DESTAQUE = CIANO if ESCURO else MARINHO
CARTAO_FUNDO = ("linear-gradient(160deg, #24395c, #1b2a44)" if ESCURO
                else "color-mix(in srgb, #1d2b42 5%, transparent)")
TEXTO_PRIMARIO = MARINHO if ESCURO else "#ffffff"

st.markdown(f"""
<style>
  [data-testid="stMainBlockContainer"] {{ padding-top: 2.6rem; }}
  .cabecalho {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem;
                border-bottom: 1px solid color-mix(in srgb, {DOURADO} 60%, transparent);
                padding-bottom: .35rem; margin-bottom: .9rem; }}
  .cabecalho h1 {{ font-weight: 700; margin: 0; padding: 0; font-size: 2.6rem; line-height: 1.1; }}
  .cabecalho .sistema {{ text-align: right; font-size: .9rem; margin: 0; opacity: .8;
                         letter-spacing: .04em; }}
  .cabecalho .slogan {{ text-align: right; color: {DOURADO}; font-style: italic;
                        font-size: 1rem; margin: 0; letter-spacing: .02em; }}
  [data-testid="stMetric"] {{ background: {CARTAO_FUNDO}; border-radius: 10px;
                              border: 1px solid color-mix(in srgb, {DESTAQUE} 40%, transparent);
                              padding: .75rem 1rem; height: 100%; }}
  [data-testid="stMetricLabel"] p {{ font-weight: 600; }}
  [data-testid="stMetricValue"] {{ font-size: 1.5rem; font-weight: 700; }}
  .dica {{ font-size: .85rem; margin: -.3rem 0 .6rem 0; opacity: .7; }}
  .dica::before {{ content: "☝ "; color: {DOURADO}; }}
  [data-testid="stSidebar"] {{ border-right: 1px solid color-mix(in srgb, {ARDOSIA} 70%, transparent); }}
  [data-testid="stSidebarContent"] {{ padding-left: .7rem; padding-right: .7rem; }}
  [data-testid="stSidebarContent"] [data-testid="stSidebarUserContent"] {{ padding: 0 0 2rem 0; }}
  .marca {{ text-align: center; margin: -.4rem 0 .9rem 0; }}
  [data-testid="stSidebarHeader"] {{ height: 2.2rem; margin-bottom: 0; }}
  .marca {{ text-align: center; margin: 0 0 .6rem 0; line-height: 1.3; }}
  .marca b {{ display: block; font-size: 1rem; letter-spacing: .08em; white-space: nowrap; }}
  .marca span {{ display: block; color: {DOURADO}; font-size: .6rem; font-weight: 700;
                 letter-spacing: .16em; white-space: nowrap; }}
  [data-testid="stMarkdownContainer"] p.secao {{ font-size: .7rem; letter-spacing: .14em;
      text-transform: uppercase; opacity: .65; margin: .5rem 0 0 0; font-weight: 600; }}
  [data-testid="stSidebarUserContent"] [data-testid="stCaptionContainer"] {{ font-size: .78rem; }}
  [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{ padding: .7rem .5rem;
      flex-direction: column; gap: .3rem; border: 1px dashed color-mix(in srgb, {ARDOSIA} 90%, transparent); }}
  [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {{ width: 100%; }}
  [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] {{ display: none; }}
  /* Menu de navegação: o rádio vira uma lista de itens */
  .st-key-menu [role="radiogroup"] {{ gap: .1rem; width: 100%; }}
  .st-key-menu [role="radiogroup"] > div {{ width: 100%; }}
  .st-key-menu [data-testid="stRadioOption"] {{ width: 100%; margin: 0; padding: .4rem .65rem;
      border-radius: 8px; border-left: 3px solid transparent; cursor: pointer; }}
  .st-key-menu [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
  .st-key-menu [data-testid="stRadioOption"]:hover {{
      background: color-mix(in srgb, {DESTAQUE} 10%, transparent); }}
  .st-key-menu [data-testid="stRadioOption"][data-selected="true"] {{
      background: color-mix(in srgb, {DESTAQUE} 16%, transparent); border-left-color: {DOURADO}; }}
  .st-key-menu [data-testid="stRadioOption"][data-selected="true"] p {{ font-weight: 600; }}
  /* Barra do topo: visões do Painel no meio, período e filtros à direita */
  .st-key-visoes [data-testid="stButtonGroup"] {{ display: flex; }}
  .st-key-visoes [data-testid="stButtonGroup"] > div {{ border-radius: 999px; padding: 3px;
      border: 1px solid color-mix(in srgb, {ARDOSIA} 80%, transparent); }}
  .st-key-visoes button {{ border-radius: 999px !important; border: none !important;
      min-width: 6.5rem; }}
  .st-key-visoes button[aria-checked="true"] {{ background: {DESTAQUE} !important; }}
  .st-key-visoes button[aria-checked="true"] p {{ font-weight: 700; color: {TEXTO_PRIMARIO}; }}
  [data-testid="stMarkdownContainer"] p.titulo-pagina {{ font-size: 1.35rem; font-weight: 700; margin: .2rem 0 0 0; }}
  .st-key-periodo [data-baseweb="input"] {{ border-radius: 999px; }}
  /* Faixa verde com os arquivos lidos à direita */
  .st-key-faixa_aviso {{ background: color-mix(in srgb, #fab219 16%, transparent);
      border: 1px solid color-mix(in srgb, #fab219 60%, transparent); border-radius: 8px;
      padding: .2rem .4rem .2rem .9rem; min-height: 3rem; justify-content: center; }}
  .st-key-faixa_aviso [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
  .st-key-faixa_aviso [data-testid="stHorizontalBlock"] {{ align-items: center; }}
  .st-key-faixa_aviso [data-testid="stPopover"] {{ display: flex; justify-content: flex-end; }}
  .st-key-faixa_aviso button {{ border: none; background: transparent; }}
  .st-key-barra_filtros {{ margin: .3rem 0 .2rem 0; }}
  .st-key-faixa_ok {{ min-height: 3rem; justify-content: center; }}
  .st-key-faixa_ok {{ background: color-mix(in srgb, #0ca30c 16%, transparent);
      border: 1px solid color-mix(in srgb, #0ca30c 55%, transparent); border-radius: 8px;
      padding: .2rem .4rem .2rem .9rem; margin-bottom: 0; }}
  .st-key-faixa_ok [data-testid="stHorizontalBlock"] {{ align-items: center; }}
  .st-key-faixa_ok p {{ margin: 0; }}
  .st-key-faixa_ok [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
  .st-key-faixa_ok [data-testid="stPopover"] {{ display: flex; justify-content: flex-end; }}
  /* Cartões de números do Painel */
  /* 4 cartões numa linha; sem espaço, 2 e 2 (nunca 3 + 1) */
  .kpis-caixa {{ container-type: inline-size; }}
  @container (max-width: 680px) {{
    .kpis.kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .8rem;
           margin-bottom: 1rem; }}
  .kpi {{ background: {CARTAO_FUNDO}; border-radius: 10px; padding: .75rem .9rem;
          border: 1px solid color-mix(in srgb, {DESTAQUE} 40%, transparent); min-width: 0;
          container-type: inline-size; }}
  .kpi .rot {{ font-weight: 600; font-size: .88rem; display: flex; gap: .45rem;
               align-items: center; }}
  .kpi .ico {{ background: color-mix(in srgb, {DESTAQUE} 18%, transparent); border-radius: 6px;
               padding: .05rem .3rem; }}
  /* O valor diminui com a largura do cartão, para caber inteiro (ex.: R$ 140.779,00) */
  .kpi .val {{ font-size: clamp(.9rem, 12.5cqi, 1.5rem); font-weight: 700; white-space: nowrap;
               font-variant-numeric: tabular-nums; margin: .35rem 0 .1rem 0; overflow: hidden;
               text-overflow: ellipsis; }}
  .kpi .val.neg {{ color: {"#ff8a80" if ESCURO else "#c62828"}; }}
  .kpi .val.ouro {{ color: {DOURADO}; }}
  .kpi .nota {{ font-size: .76rem; opacity: .72; }}
  .st-key-faixa_ok button {{ border: none; background: transparent; }}
  /* Painéis com borda e o painel em degradê ciano */
  .titulo-painel {{ font-weight: 700; font-size: 1.05rem; margin-bottom: .3rem; }}
  .titulo-painel .tag {{ background: {DOURADO}; color: {MARINHO}; font-size: .72rem;
      border-radius: 999px; padding: .1rem .55rem; margin-left: .5rem; vertical-align: middle; }}
  .st-key-painel_ciano {{ background: linear-gradient(170deg, #7fe2ff 0%, #3fa7d6 55%, #2f7fb0 100%);
      color: {MARINHO}; border-radius: 12px; padding: 1rem 1.1rem 1.2rem 1.1rem;
      box-sizing: border-box; container-type: inline-size; }}
  /* Painel estreito: o nome numa linha, o valor e o % embaixo (classe dobrada para vencer
     as regras do painel, que vêm depois) */
  @container (max-width: 300px) {{
    .st-key-painel_ciano.st-key-painel_ciano .tabcat .linha {{ grid-template-columns: 1fr auto; row-gap: .1rem; }}
    .st-key-painel_ciano.st-key-painel_ciano .tabcat .linha .nome {{ grid-column: 1 / -1; }}
    .st-key-painel_ciano.st-key-painel_ciano .tabcat .linha > .num:not(.qtd) {{ text-align: left; }}
    .st-key-painel_ciano.st-key-painel_ciano .tabcat .linha .pct {{ min-width: 3.4rem; justify-content: flex-end; }}
    .st-key-painel_ciano.st-key-painel_ciano .tabcat .linha .pct b {{ text-align: right; }}
  }}
  .st-key-painel_ciano * {{ color: {MARINHO}; }}
  .st-key-painel_ciano h3 {{ margin: 0; padding: 0 0 .2rem 0; }}
  .st-key-painel_ciano .sub-titulo {{ font-size: .72rem; letter-spacing: .12em; font-weight: 700;
      text-transform: uppercase; margin-bottom: .3rem; }}
  .st-key-painel_ciano .tabcat {{ border: none; font-size: .86rem; }}
  /* No painel estreito, a barra de % vai por baixo da linha */
  .st-key-painel_ciano .tabcat .linha {{ grid-template-columns: minmax(0, 1fr) auto 3.3rem;
      padding: .38rem 0 .55rem 0; gap: .6rem; position: relative; }}
  .st-key-painel_ciano .tabcat .pct .trilho {{ position: absolute; left: 0; right: 0; bottom: 3px;
      height: 4px; }}
  .st-key-painel_ciano .tabcat .pct b {{ min-width: 0; width: 100%; }}
  .st-key-painel_ciano .tabcat .num, .st-key-painel_ciano .tabcat .pct b {{ white-space: nowrap; }}
  .st-key-painel_ciano .dica {{ font-size: .78rem; margin-top: .6rem; }}
  .st-key-painel_ciano .tabcat .linha .nome {{ text-transform: lowercase; display: inline-block; }}
  .st-key-painel_ciano .tabcat .linha .nome::first-letter {{ text-transform: uppercase; }}
  .st-key-painel_ciano .tabcat .forn .nome {{ padding-left: 0; }}
  .st-key-painel_ciano .tabcat .qtd {{ display: none; }}
  .st-key-painel_ciano .tabcat .linha + .linha, .st-key-painel_ciano .tabcat details {{
      border-bottom: 1px solid rgba(29, 43, 66, .18); }}
  .st-key-painel_ciano .tabcat .pct .trilho {{ background: rgba(29, 43, 66, .18); }}
  .st-key-painel_ciano .tabcat .pct .trilho i {{ background: {MARINHO}; }}
  .st-key-painel_ciano .dica {{ opacity: .8; }}
  .st-key-painel_ciano .dica::before {{ color: {MARINHO}; }}
  /* Categorias escolhidas (pílulas) */
  .stButtonGroup button[data-variant="pills"][aria-checked="true"] {{
      border-color: {DESTAQUE}; background: color-mix(in srgb, {DESTAQUE} 16%, transparent); }}
  [class*="st-key-todos_nenhum"] [data-testid="stBaseButton-tertiary"] {{ border: none; background: transparent; padding: 0 .3rem;
      min-height: 0; opacity: .75; }}
  [class*="st-key-todos_nenhum"] {{ flex-wrap: wrap; row-gap: .2rem; }}
  /* As pílulas quebram em várias linhas em vez de passar da tela */
  [class*="st-key-todos_nenhum"] > div:has([data-testid="stButtonGroup"]) {{
      flex: 0 1 auto; min-width: 0; max-width: 100%; }}
  [class*="st-key-todos_nenhum"] [data-testid="stButtonGroup"] [role="group"],
  [class*="st-key-todos_nenhum"] [data-testid="stButtonGroup"] > div {{ flex-wrap: wrap; }}
  [class*="st-key-todos_nenhum"] p {{ font-size: .82rem; }}
  .st-key-ir_plus button {{ border: 1px solid {DOURADO}; color: {DOURADO}; border-radius: 999px;
      background: transparent; font-weight: 700; }}
  .st-key-ir_plus button:hover {{ background: color-mix(in srgb, {DOURADO} 15%, transparent);
      color: {DOURADO}; border-color: {DOURADO}; }}
  [data-testid="stBaseButton-primary"] {{ color: {TEXTO_PRIMARIO}; }}

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
      content: "📄\\A Arraste seus extratos para cá\\A ou"; white-space: pre; text-align: center;
      font-size: 1.15rem; font-weight: 600; line-height: 1.7; }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzone"] > span {{ order: 1; }}
  .st-key-upload_grande [data-testid="stFileUploaderDropzoneInstructions"] {{ order: 2; }}
  .st-key-upload_grande [data-testid="stBaseButton-secondary"] {{
      background: {COR_ENTRADAS}; color: {TEXTO_PRIMARIO}; border: none; border-radius: 999px;
      padding: .7rem 1.6rem; font-size: 1.05rem; font-weight: 600; }}
  .st-key-upload_grande [data-testid="stBaseButton-secondary"]:hover {{
      background: color-mix(in srgb, {COR_ENTRADAS} 85%, #000); color: {TEXTO_PRIMARIO}; }}
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
  .st-key-assinar_flutuante {{ position: fixed; right: 1.2rem; bottom: 4.6rem; z-index: 999990;
                               width: auto !important; }}
  .st-key-assinar_flutuante button {{ background: {DOURADO}; color: #0f1a2e; border: none;
                                      border-radius: 999px; padding: .6rem 1.05rem;
                                      font-weight: 600; box-shadow: 0 3px 12px rgba(0,0,0,.25); }}
  .st-key-assinar_flutuante button:hover {{ background: #d8b23a; color: #0f1a2e; }}
  .st-key-assinar_flutuante button p {{ font-weight: 600; }}
  .flutuantes .curto {{ display: none; }}
  /* Espaço no fim da página para os botões não cobrirem o rodapé */
  [data-testid="stMainBlockContainer"] {{ padding-bottom: 8rem; }}
  @media (max-width: 640px) {{
    .flutuantes {{ right: .8rem; bottom: .8rem; }}
    .st-key-assinar_flutuante {{ right: .8rem; bottom: 3.9rem; }}
    .flutuantes a {{ font-size: .8rem; padding: .5rem .85rem; }}
    .flutuantes .longo {{ display: none; }}
    .flutuantes .curto {{ display: inline; }}
    .tabcat .linha {{ grid-template-columns: minmax(0, 1.6fr) 1.2fr 1fr; }}
    .tabcat .qtd {{ display: none; }}
    .cabecalho {{ flex-direction: column; align-items: stretch; gap: .2rem; }}
    .cabecalho h1 {{ font-size: 2rem; }}
    .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
</style>
<div class="cabecalho">
  <h1>Contas em Dia</h1>
  <div><p class="sistema">Sistema de Controle Financeiro</p>
  <p class="slogan">Seus gastos na palma da mão</p></div>
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


def _curto(v):
    """Valor curto para rótulo de ponto: 850 / 7,2 mil / 13 mil."""
    a = abs(v)
    if a >= 10000:
        return f"{a / 1000:.0f} mil"
    if a >= 1000:
        return f"{a / 1000:.1f} mil".replace(".", ",")
    return f"{a:.0f}"


def grafico_mensal(mensal, series=None, altura=380):
    """Entrou e saiu, mês a mês: duas linhas com o valor em cada ponto (o da linha mais alta
    em cima do ponto, o da mais baixa embaixo) e o nome no fim de cada linha.

    series: (coluna, nome, cor) de cada linha; o padrão é Entradas e Saídas."""
    series_cfg = series or [("Entradas", "Entrou", COR_ENTRADAS), ("Saídas", "Saiu", COR_SAIDAS)]
    longo = mensal.melt(id_vars="Mês", value_vars=[c for c, _, _ in series_cfg],
                        var_name="Tipo", value_name="Total")
    longo["Série"] = longo["Tipo"].map({c: n for c, n, _ in series_cfg})
    longo["Rótulo"] = longo["Mês"].map(rotulo_mes)
    longo["Valor"] = longo["Total"].map(formatar_reais)
    longo["Texto"] = longo["Total"].map(_curto)
    maior = longo.groupby("Mês")["Total"].transform("max")
    longo["Acima"] = longo["Total"] >= maior
    ordem = [rotulo_mes(m) for m in mensal["Mês"]]
    series = [n for _, n, _ in series_cfg]
    x = alt.X("Rótulo:N", sort=ordem, title=None, axis=alt.Axis(labelAngle=0, labelOverlap=True),
              scale=alt.Scale(padding=0.3))
    y = alt.Y("Total:Q", axis=EIXO_REAIS)
    cor = alt.Color("Série:N", sort=series, legend=None,
                    scale=alt.Scale(domain=series, range=[c for _, _, c in series_cfg]))
    base = alt.Chart(longo).encode(x=x, y=y, color=cor)
    linhas = base.mark_line(strokeWidth=2.5)
    pontos = base.mark_point(filled=True, size=70, opacity=1).encode(
        tooltip=[alt.Tooltip("Rótulo:N", title="Mês"), alt.Tooltip("Série:N", title=""),
                 alt.Tooltip("Valor:N", title="Total")])
    texto = dict(fontSize=11, color=cor_do_texto())
    em_cima = alt.Chart(longo[longo["Acima"]]).mark_text(baseline="bottom", dy=-7, **texto) \
        .encode(x=x, y=y, text="Texto:N")
    embaixo = alt.Chart(longo[~longo["Acima"]]).mark_text(baseline="top", dy=7, **texto) \
        .encode(x=x, y=y, text="Texto:N")
    fim = longo[longo["Mês"] == mensal["Mês"].iloc[-1]]
    nomes = alt.Chart(fim).mark_text(align="left", dx=10, fontSize=12, fontWeight="bold",
                                     color=cor_do_texto()).encode(x=x, y=y, text="Série:N")
    return (linhas + pontos + em_cima + embaixo + nomes).properties(
        width="container", height=altura,
        padding={"left": 5, "top": 10, "bottom": 5, "right": 8},
        autosize=alt.AutoSizeParams(type="fit", contains="padding"))


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
                   altura=ALTURA_LINHAS, largura_nomes=LARGURA_NOMES, com_total=True):
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
    # Sem o total (com_total=False), as linhas usam a altura toda do gráfico
    total = longo.groupby("Mês", as_index=False)["Valor"].sum().assign(Fornecedor=nome_total)
    dados = pd.concat([longo, total], ignore_index=True) if com_total else longo.copy()
    dados["Rótulo"] = dados["Mês"].map(rotulo_mes)
    dados["Texto"] = dados["Valor"].map(formatar_reais)
    rotulos = [rotulo_mes(m) for m in meses]
    nomes = ([nome_total] if com_total else []) + series
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
                    scale=alt.Scale(domain=nomes, range=([COR_TOTAL] if com_total else []) + CORES_SERIES[:len(series)]))
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


@st.cache_data(show_spinner=False)
def relatorio_de_exemplo():
    """PDF de exemplo da vitrine (dados fictícios); gerado uma vez por servidor."""
    return exemplo.relatorio_exemplo()


def na_sessao(nome, chave, calcular, guardar=8):
    """Guarda o resultado na memória da sessão, para os cliques seguintes não refazerem a
    leitura dos extratos. Fica só na sessão (some ao fechar o app), nunca num cache do
    servidor compartilhado. Erros também são lembrados e repetidos."""
    memoria = st.session_state.setdefault("_memoria", {}).setdefault(nome, {})
    k = chave
    if k not in memoria:
        try:
            memoria[k] = ("ok", calcular())
        except Exception as e:  # noqa: BLE001 - o erro volta para quem chamou
            memoria[k] = ("erro", e)
        while len(memoria) > guardar:
            memoria.pop(next(iter(memoria)))
    situacao, valor = memoria[k]
    if situacao == "erro":
        raise valor
    # Cópia: quem recebe pode alterar as tabelas sem mexer no que ficou guardado
    return copy.deepcopy(valor)


def impressao(*partes):
    """Identificador curto do conteúdo (bytes, tabelas, textos), para usar como chave."""
    h = hashlib.sha256()
    for p in partes:
        if isinstance(p, bytes):
            h.update(p)
        elif isinstance(p, pd.DataFrame):
            h.update(pd.util.hash_pandas_object(p, index=False).values.tobytes())
            h.update(repr(list(p.columns)).encode())
        else:
            h.update(pickle.dumps(p))
        h.update(b"|")
    return h.hexdigest()


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _cnpj_guardado(cnpj, tempo=10):
    info = consultar_cnpj(cnpj, tempo)
    if info is None:
        raise LookupError(cnpj)   # erro não fica no cache: tenta de novo da próxima vez
    return info


def consultar_cnpj_cache(cnpj):
    """Dados públicos do CNPJ (guardados por uma semana), ou None se a consulta falhar."""
    try:
        return _cnpj_guardado(cnpj)
    except LookupError:
        return None


MAX_CNPJ_POR_VEZ = 30
TEMPO_CNPJ = 5   # segundos por consulta automática: a Receita lenta não trava a tela


def consultar_cnpj_cache_sem_contexto(cnpj):
    """Para as consultas em paralelo (fora da execução da página): usa a mesma memória de
    uma semana quando dá, senão consulta direto."""
    try:
        return _cnpj_guardado(cnpj, TEMPO_CNPJ)
    except LookupError:
        return None
    except Exception:  # noqa: BLE001 - sem o contexto do Streamlit, consulta sem memória
        return consultar_cnpj(cnpj, TEMPO_CNPJ)


def cnpjs_pendentes(t, regras):
    """Fornecedores de saída sem categoria (ou só "transferência") que ainda não têm regra e
    trazem CNPJ na descrição: [chave, CNPJ, Fornecedor]."""
    s = t[t["Tipo"] == "Saída"]
    s = s.assign(chave=s["FornecedorOriginal"].map(chave_fornecedor),
                 CNPJ=s["Descrição"].map(extrair_cnpj))
    pendente = pd.Series([c == "TRANSFERÊNCIA" or nao_identificado(c, sc) for c, sc in
                          zip(s["Categoria"], s["Subcategoria"])], index=s.index, dtype=bool)
    s = s[pendente & ~s["chave"].isin(set(regras["chave"])) & s["CNPJ"].notna()]
    return (s.groupby(["chave", "CNPJ"], as_index=False)
            .agg(Fornecedor=("Fornecedor", "first")))


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
# Sem limitar o tipo no envio: no celular, arquivos do Google Drive e de outros apps
# costumam chegar sem extensão (ou com outra), e o Streamlit recusaria a página inteira.
# Cada arquivo é reconhecido pelo conteúdo, e o que não for extrato aparece no aviso amarelo
TIPOS_EXTRATO = None
DICA_DRIVE = ("**No celular, baixe o arquivo antes de enviar.** Arquivos escolhidos direto do "
              "Google Drive costumam falhar (aparece um \"!\" vermelho). No Drive, abra o arquivo "
              "→ **⋮ → Fazer download** e, aqui, escolha-o pela pasta **Downloads**.")
_navegador = (st.context.headers.get("User-Agent") or "").lower()
NO_CELULAR = any(x in _navegador for x in ("android", "iphone", "ipad", "mobile"))
# Arquivos enviados pela área grande da tela inicial: guardados na sessão (só na memória)
# porque aquela área some depois do envio
st.session_state.setdefault("arquivos_principal", [])

with st.sidebar:
    st.markdown('<div class="marca"><b>CONTAS EM DIA</b><span>CONTROLE FINANCEIRO</span></div>'
                '<p class="secao">📁 Seus extratos</p>', unsafe_allow_html=True)
    arquivos_lateral = st.file_uploader(
        "Escolha seus extratos", label_visibility="collapsed",
        type=TIPOS_EXTRATO,
        accept_multiple_files=True,
        help="Extratos em CSV, Excel ou OFX de qualquer banco, de vários meses e contas. "
             "Em PDF: extratos Nubank, Sicredi e XP, e fatura do cartão BB. Pode mandar o mesmo "
             "mês em mais de um formato: as repetições são descartadas. Pode mandar "
             "uma pasta compactada (.zip)."
    )
    if st.session_state["arquivos_principal"]:
        st.caption(f"📎 {len(st.session_state['arquivos_principal'])} arquivo(s) enviado(s) "
                   "pela tela principal")
        if st.button("Remover esses arquivos", type="tertiary"):
            st.session_state["arquivos_principal"] = []
            st.rerun()
    arquivos = list(arquivos_lateral or []) + st.session_state["arquivos_principal"]
    nome_titular = st.text_input(
        "Seu nome (opcional)", label_visibility="collapsed",
        placeholder="Seu nome (opcional)",
        help="Pix e TED para você mesmo em outro banco viram transferência entre "
             "contas, e não gasto. Use nome e sobrenome como aparecem no extrato."
    )
    # O menu de navegação é preenchido depois de ler os extratos (as páginas dependem do
    # Plus), mas fica aqui, acima da seção Plus
    menu_lateral = st.container()

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


def hoje_brasil():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def entrar_no_plus(codigo, nome):
    """Confere o código. Aceita os códigos assinados (com validade e titular) e os da
    lista fixa PLUS_CODIGOS (para testes e cortesias, sem validade). Retorna o erro ou ""."""
    codigo = (codigo or "").strip()
    if not codigo:
        return "Digite o código."
    if any(hmac.compare_digest(codigo.encode(), c.encode())
           for c in _lista_segredo("PLUS_CODIGOS")):
        st.session_state.update(plus=True, plus_ate=None, plus_titular="")
        return ""
    r = codigos.validar_codigo(CHAVE_PLUS, codigo, nome, hoje=hoje_brasil(),
                               bloqueados=set(_lista_segredo("PLUS_BLOQUEADOS")))
    if r["ok"]:
        st.session_state.update(plus=True, plus_ate=r["validade"],
                                plus_titular=" ".join(nome.split()))
        return ""
    return r["motivo"]


CHAVE_PLUS = ler_segredo("PLUS_CHAVE") or ""
LINK_ASSINATURA = ler_segredo("PLUS_LINK")
LINK_CONSULTORIA = ler_segredo("CONTATO_CONSULTORIA")
EMAIL_CONTATO = ler_segredo("CONTATO_EMAIL")
PRECO_PLUS = ler_segredo("PLUS_PRECO")   # opcional, só para mostrar ("R$ 19,90 por mês")
PRAZO_RESPOSTA = "Respondemos em até 1 dia útil."


def _whatsapp_com_texto(link, texto):
    """Link do WhatsApp (wa.me) com a mensagem já escrita."""
    if not link or "wa.me" not in link:
        return link
    return f"{link}{'&' if '?' in link else '?'}text={quote(texto)}"


def _email_com_texto(assunto, corpo):
    return f"mailto:{EMAIL_CONTATO}?subject={quote(assunto)}&body={quote(corpo)}" \
        if EMAIL_CONTATO else None


def _gmail_com_texto(assunto, corpo):
    """Abre a tela de escrever do Gmail no navegador (o "mailto:" só funciona quando há um
    programa de e-mail configurado no computador; com Gmail no navegador, não abre nada)."""
    return (f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(EMAIL_CONTATO)}"
            f"&su={quote(assunto)}&body={quote(corpo)}") if EMAIL_CONTATO else None


def botoes_email(colunas, assunto, corpo, disabled=False):
    """Gmail no navegador e outro programa de e-mail, mais o endereço para copiar."""
    c_gmail, c_app = colunas
    c_gmail.link_button("✉️ Gmail", _gmail_com_texto(assunto, corpo),
                        disabled=disabled)
    c_app.link_button("📧 Outro e-mail", _email_com_texto(assunto, corpo),
                      disabled=disabled)
    st.caption(f"Ou escreva para **{EMAIL_CONTATO}** (assunto: {assunto}).")


@st.dialog("⭐ Assinar o Contas em Dia Plus")
def abrir_assinatura():
    """Assinar em 2 passos: pagar pelo link e mandar o comprovante (é assim que o código
    chega: pelo mesmo canal em que a pessoa mandou o comprovante). Nada é guardado."""
    st.markdown("Relatório em PDF, Imposto de Renda, fixos e parcelas, saúde financeira e "
                "classificação que o app lembra." + (f" **{PRECO_PLUS}**." if PRECO_PLUS else ""))
    st.markdown("**1. Pague pelo link**")
    if LINK_ASSINATURA:
        st.link_button("💳 Pagar com Pix", LINK_ASSINATURA, type="primary")
    else:
        st.caption("Peça os dados para pagamento no passo 2.")
    st.markdown("**2. Envie o comprovante** pelo WhatsApp ou por e-mail")
    nome = st.text_input("Nome completo do titular dos extratos",
                         help="Como aparece no seu extrato. O código Plus vale para essa pessoa.",
                         placeholder="Ex: Maria da Silva Souza")
    texto = ("Olá! Acabei de assinar o Contas em Dia Plus.\n"
             f"Nome completo do titular (como aparece no extrato): {nome.strip() or '______'}\n"
             "Segue o comprovante do pagamento.")
    c1, c2, c3 = st.columns(3)
    if LINK_CONSULTORIA:
        c1.link_button("📱 WhatsApp", _whatsapp_com_texto(LINK_CONSULTORIA, texto),
                       disabled=not nome.strip())
    if EMAIL_CONTATO:
        botoes_email((c2, c3), "Assinatura Contas em Dia Plus", texto, disabled=not nome.strip())
    if not nome.strip():
        st.caption("Digite o nome para liberar os botões. Anexe o comprovante na mensagem.")
    st.markdown("**3. Receba seu código**")
    st.caption(f"O código chega pelo mesmo canal, depois da confirmação do pagamento. "
               f"{PRAZO_RESPOSTA} Para usar: menu lateral → ⭐ Tenho um código Plus.")


def secao_ajuda():
    """Dúvidas frequentes e contato (sem guardar nada)."""
    st.subheader("❓ Ajuda")
    duvidas = [
        ("Como baixo o extrato do meu banco?",
         "No app ou no site do banco, abra o **extrato** da conta (ou a **fatura** do cartão) e "
         "procure a opção de **exportar, compartilhar ou baixar**. O app lê CSV, Excel e OFX de "
         "qualquer banco e, em PDF, os extratos do Nubank, Sicredi e XP e a fatura do cartão BB. "
         "Quanto mais meses, melhores as análises."),
        ("No celular, o arquivo fica com um \"!\" vermelho e não envia.",
         DICA_DRIVE + " O mesmo vale para OneDrive, Dropbox e outros apps de nuvem."),
        ("Meu arquivo não foi reconhecido. E agora?",
         "Abra **📂 Arquivos lidos** para ver o motivo. Se o banco oferecer, tente outro formato "
         "(OFX ou CSV costumam funcionar melhor que PDF). Se não der certo, fale com a gente "
         "pelo botão abaixo e diga qual é o banco e o formato. **Não envie o extrato.**"),
        ("Meus dados ficam guardados?",
         "Não. Os extratos ficam só na memória enquanto o app está aberto e são apagados ao "
         "fechar. O que fica guardado são as classificações que você salvar (nome da empresa → "
         "categoria), sem valores nem datas."),
        ("Uma categoria está errada.",
         "Em **📋 Transações** ficam os Pix para empresas que o app classificou pela Receita "
         "(CNPJ), para conferir e mudar. No Plus, a "
         "página **⭐ Classificar** corrige qualquer fornecedor e o app lembra nas próximas vezes."),
        ("Como funciona o código Plus?",
         "Depois do pagamento, você recebe um código pelo WhatsApp ou e-mail. No menu lateral, "
         "abra **⭐ Tenho um código Plus**, cole o código e digite o nome completo do titular, "
         "igual ao informado na compra. O código vale até a data de validade."),
        ("Meu código não funciona ou venceu.",
         "Confira se o nome está igual ao informado na compra (acentos e maiúsculas não "
         "importam). Se venceu, renove pelo botão **⭐ Assinar área Plus**. Não há cobrança "
         "automática: o acesso simplesmente termina na data."),
    ]
    for pergunta, resposta in duvidas:
        with st.expander(pergunta):
            st.markdown(resposta)
    st.markdown("**Ainda com dúvida ou encontrou um problema?** Fale com a gente pelo "
                "WhatsApp ou por e-mail:")
    c1, c2, c3 = st.columns(3)
    if LINK_CONSULTORIA:
        c1.link_button("📱 WhatsApp", _whatsapp_com_texto(
            LINK_CONSULTORIA, "Olá! Tenho uma dúvida sobre o Contas em Dia:"))
    if EMAIL_CONTATO:
        botoes_email((c2, c3), "Contas em Dia - problema",
                     "O que eu estava fazendo:\n\nO que aconteceu:\n\nBanco e formato do "
                     "arquivo (ex.: Nubank, PDF):\n\n(Por segurança, não anexe extratos.)")
    st.caption(PRAZO_RESPOSTA)
st.session_state.setdefault("plus", False)
# O acesso vence durante o uso se o dia acabar
if st.session_state["plus"] and st.session_state.get("plus_ate") \
        and st.session_state["plus_ate"] < hoje_brasil():
    st.session_state["plus"] = False
    st.session_state["aviso_plus"] = (f"Seu acesso Plus venceu em "
                                      f"{st.session_state['plus_ate']:%d/%m/%Y}.")

with st.sidebar:
    st.markdown('<p class="secao">⭐ Plus</p>', unsafe_allow_html=True)
    if st.session_state["plus"]:
        ate = st.session_state.get("plus_ate")
        st.markdown("⭐ **Plus ativo**" + (f" até {ate:%d/%m/%Y}" if ate else ""))
        if st.session_state.get("plus_titular"):
            st.caption(f"Titular: {st.session_state['plus_titular']}")
        if st.button("Sair do Plus"):
            st.session_state["plus"] = False
            st.rerun()
    else:
        if st.session_state.get("aviso_plus"):
            st.warning(st.session_state["aviso_plus"])
        with st.expander("⭐ Tenho um código Plus",
                         expanded=bool(st.session_state.get("aviso_plus"))):
            with st.form("form_plus", border=False):
                codigo = st.text_input("Código de acesso", type="password")
                nome_plus = st.text_input(
                    "Nome completo do titular",
                    help="O mesmo nome informado na compra, como aparece no seu extrato. O "
                         "Plus vale para os extratos dessa pessoa.")
                if st.form_submit_button("Entrar"):
                    erro = entrar_no_plus(codigo, nome_plus)
                    if erro:
                        st.error(erro)
                    else:
                        st.session_state.pop("aviso_plus", None)
                        st.rerun()
            if st.button("Quero o Plus" if not st.session_state.get("aviso_plus")
                         else "Renovar o Plus", key="assinar_lateral"):
                abrir_assinatura()
PLUS = st.session_state["plus"]

# ============================================================================
# ADMINISTRAÇÃO (endereço do app + ?admin=1): gerar códigos Plus
# ============================================================================
def pagina_admin():
    st.subheader("🔧 Administração · Códigos Plus")
    senha_certa = ler_segredo("ADMIN_SENHA") or ""
    if not senha_certa:
        st.info("Para usar esta página, crie o segredo ADMIN_SENHA (uma senha forte) em "
                "Settings → Secrets do app.")
        return
    if not st.session_state.get("admin_ok"):
        with st.form("form_admin", border=False):
            senha = st.text_input("Senha de administrador", type="password")
            if st.form_submit_button("Entrar"):
                if hmac.compare_digest(senha.encode(), senha_certa.encode()):
                    st.session_state["admin_ok"] = True
                    st.rerun()
                st.error("Senha incorreta.")
        return
    if st.button("Sair da administração"):
        st.session_state["admin_ok"] = False
        st.rerun()
    if not CHAVE_PLUS:
        st.warning("Falta a chave que assina os códigos. Em Settings → Secrets, acrescente a "
                   "linha abaixo (gerada agora, aleatória) e salve. Não troque essa chave "
                   "depois: os códigos já vendidos deixariam de valer.")
        st.code(f'PLUS_CHAVE = "{secrets.token_urlsafe(32)}"', language="toml")
        return

    st.markdown("#### Gerar código")
    st.caption("Depois que o pagamento cair: informe o nome completo do titular (como aparece "
               "no extrato dele) e a validade.")
    with st.form("form_gerar"):
        nome = st.text_input("Nome completo do titular")
        prazo = st.radio("Validade", ["30 dias", "3 meses", "1 ano", "Escolher a data"],
                         horizontal=True)
        data_escolhida = st.date_input("Data (se escolher a data)",
                                       value=hoje_brasil() + timedelta(days=30),
                                       format="DD/MM/YYYY")
        gerar = st.form_submit_button("Gerar código", type="primary")
    if gerar:
        dias = {"30 dias": 30, "3 meses": 92, "1 ano": 366}.get(prazo)
        validade = hoje_brasil() + timedelta(days=dias) if dias else data_escolhida
        try:
            codigo = codigos.gerar_codigo(CHAVE_PLUS, nome, validade)
        except ValueError as e:
            st.error(str(e).capitalize())
        else:
            nome = " ".join(nome.split())
            st.success(f"Código de {nome}, válido até {validade:%d/%m/%Y}:")
            st.code(codigo, language=None)
            st.markdown("**Mensagem pronta para enviar:**")
            st.code(f"Olá, {nome.split()[0]}! Seu acesso ao Contas em Dia Plus está "
                    f"liberado até {validade:%d/%m/%Y}.\n\nCódigo: {codigo}\n\nNo app, "
                    "abra o menu lateral → ⭐ Tenho um código Plus, cole o código e digite "
                    f"seu nome completo: {nome}", language=None)
            st.markdown("**Para o seu controle** (cole numa planilha; o app não guarda):")
            st.code(f"{hoje_brasil():%d/%m/%Y};{nome};{codigo.split('-')[2]};"
                    f"{validade:%d/%m/%Y};{codigo}", language=None)

    st.markdown("#### Conferir um código")
    with st.form("form_conferir"):
        c1, c2 = st.columns(2)
        cod = c1.text_input("Código")
        nom = c2.text_input("Nome completo do titular")
        if st.form_submit_button("Conferir"):
            r = codigos.validar_codigo(CHAVE_PLUS, cod, nom, hoje=hoje_brasil(),
                                       bloqueados=set(_lista_segredo("PLUS_BLOQUEADOS")))
            if r["ok"]:
                st.success(f"Válido até {r['validade']:%d/%m/%Y} (identificação {r['ident']}).")
            else:
                st.error(r["motivo"])

    st.markdown("#### Cancelar um código")
    st.caption("Para cancelar antes do vencimento (estorno, uso indevido), acrescente a "
               "identificação do código (as 4 letras do meio, ex.: K7Q2) ao segredo "
               "PLUS_BLOQUEADOS, separadas por vírgula: PLUS_BLOQUEADOS = \"K7Q2, AB3D\"")


if st.query_params.get("admin") == "1":
    pagina_admin()
    st.stop()

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


def botoes_flutuantes():
    """Assinar o Plus e falar com um especialista: sempre à vista, no canto da tela."""
    botoes = []
    if not PLUS and (LINK_ASSINATURA or LINK_CONSULTORIA or EMAIL_CONTATO):
        # Botão do Streamlit (abre a janela de assinatura sem recarregar a página nem perder
        # os extratos enviados), fixado no canto pelo CSS de .st-key-assinar_flutuante
        with st.container(key="assinar_flutuante"):
            if st.button("⭐ Assinar área Plus", key="assinar_canto"):
                abrir_assinatura()
        if not LINK_CONSULTORIA:
            st.markdown("<style>.st-key-assinar_flutuante {bottom: 1.2rem !important;}</style>",
                        unsafe_allow_html=True)
    if LINK_CONSULTORIA:
        falar = _whatsapp_com_texto(LINK_CONSULTORIA, "Olá! Quero falar com um especialista "
                                                      "financeiro/contábil.")
        botoes.append(f'<a class="whats" href="{escape(falar)}" target="_blank" rel="noopener">'
                      f'{ICONE_WHATSAPP}<span class="longo">Falar com um especialista financeiro/contábil'
                      '</span><span class="curto">Falar com especialista</span></a>')
    if botoes:
        st.markdown(f'<div class="flutuantes">{"".join(botoes)}</div>', unsafe_allow_html=True)


# O conteúdo vai num container e o rodapé é desenhado logo depois: assim ele aparece
# embaixo de qualquer página, e também quando a tela para antes (st.stop)
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
        # No celular, arquivo escolhido direto do Google Drive (sem estar baixado) falha no envio,
        # antes de chegar ao app: o "!" vermelho no arquivo
        if NO_CELULAR:
            st.info(DICA_DRIVE, icon="📱")
        st.markdown("""
        ## 🚀 Como usar
        1. No app ou no site do banco, baixe o **extrato** da conta (CSV, Excel ou OFX) ou
           a **fatura do cartão**. Pode enviar vários meses e várias contas de uma vez.
        2. Arraste os arquivos para a área acima, ou clique em **Escolher arquivos**.
           Também dá para usar o menu lateral (📁 Seus extratos).
        3. Em PDF: extratos da conta Nubank, Sicredi e XP, e fatura do cartão BB. Se mandar
           o mesmo mês em mais de um formato, as repetições são descartadas
        4. Pronto: veja o resumo, o mês a mês e as transações já separadas por categoria

        **Movimentações internas** (aplicação/resgate automático, transferência entre
        suas contas e pagamento de fatura do cartão) não contam como entrada nem saída.
        """)
        with st.expander("❓ Dúvidas frequentes e contato"):
            secao_ajuda()
        st.stop()

    # Logo abaixo do título: a faixa verde e o aviso dos arquivos não importados; depois, os
    # filtros, junto dos gráficos. Preenchidos depois de ler os extratos
    faixas = st.container()
    barra_topo = st.container()
    tabelas = []
    leitura = []
    ids_lidos, colunas_usadas = [], []   # identificam o que foi lido, para a memória
    titulares = []   # nome do titular, quando o PDF traz (Sicredi, XP)
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


    def eh_zip(nome, conteudo):
        """.zip pelo nome ou, sem extensão, pelo conteúdo (o Excel .xlsx também é zip por
        dentro, mas tem o [Content_Types].xml)."""
        if nome.lower().endswith(".zip"):
            return True
        if "." in nome.rsplit("/", 1)[-1] or conteudo[:4] != b"PK\x03\x04":
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                return "[Content_Types].xml" not in z.namelist()
        except zipfile.BadZipFile:
            return False

    expandidos = []
    for arquivo in arquivos:
        if eh_zip(arquivo.name, arquivo.getvalue()):
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
            conteudo = arquivo.getvalue()
            id_arquivo = impressao(arquivo.name, conteudo)
            r = na_sessao("arquivo", id_arquivo,
                          lambda: carregar_arquivo(arquivo.name, conteudo), guardar=400)
            r["id"] = id_arquivo
            ids_lidos.append(id_arquivo)
        except SemLancamentos as e:
            leitura.append({"Arquivo": arquivo.name, "Conta": e.conta, "Situação": f"➖ {e}"})
            continue
        except Exception as e:
            leitura.append({"Arquivo": arquivo.name, "Conta": "—", "Situação": f"⚠️ ignorado: {e}"})
            continue
        r["nome"] = arquivo.name
        if r.get("titular"):
            titulares.append(r["titular"])
        if r["tipo"] == "transacoes":
            tabelas.append(r["dados"])
            leitura.append({"Arquivo": arquivo.name, "Conta": r["conta"],
                            "Situação": f"✅ {len(r['dados'])} lançamentos"})
        else:
            layouts.setdefault(tuple(r["bruto"].columns), []).append(r)

    def colunas_de(sugestao):
        return {"data": sugestao["data"], "descricao": sugestao["descricao"],
                "valor": None if sugestao["credito"] else sugestao["valor"],
                "credito": sugestao["credito"], "debito": sugestao["debito"]}

    def montar(r, colunas):
        return na_sessao("colunas", (r["id"], repr(sorted(colunas.items()))),
                         lambda: montar_transacoes(r["bruto"], colunas, r["conta"]),
                         guardar=400)

    # Primeiro só identifica as colunas de cada formato de planilha; quem precisa de ajuda
    # vai para o aviso amarelo, ao lado da faixa verde
    grupos = []
    for cols, grupo in layouts.items():
        sugestao = detectar_colunas(grupo[0]["bruto"])
        completo = bool(sugestao["data"] and sugestao["descricao"]
                        and (sugestao["valor"] or sugestao["credito"]))
        if completo:
            try:
                montar(grupo[0], colunas_de(sugestao))
            except ValueError:
                completo = False
        grupos.append((cols, grupo, sugestao, completo))
    nao_lidos = [x for x in leitura if x["Situação"].startswith("⚠️")]
    a_ajustar = [g for g in grupos if not g[3]]
    qtd_aviso = len(nao_lidos) + sum(len(g[1]) for g in a_ajustar)
    with faixas:
        if qtd_aviso:
            lugar_verde, lugar_amarelo = st.columns([1.6, 1], gap="small")
        else:
            lugar_verde, lugar_amarelo = st.container(), None
    detalhes_aviso = None
    if lugar_amarelo:
        with lugar_amarelo, st.container(key="faixa_aviso"):
            a1, a2 = st.columns([2, 1], vertical_alignment="center")
            a1.markdown(f"⚠️ {qtd_aviso} arquivo(s) não importado(s)")
            detalhes_aviso = a2.popover("Ver detalhes", type="tertiary")
        with detalhes_aviso:
            if nao_lidos:
                st.markdown("**Não foi possível ler**")
                # Mesmo motivo para vários arquivos (ex.: 30 XMLs de nota) numa linha só
                motivos = (pd.DataFrame(nao_lidos).groupby("Situação", sort=False)["Arquivo"]
                           .agg(lambda a: a.iat[0] if len(a) == 1 else
                                f"{len(a)} arquivos ({', '.join(a.head(2))}...)")
                           .reset_index())
                st.dataframe(motivos[["Arquivo", "Situação"]], hide_index=True, width=760)
            if a_ajustar:
                st.markdown("**Colunas não reconhecidas** · indique onde estão a data, a "
                            "descrição e o valor")

    for n, (cols, grupo, sugestao, completo) in enumerate(grupos):
        bruto0 = grupo[0]["bruto"]
        opcoes = ["—"] + list(cols)

        def indice(coluna):
            return opcoes.index(coluna) if coluna in opcoes else 0

        colunas = colunas_de(sugestao)
        # Só pede ajuda quando as colunas não foram reconhecidas
        if not completo:
            with detalhes_aviso, st.expander(
                    f"⚙️ {grupo[0]['conta']} ({len(grupo)} arquivo(s))"):
                st.caption(", ".join(r["nome"] for r in grupo))
                c1, c2 = st.columns(2)
                col_data = c1.selectbox("Data", opcoes, index=indice(sugestao["data"]),
                                        key=f"data{n}")
                col_desc = c2.multiselect("Descrição", list(cols),
                                          default=sugestao["descricao"],
                                          help="Pode escolher mais de uma coluna; o texto é "
                                               "juntado.", key=f"desc{n}")
                modo = st.radio("Como o banco mostra os valores?",
                                ["Uma coluna de valor (negativo = saída)",
                                 "Colunas separadas de crédito e débito"],
                                index=1 if sugestao["credito"] else 0, horizontal=True,
                                key=f"modo{n}")
                if modo.startswith("Uma"):
                    col_valor = st.selectbox("Valor", opcoes, index=indice(sugestao["valor"]),
                                             key=f"valor{n}")
                    col_cred = col_deb = "—"
                else:
                    c3, c4 = st.columns(2)
                    col_cred = c3.selectbox("Crédito (entradas)", opcoes,
                                            index=indice(sugestao["credito"]), key=f"cred{n}")
                    col_deb = c4.selectbox("Débito (saídas)", opcoes,
                                           index=indice(sugestao["debito"]), key=f"deb{n}")
                    col_valor = "—"
                st.dataframe(bruto0.head(5), width=620)
            colunas = {k: (None if v == "—" else v) for k, v in
                       {"data": col_data, "valor": col_valor,
                        "credito": col_cred, "debito": col_deb}.items()}
            colunas["descricao"] = col_desc
        colunas_usadas.append(repr(sorted(colunas.items())))
        for r in grupo:
            try:
                t = montar(r, colunas)
                tabelas.append(t)
                leitura.append({"Arquivo": r["nome"], "Conta": r["conta"],
                                "Situação": f"✅ {len(t)} lançamentos"})
            except ValueError as e:
                leitura.append({"Arquivo": r["nome"], "Conta": r["conta"],
                                "Situação": f"⚠️ {e} (ajuste em ⚠️ Ver detalhes)"})

    # Sem o nome digitado, usa o titular que veio no extrato (para achar as transferências
    # entre as próprias contas)
    titular_plus = st.session_state.get("plus_titular", "") if PLUS else ""
    titular_usado = (nome_titular.strip() or titular_plus
                     or (titulares[0] if titulares else ""))
    if not nome_titular.strip() and titulares:
        st.caption(f"👤 Titular identificado no extrato: **{titulares[0]}**. As transferências "
                   "para esse nome em outro banco contam como movimentação entre suas contas.")
    # O código Plus vale para um titular: extratos de outra pessoa (quando o PDF traz o nome)
    # ficam fora das análises do Plus
    outros_titulares = sorted({t for t in titulares
                               if titular_plus and not codigos.mesmo_titular(titular_plus, t)})
    if outros_titulares:
        PLUS = False
        st.error(f"Seu código Plus é de **{titular_plus}**, mas há extrato de outra pessoa "
                 f"({', '.join(outros_titulares)}). Para usar o Plus, envie só os seus "
                 "extratos. As análises gratuitas continuam disponíveis.", icon="🔒")
    if len({chave_fornecedor(x) for x in titulares}) > 1:
        st.info("Os extratos enviados são de titulares diferentes.", icon="ℹ️")
    # Regras lembradas (compartilhadas + pessoais) vencem as palavras-chave
    regras_comp = regras_compartilhadas(st.session_state["versao_regras"])
    regras_todas = juntar(juntar(juntar(regras_comp, regras_privadas),
                                 st.session_state["regras_sessao"]),
                          st.session_state["regras_pessoais"])
    chave_todos = impressao(ids_lidos, colunas_usadas, titular_usado, regras_todas)
    todos = na_sessao("todos", chave_todos,
                      lambda: aplicar_regras(consolidar(tabelas, titular_usado), regras_todas))

    # Pix para empresas sem categoria: o CNPJ da descrição é consultado na Receita (dados
    # públicos) e a categoria vem da atividade principal (CNAE), sem precisar pedir. Vale até
    # fechar o app; em 📋 Transações dá para conferir e mudar
    tentados = st.session_state.setdefault("cnpj_tentados", set())
    novos = cnpjs_pendentes(todos, regras_todas)
    novos = novos[~novos["CNPJ"].isin(tentados)].head(MAX_CNPJ_POR_VEZ)
    if not novos.empty:
        with st.spinner(f"🔎 Consultando {len(novos)} CNPJ(s) na Receita para classificar os "
                        "Pix para empresas..."):
            with ThreadPoolExecutor(max_workers=6) as ex:
                infos = list(ex.map(consultar_cnpj_cache_sem_contexto, novos["CNPJ"]))
        regras_auto, linhas = [], []
        for r, info in zip(novos.itertuples(), infos):
            tentados.add(r.CNPJ)
            sugestao = categoria_do_cnae(info["cnae"]) if info else None
            categoria, sub_ = sugestao if sugestao else (CATEGORIA_PADRAO, SUB_NAO_IDENTIFICADO)
            validas = subcategorias_de(categoria)
            sub_ = sub_ if sub_ in validas else validas[-1]
            nome = (info["nome"] if info and info["nome"] else r.Fornecedor)
            if sugestao:
                regras_auto.append(nova_regra(r.chave, nome, categoria, sub_, "cnpj", r.CNPJ,
                                              info["cnae"]))
            linhas.append({
                "chave": r.chave, "Fornecedor": r.Fornecedor, "CNPJ": r.CNPJ,
                "Nome na Receita": info["nome"] if info else "(não encontrado)",
                "Atividade principal (CNAE)":
                    f"{info['cnae']} · {info['atividade']}" if info else "",
                "Categoria": categoria, "Subcategoria": sub_,
                "cnae": info["cnae"] if info else "", "mei": bool(info and info["mei"]),
                "Situação": ("✅ classificado" if sugestao else
                             "atividade sem categoria" if info else "não encontrado na Receita"),
            })
        st.session_state["cnpj_auto"] = pd.concat(
            [st.session_state.get("cnpj_auto", pd.DataFrame()), pd.DataFrame(linhas)],
            ignore_index=True)
        if regras_auto:
            st.session_state["regras_sessao"] = juntar(st.session_state["regras_sessao"],
                                                       pd.concat(regras_auto))
            st.session_state["aviso_cnpj"] = (
                f"🔎 {len(regras_auto)} fornecedor(es) classificado(s) pela atividade na Receita "
                "(CNPJ). Confira ou mude em 📋 Transações.")
            st.rerun()
    if st.session_state.get("aviso_cnpj"):
        st.toast(st.session_state.pop("aviso_cnpj"))

    if todos.empty:
        st.warning("Nenhuma transação encontrada. Confira os arquivos e as colunas em "
                   "⚠️ Ver detalhes.")
        st.dataframe(pd.DataFrame(leitura), hide_index=True, width="stretch")
        st.stop()

    # Menu lateral: as páginas da área aberta ou do Plus
    PAINEL = "📊 Painel"
    PAGINAS = [PAINEL, "📅 Mês a mês", "📋 Transações", "📥 Download"]
    PAGINAS += (["⭐ Relatório", "⭐ Imposto de Renda", "⭐ Fixos e parcelas",
                 "⭐ Saúde financeira", "⭐ Classificar"] if PLUS
                else ["⭐ Área Plus"]) + ["❓ Ajuda"]
    with menu_lateral:
        st.markdown('<p class="secao">🧭 Navegação</p>', unsafe_allow_html=True)
        with st.container(key="menu"):
            pagina = st.radio("Navegação", PAGINAS, label_visibility="collapsed",
                              key="pagina_plus" if PLUS else "pagina_livre",
                              persist_state="page", width="stretch")

    def escolher_categorias(opcoes, nome, rotulo):
        """Pílulas para escolher categorias ou contas (todas marcadas no início). A chave
        muda quando as opções mudam (uma reclassificação), e a escolha recomeça."""
        chave = f"pilulas_{nome}_{abs(hash(tuple(opcoes)))}"
        # Marcar/Desmarcar todas mudam o valor pela sessão; aí o default não pode vir junto
        st.session_state.setdefault(chave, list(opcoes))
        with st.container(key=f"todos_nenhum_{nome}", horizontal=True, gap="small",
                          vertical_alignment="bottom"):
            escolhidas = st.pills(rotulo, opcoes, selection_mode="multi", key=chave,
                                  persist_state="page", width="content")
            st.button("Marcar todas", key=f"todas_{nome}", type="tertiary",
                      on_click=lambda: st.session_state.update({chave: list(opcoes)}))
            st.button("Desmarcar todas", key=f"nenhuma_{nome}", type="tertiary",
                      on_click=lambda: st.session_state.update({chave: []}))
        return escolhidas

    # Barra do topo: título da página (ou as visões do Painel), período e filtros
    contas = sorted(todos["Conta"].unique())
    inicio, fim = todos["Data"].min().date(), todos["Data"].max().date()
    # Filtros juntos: visão do Painel (ou o nome da página), Área Plus e período numa linha;
    # embaixo, as contas e (em Entradas e Saídas) as categorias, do mesmo jeito
    with barra_topo:
        with st.container(key="barra_filtros", horizontal=True, vertical_alignment="center",
                          gap="small"):
            if pagina == PAINEL:
                with st.container(key="visoes", width="content"):
                    visao = st.segmented_control("Visão", ["Resumo", "Entradas", "Saídas"],
                                                 default="Resumo", required=True,
                                                 label_visibility="collapsed", key="visao",
                                                 persist_state="page")
            else:
                st.markdown(f'<p class="titulo-pagina">{escape(pagina)}</p>',
                            unsafe_allow_html=True, width="content")
            if not PLUS and pagina != "⭐ Área Plus":
                with st.container(key="ir_plus", width="content"):
                    st.button("⭐ Área Plus", key="botao_ir_plus",
                              on_click=lambda: st.session_state.update(
                                  pagina_livre="⭐ Área Plus"))
            with st.container(key="periodo", width=270):
                periodo_sel = st.date_input("📅 Período", value=(inicio, fim),
                                            min_value=inicio, max_value=fim,
                                            format="DD/MM/YYYY", label_visibility="collapsed",
                                            key="periodo_sel", persist_state="page")
        filtro_contas = escolher_categorias(contas, "contas", "Contas")

    df = todos[todos["Conta"].isin(filtro_contas)]
    if isinstance(periodo_sel, tuple) and len(periodo_sel) == 2:
        df = df[(df["Data"].dt.date >= periodo_sel[0]) & (df["Data"].dt.date <= periodo_sel[1])]
    if df.empty:
        st.warning("Escolha ao menos uma conta." if not filtro_contas
                   else "Nenhuma transação com esses filtros.")
        st.stop()

    # Identifica os dados na tela (extratos, regras, contas e período), para a memória
    chave_filtros = (chave_todos, tuple(filtro_contas), str(periodo_sel))
    internas = df[df["Tipo"] == "Interna"]
    periodo = f"{df['Data'].min():%d/%m/%Y} a {df['Data'].max():%d/%m/%Y}"
    with lugar_verde, st.container(key="faixa_ok"):
        f1, f2 = st.columns([3, 1.2], vertical_alignment="center")
        f1.markdown(f"✅ {len(df) - len(internas)} transações de {periodo}",
                    help=f"{len(internas)} movimentações internas (aplicações, transferências "
                         "entre suas contas, pagamento de fatura) ficam à parte.")
        with f2.popover(f"📂 Arquivos lidos ({len(arquivos)})", type="tertiary"):
            st.dataframe(pd.DataFrame(leitura), hide_index=True, width=620)
    # Erro que só apareceu ao montar com as colunas escolhidas (fora do aviso amarelo)
    novos_erros = [x["Arquivo"] for x in leitura if x["Situação"].startswith("⚠️")
                   and x not in nao_lidos]
    if novos_erros and not a_ajustar:
        st.warning(f"Não foi possível ler: {', '.join(novos_erros)}. Veja em 📂 Arquivos lidos.",
                   icon="⚠️")

    entradas = df.loc[df["Tipo"] == "Entrada", "Valor"].sum()
    saidas = -df.loc[df["Tipo"] == "Saída", "Valor"].sum()
    aplicado = -internas.loc[internas["Categoria"] == CATEGORIA_APLICACAO, "Valor"].sum()
    meses = max(1, df["Mês"].nunique())
    varios_meses = df["Mês"].nunique() > 1

    # Entradas agrupadas por tipo (recebido de empresas, de pessoas, salário...)
    df_entradas = df[df["Tipo"] == "Entrada"].assign(
        Categoria=lambda d: d["Subcategoria"].replace("", "Outras entradas"), Subcategoria="")
    tipos_entrada = resumo_categorias(df_entradas, tipo="Entrada")
    cats = resumo_categorias(df)

    # Recorrentes, parcelas e IR olham todo o histórico das contas escolhidas (o filtro
    # de período cortaria parcelas e meses); a saúde financeira segue o período
    df_contas = todos[todos["Conta"].isin(filtro_contas)]
    chave_contas = (chave_todos, tuple(filtro_contas))
    recorrentes = na_sessao("recorrentes", chave_contas,
                            lambda: plus.gastos_recorrentes(df_contas))
    parcelas, cronograma = na_sessao("parcelas", chave_contas,
                                     lambda: plus.parcelas_futuras(df_contas))
    compromissos = plus.compromissos_mensais(recorrentes)
    parcelas_proximo = float(cronograma["Valor"].iloc[0]) if not cronograma.empty else 0.0
    anos_ir = sorted(df_contas["Data"].dt.year.unique(), reverse=True)

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

    def cartoes_kpi(itens):
        """Os 4 cartões do alto: (ícone, título, valor, nota, classe do valor, dica)."""
        html = ['<div class="kpis-caixa"><div class="kpis">']
        for icone, titulo, valor, nota, classe, ajuda in itens:
            html.append(f'<div class="kpi" title="{escape(ajuda)}"><div class="rot">'
                        f'<span class="ico">{icone}</span>{escape(titulo)}</div>'
                        f'<div class="val {classe}">{escape(valor)}</div>'
                        f'<div class="nota">{escape(nota)}</div></div>')
        st.markdown("".join(html + ["</div></div>"]), unsafe_allow_html=True)

    def por_mes(n):
        return f"{n} {'mês' if n == 1 else 'meses'}"

    def titulo_painel(titulo, tag):
        st.markdown(f'<div class="titulo-painel">{titulo}<span class="tag">{tag}</span></div>',
                    unsafe_allow_html=True)

    def painel_ciano(titulo, subtitulo, tabela, tipo, n=8):
        """Painel em degradê ciano, à direita, com o ranking."""
        with st.container(key="painel_ciano"):
            st.markdown(f"### {titulo}")
            st.markdown(f'<div class="sub-titulo">{subtitulo}</div>', unsafe_allow_html=True)
            if tabela.empty:
                st.caption("Nada no período.")
            else:
                st.markdown(ranking_html(tabela, tipo, n=n), unsafe_allow_html=True)

    def linhas_por_mes(dados, rotulo, com_total=True):
        """Uma linha por categoria escolhida (as 7 maiores; o resto em "Outros") e, se
        com_total, o total, mês a mês."""
        longo = (dados.assign(Valor=dados["Valor"].abs())
                 .groupby(["Mês", "Categoria"], as_index=False)["Valor"].sum()
                 .rename(columns={"Categoria": "Fornecedor"}))
        st.altair_chart(grafico_linhas(longo, "Total", max_series=7, rotulo=rotulo,
                                       altura=420 if com_total else 380,
                                       largura_nomes=170, com_total=com_total),
                        width="stretch")
        dica("Passe o mouse sobre o gráfico para ver os valores de cada mês")

    # ----------------------------------------------------------------------------
    if pagina == PAINEL and visao == "Resumo":
        esq, dir_ = st.columns([3, 1.3], gap="medium")
        with esq:
            saldo = entradas - saidas
            cartoes_kpi([
                ("💰", "Entradas", formatar_reais(entradas),
                 f"média de {formatar_reais(entradas / meses)} por mês", "", ""),
                ("💸", "Saídas", formatar_reais(saidas),
                 f"média de {formatar_reais(saidas / meses)} por mês", "", ""),
                ("⚖️", "Saldo do período", formatar_reais(saldo),
                 "sobrou no período" if saldo >= 0 else "faltou no período",
                 "" if saldo >= 0 else "neg", ""),
                ("🏦", "Aplicado (líquido)", formatar_reais(aplicado), "aplicações menos resgates",
                 "", "Aplicações menos resgates no período (Rende Fácil, caixinhas, fundos...). "
                     "Não entra em entradas nem saídas."),
            ])
            with st.container(border=True):
                titulo_painel("Entrou e saiu", "mês a mês")
                st.altair_chart(grafico_mensal(resumo_mensal(df)), width="stretch")
                dica("Passe o mouse sobre os pontos para ver o valor completo")
            with st.container(border=True):
                titulo_painel("De onde vem", "tipos de entrada")
                if tipos_entrada.empty:
                    st.info("Não há entradas no período.")
                else:
                    st.markdown(ranking_html(tipos_entrada, "Entrada"), unsafe_allow_html=True)
                dica("Os detalhes, com quem pagou, estão em Entradas (logo acima)")
        with dir_:
            painel_ciano("Para onde vai", "Maiores categorias de gasto", cats, "Saída")

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
    if pagina == PAINEL and visao == "Entradas":
        if tipos_entrada.empty:
            st.info("Não há entradas no período.")
        else:
            sel = escolher_categorias(tipos_entrada["Categoria"].tolist(), "entradas",
                                      "Tipos de entrada")
            df_e = df_entradas[df_entradas["Categoria"].isin(sel)]
            if df_e.empty:
                st.info("Escolha ao menos um tipo de entrada.")
            else:
                tipos_sel = resumo_categorias(df_e, tipo="Entrada")
                total_e = df_e["Valor"].sum()
                fontes = df_e.assign(_k=df_e["Fornecedor"].map(chave_fornecedor))
                por_fonte = fontes.groupby("_k")["Valor"].sum().sort_values(ascending=False)
                esq, dir_ = st.columns([3, 1.3], gap="medium")
                with esq:
                    cartoes_kpi([
                        ("💰", "Total de entradas", formatar_reais(total_e),
                         "nos tipos escolhidos", "", ""),
                        ("📅", "Média por mês", formatar_reais(total_e / meses), por_mes(meses),
                         "", ""),
                        ("👥", "Fontes diferentes", f"{len(por_fonte)}", "quem pagou", "", ""),
                        ("🎯", "Maior fonte",
                         f"{por_fonte.iloc[0] / total_e * 100:.0f}%".replace(".", ","),
                         "das entradas escolhidas", "ouro",
                         "Quanto das entradas veio de quem mais pagou. Quanto maior, mais você "
                         "depende de uma fonte só."),
                    ])
                    with st.container(border=True):
                        if varios_meses:
                            titulo_painel("Entradas", "por tipo e total, mês a mês")
                            linhas_por_mes(df_e, "Tipo")
                        else:
                            # Período de um mês só: não há linha mês a mês para desenhar
                            titulo_painel("Entradas",
                                          f"por tipo em {rotulo_mes(df['Mês'].iat[0])}")
                            st.altair_chart(grafico_categorias(tipos_sel, "Entrada"),
                                            width="stretch")
                            dica("Escolha um período de 2 meses ou mais para ver a evolução "
                                 "mês a mês")
                with dir_:
                    painel_ciano("De onde vem", "Tipos escolhidos", tipos_sel, "Entrada")
                with st.container(border=True):
                    titulo_painel("Quem pagou", "por tipo de entrada")
                    dica("Clique num tipo para ver quem mais pagou · nas linhas abertas, "
                         "o % é sobre o tipo")
                    st.markdown(na_sessao("detalhe", (chave_filtros, "Entrada", tuple(sel)),
                                          lambda: tabela_categorias_html(
                                              tipos_sel, df_e, tipo="Entrada",
                                              rotulo="Tipo de entrada")),
                                unsafe_allow_html=True)

    # ----------------------------------------------------------------------------
    if pagina == PAINEL and visao == "Saídas":
        if cats.empty:
            st.info("Não há saídas no período.")
        else:
            sel = escolher_categorias(cats["Categoria"].tolist(), "saidas", "Categorias")
            df_s = df[(df["Tipo"] == "Saída") & df["Categoria"].isin(sel)]
            if df_s.empty:
                st.info("Escolha ao menos uma categoria.")
            else:
                cats_sel = resumo_categorias(df_s)
                total_s = -df_s["Valor"].sum()
                fixos_sel = plus.compromissos_mensais(
                    recorrentes[recorrentes["Categoria"].isin(sel)])
                esq, dir_ = st.columns([3, 1.3], gap="medium")
                with esq:
                    cartoes_kpi([
                        ("💸", "Total de saídas", formatar_reais(total_s),
                         "nas categorias escolhidas", "", ""),
                        ("📅", "Média por mês", formatar_reais(total_s / meses), por_mes(meses),
                         "", ""),
                        ("🏠", "Maior categoria", cats_sel.iloc[0]["Categoria"].capitalize(),
                         f"{_pct(cats_sel.iloc[0]['% das saídas'])} das escolhidas", "ouro", ""),
                        ("🔁", "Contas que se repetem", formatar_reais(fixos_sel), "por mês", "",
                         "Assinaturas, mensalidades e contas mensais ainda ativas, nas "
                         "categorias escolhidas."),
                    ])
                    with st.container(border=True):
                        if varios_meses:
                            titulo_painel("Saídas", "por categoria, mês a mês")
                            linhas_por_mes(df_s, "Categoria", com_total=False)
                        else:
                            # Período de um mês só: não há linha mês a mês para desenhar
                            titulo_painel("Saídas",
                                          f"por categoria em {rotulo_mes(df['Mês'].iat[0])}")
                            st.altair_chart(grafico_categorias(cats_sel), width="stretch")
                            dica("Escolha um período de 2 meses ou mais para ver a evolução "
                                 "mês a mês")
                with dir_:
                    painel_ciano("Para onde vai", "Categorias escolhidas", cats_sel, "Saída")
                with st.container(border=True):
                    titulo_painel("Para quem foi", "categoria → subcategoria → fornecedor")
                    dica("Clique numa categoria para abrir as subcategorias e os maiores "
                         "fornecedores · nas linhas abertas, o % é sobre o grupo de cima")
                    st.markdown(na_sessao("detalhe", (chave_filtros, "Saída", tuple(sel)),
                                          lambda: tabela_categorias_html(cats_sel, df_s)),
                                unsafe_allow_html=True)

                sem_id = [nao_identificado(c, sc) for c, sc in
                          zip(df_s["Categoria"], df_s["Subcategoria"])]
                pct_sem_id = df_s.loc[sem_id, "Valor"].sum() / df_s["Valor"].sum() * 100
                if pct_sem_id > 20:
                    st.caption(f"ℹ️ {pct_sem_id:.0f}% das saídas não foram identificadas. "
                               + ("Classifique em ⭐ Classificar." if PLUS else
                                  "Pix para empresas são classificados pela Receita; "
                                  "confira em 📋 Transações."))

    # ----------------------------------------------------------------------------
    if pagina == "📅 Mês a mês":
        mensal = resumo_mensal(df)
        st.subheader("Entrou e saiu, mês a mês")
        dica("Passe o mouse sobre os pontos para ver o valor completo")
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
    if pagina == "📥 Download":
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
    # Pendentes: não identificados e transferências sem outra categoria
    saidas_forn["pendente"] = [c == "TRANSFERÊNCIA" or nao_identificado(c, sc) for c, sc in
                               zip(saidas_forn["Categoria"], saidas_forn["Subcategoria"])]
    def subcategoria_valida(categoria, sub):
        validas = subcategorias_de(categoria)
        return sub if sub in validas else validas[-1]

    def secao_cnpj(lembrar):
        """Os Pix para empresas que o app classificou sozinho pela Receita (CNPJ), para
        conferir e mudar. lembrar=True (Plus) também grava as regras para as próximas vezes."""
        if st.session_state.get("aviso_regras"):
            st.success(st.session_state.pop("aviso_regras"), icon="✅")
        auto = st.session_state.get("cnpj_auto")
        if auto is None or auto.empty:
            st.caption("Nenhum Pix para empresa (com CNPJ na descrição) ficou sem categoria.")
            return
        totais = -saidas_forn.groupby("chave")["Valor"].sum()
        tab = auto.assign(Total=auto["chave"].map(totais).fillna(0).map(formatar_reais),
                          Subcategoria=auto["Subcategoria"].replace("", SEM_SUB))
        ok = (auto["Situação"] == "✅ classificado").sum()
        st.markdown(f"**{ok} de {len(auto)} fornecedor(es) classificados automaticamente** pela "
                    "atividade principal na Receita Federal (dados públicos, BrasilAPI). Mude a "
                    "categoria se algum estiver errado.")
        editado = st.data_editor(
            tab, hide_index=True, width="stretch", key="editor_cnpj",
            column_order=["Fornecedor", "Nome na Receita", "Categoria", "Subcategoria", "Total",
                          "Situação", "Atividade principal (CNAE)"],
            disabled=["Fornecedor", "Nome na Receita", "Atividade principal (CNAE)", "Total",
                      "Situação"],
            column_config={
                "Categoria": st.column_config.SelectboxColumn(options=categorias_editaveis()),
                "Subcategoria": st.column_config.SelectboxColumn(options=todas_subs),
            })
        mudou = editado[(editado["Categoria"] != tab["Categoria"])
                        | (editado["Subcategoria"] != tab["Subcategoria"])]

        def regras_de(linhas):
            novas, pessoais_mei = [], []
            for _, r in linhas.iterrows():
                nome = r["Nome na Receita"] if not r["Nome na Receita"].startswith("(") \
                    else r["Fornecedor"]
                regra = nova_regra(r["chave"], nome, r["Categoria"],
                                   subcategoria_valida(r["Categoria"], r["Subcategoria"]),
                                   "cnpj", r["CNPJ"], r["cnae"])
                # MEI tem o nome da pessoa no CNPJ: não vai para o arquivo público
                (pessoais_mei if r["mei"] else novas).append(regra)
            return novas, pessoais_mei

        b1, b2, b3 = st.columns(3)
        if b1.button(f"✅ Aplicar {len(mudou)} alteração(ões)", disabled=mudou.empty):
            novas, pessoais_mei = regras_de(mudou)
            st.session_state["regras_sessao"] = juntar(st.session_state["regras_sessao"],
                                                       pd.concat(novas + pessoais_mei))
            atual = auto.copy()
            atual.loc[mudou.index, "Categoria"] = mudou["Categoria"]
            atual.loc[mudou.index, "Subcategoria"] = [
                subcategoria_valida(c, sc) for c, sc in zip(mudou["Categoria"],
                                                            mudou["Subcategoria"])]
            atual.loc[mudou.index, "Situação"] = "✏️ alterado por você"
            st.session_state["cnpj_auto"] = atual
            st.session_state["aviso_regras"] = (f"{len(mudou)} fornecedor(es) alterado(s) até "
                                                "você fechar o app")
            st.rerun()
        if lembrar:
            para_lembrar = editado[(editado["Situação"] != "atividade sem categoria")
                                   & (editado["Situação"] != "não encontrado na Receita")
                                   | editado.index.isin(mudou.index)]
            if b2.button(f"💾 Lembrar {len(para_lembrar)} nas próximas vezes",
                         disabled=para_lembrar.empty):
                novas, pessoais_mei = regras_de(para_lembrar)
                try:
                    salvar_regras(pd.concat(novas) if novas else regras_vazias(),
                                  pd.concat(pessoais_mei) if pessoais_mei else regras_vazias(),
                                  "CNPJ " + ", ".join(para_lembrar["Fornecedor"].head(5)))
                except Exception as e:
                    st.error(f"Não foi possível salvar as regras: {e}")
                    return
                st.rerun()
        falhas = auto[auto["Situação"] == "não encontrado na Receita"]
        if not falhas.empty and b3.button(f"🔄 Consultar de novo {len(falhas)} não "
                                          "encontrado(s)"):
            st.session_state["cnpj_tentados"] -= set(falhas["CNPJ"])
            st.session_state["cnpj_auto"] = auto.drop(falhas.index).reset_index(drop=True)
            st.rerun()

    # ----------------------------------------------------------------------------
    if pagina == "📋 Transações":
        # Revisão dos Pix para empresas que o app classificou sozinho pela Receita (CNPJ)
        auto = st.session_state.get("cnpj_auto")
        if auto is not None and not auto.empty:
            with st.expander(f"🔎 Pix para empresas classificados pela Receita ({len(auto)})"):
                st.markdown("Pix feitos a empresas trazem o CNPJ na descrição. Assim que você "
                            "envia os extratos, o app consulta a **atividade principal** da "
                            "empresa nos dados públicos da Receita Federal e já classifica. "
                            "Confira e mude o que quiser.")
                secao_cnpj(lembrar=PLUS)
                if not PLUS:
                    st.caption("🔒 Nada é guardado: as classificações valem até você fechar o "
                               "app. Para o app lembrar nas próximas vezes, use a versão "
                               "⭐ Plus.")
        f1, f2, f3 = st.columns([2, 2, 1])
        filtro_cat = f1.multiselect("Categoria", sorted(df["Categoria"].unique()),
                                    placeholder="Todas")
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

    if not PLUS:
        if pagina == "❓ Ajuda":
            secao_ajuda()

        if pagina == "⭐ Área Plus":
            st.markdown('<div class="vitrine"><h3>⭐ Contas em Dia Plus</h3>'
                        'Análises prontas a partir dos mesmos extratos. Seus extratos e '
                        'relatórios também não ficam guardados: ao fechar o app, tudo é apagado '
                        '(baixe as planilhas que quiser). Só as classificações que você salvar '
                        'são lembradas.</div>', unsafe_allow_html=True)
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
            - **⭐ Relatório completo em PDF** — 4 páginas em linguagem simples: sua nota
              geral, os destaques do período, para onde foi o dinheiro (categorias,
              subcategorias e maiores gastos), o que já está comprometido nos próximos meses,
              os pontos de atenção, a prévia do IR e os próximos passos sugeridos.
            - **⭐ Imposto de Renda** — despesas que possivelmente podem ser deduzidas (saúde,
              educação, PGBL, pensão) com o CNPJ de quem recebeu (caso seja localizável no
              extrato), e os rendimentos recebidos de empresas e de pessoas. Pronto para levar
              ao contador, em planilha.
            - **⭐ Fixos e parcelas** — o que se repete todo mês, a data prevista do
              próximo, e as parcelas do cartão que ainda faltam (quantas e quanto, mês a mês).
            - **⭐ Saúde financeira** — indicadores com semáforo: quanto sobra, meses no
              vermelho, dependência de uma fonte de renda, compromissos e reserva de emergência.
            - **⭐ Classificar** — corrija a categoria de qualquer fornecedor e o app lembra
              nas próximas vezes.
            """)
            st.download_button("📄 Ver um relatório de exemplo (PDF, dados fictícios)",
                               relatorio_de_exemplo(), "Relatorio_Contas_em_Dia_exemplo.pdf",
                               "application/pdf")
            st.markdown("**Como ter acesso:** faça o pagamento em *⭐ Assinar área Plus* e "
                        "receba seu código. Depois, no menu lateral, abra *⭐ Tenho um código "
                        "Plus*, cole o código e digite seu nome completo. O código vale para os "
                        "extratos do titular, até a data de validade.")
            b1, b2 = st.columns(2)
            if b1.button("⭐ Quero o Plus", type="primary", key="assinar_vitrine"):
                abrir_assinatura()
            if LINK_CONSULTORIA:
                b2.link_button("💬 Falar com um especialista", LINK_CONSULTORIA)
            if not LINK_ASSINATURA and not LINK_CONSULTORIA:
                st.caption("As assinaturas abrem em breve.")
        st.stop()

    if pagina == "❓ Ajuda":
        secao_ajuda()

    # ----------------------------------------------------------------------------
    if pagina == "⭐ Relatório":
        st.subheader("📄 Relatório Contas em Dia")
        st.markdown("""
        Um PDF de 4 páginas, para ler com calma, imprimir ou levar ao seu especialista:
        1. **Seu dinheiro em uma página** — nota geral, quanto entrou e saiu, destaques, o mês
           a mês e as aplicações
        2. **Para onde foi o dinheiro** — categorias, subcategorias e maiores gastos
        3. **O que já está comprometido** — próximos 3 meses, contas que se repetem e parcelas
        4. **Atenção, imposto e próximos passos** — indicadores, prévia do IR, sugestões e o
           que falta enviar para o relatório ficar mais completo
        """)
        st.caption(f"Usa as contas e o período escolhidos no menu lateral ({periodo}). A reserva "
                   "de emergência usa o valor informado na página ⭐ Saúde financeira.")
        def pdf_do_relatorio(t=df, guardado=st.session_state.get("guardado") or None):
            # Só roda no clique: o PDF é montado na hora e entregue para download
            return relatorio.gerar_pdf(relatorio.montar_relatorio(t, guardado=guardado))

        st.download_button("📥 Baixar relatório (PDF)", pdf_do_relatorio,
                           f"Relatorio_Contas_em_Dia_{datetime.now():%Y%m%d}.pdf",
                           "application/pdf", type="primary", on_click="ignore")
        st.caption("🔒 O relatório é montado na hora do clique, na memória, e não fica guardado.")

    # ----------------------------------------------------------------------------
    if pagina == "⭐ Imposto de Renda":
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
    if pagina == "⭐ Fixos e parcelas":
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
    if pagina == "⭐ Saúde financeira":
        guardado = st.number_input(
            "Quanto você tem guardado hoje, em reais? (opcional)", min_value=0, step=1000,
            key="guardado",
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
    if pagina == "⭐ Classificar":
        if st.session_state.get("aviso_regras"):
            st.success(st.session_state.pop("aviso_regras"), icon="✅")

        with st.expander("❓ Como funciona esta página", expanded=True):
            st.markdown("""
            Aqui **você mesmo** corrige a categoria dos gastos — direto na tabela. O app
            aprende e, nos próximos extratos, já classifica esse fornecedor sozinho.

            1. A tabela mostra cada **fornecedor** (por padrão, só os não identificados e as
               transferências). Desligue o botão acima da tabela para ver todos.
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
        so_pendentes = st.toggle("Mostrar só os não identificados e as transferências",
                                 value=True)

        grupo = (saidas_forn.groupby("chave")
                 .agg(Fornecedor=("Fornecedor", lambda v: max(v.unique(), key=len)),
                      Categoria=("Categoria", lambda v: v.mode().iat[0]),
                      Subcategoria=("Subcategoria", lambda v: v.mode().iat[0]),
                      Total=("Valor", lambda v: -v.sum()),
                      Transações=("Valor", "count"),
                      pendente=("pendente", "any"))
                 .sort_values("Total", ascending=False).reset_index())
        if so_pendentes:
            grupo = grupo[grupo["pendente"]].reset_index(drop=True)
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

        st.caption("🔎 Os Pix para empresas que o app classificou pela Receita (CNPJ) estão "
                   "em 📋 Transações, para conferir e lembrar.")

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
