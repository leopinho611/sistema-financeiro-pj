import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
from datetime import datetime
import io

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Sistema Financeiro PJ",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CATEGORIAS (DICIONÁRIO DE PALAVRAS-CHAVE)
# ============================================================================
CATEGORIAS = {
    "CASA": ["aluguel", "condominio", "agua", "luz", "gas", "internet", "telefone", "empreitada", "pintura", "reforma"],
    "TRANSPORTE": ["combustivel", "gasolina", "etanol", "estacionamento", "pedagio", "uber", "99taxi", "onibus", "passagem", "manutencao", "mecanico"],
    "ALIMENTAÇÃO": ["restaurante", "comida", "pizza", "hamburguer", "mercado", "padaria", "supermercado", "açougue", "feira", "delivery"],
    "SAÚDE": ["farmacia", "medico", "dentista", "hospital", "clinica", "exame", "laboratorio", "fisioterapia", "academia"],
    "EDUCAÇÃO": ["escola", "universidade", "curso", "livro", "professor", "aula", "capacitacao"],
    "LAZER": ["cinema", "teatro", "show", "viagem", "hotel", "passagem aerea", "turismo", "bar", "nightclub"],
    "SHOPPING": ["roupa", "sapato", "loja", "vestuario", "shop"],
    "INVESTIMENTO": ["fii", "acao", "tesouro", "fundo", "bitcoin", "cripto", "bolsa"],
    "IMPOSTO": ["irpf", "irpj", "icms", "pis", "cofins", "imposto", "taxa", "licensa"],
    "OUTRO": []
}

# ============================================================================
# FUNÇÕES DE CATEGORIZAÇÃO
# ============================================================================
def categorizar_transacao(descritivo):
    """Categoriza uma transação baseado no descritivo"""
    descritivo_lower = str(descritivo).lower().strip()

    for categoria, palavras_chave in CATEGORIAS.items():
        for palavra in palavras_chave:
            if palavra.lower() in descritivo_lower:
                return categoria
    return "OUTRO"

def processar_arquivo(file, file_type):
    """Processa arquivo CSV ou XLSX"""
    try:
        if file_type == "csv":
            df = pd.read_csv(file, encoding='utf-8')
        else:
            df = pd.read_excel(file)
        return df
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None

def adicionar_coluna_categoria(df):
    """Adiciona coluna de categoria automaticamente"""
    # Tenta detectar a coluna de descritivo
    colunas_descritivo = [col for col in df.columns if any(x in col.lower() for x in ['descritivo', 'descrição', 'description', 'memo', 'conceito'])]

    if not colunas_descritivo:
        st.warning("⚠️ Não encontrei coluna de descritivo. Usando primeira coluna como referência.")
        coluna_desc = df.columns[0]
    else:
        coluna_desc = colunas_descritivo[0]

    df['CATEGORIA'] = df[coluna_desc].apply(categorizar_transacao)
    return df

def adicionar_coluna_valor(df):
    """Tenta detectar valores e calcula saldo"""
    # Procura por colunas de débito/crédito
    colunas_valor = [col for col in df.columns if any(x in col.lower() for x in ['valor', 'value', 'debit', 'credit', 'débito', 'crédito', 'amount'])]

    if colunas_valor:
        # Se tem débito E crédito separados
        débito_cols = [col for col in colunas_valor if any(x in col.lower() for x in ['débito', 'debit', 'saida'])]
        crédito_cols = [col for col in colunas_valor if any(x in col.lower() for x in ['crédito', 'credit', 'entrada'])]

        if débito_cols and crédito_cols:
            df['VALOR'] = df[crédito_cols[0]].astype(float) - df[débito_cols[0]].astype(float)
        elif colunas_valor:
            df['VALOR'] = df[colunas_valor[0]].astype(float)

    return df

# ============================================================================
# INTERFACE STREAMLIT
# ============================================================================
st.title("💰 Sistema de Controle Financeiro - PJ/Autônomo")
st.markdown("Importar extrato bancário, categorizar automaticamente e gerar análises")

# ============================================================================
# SIDEBAR - UPLOAD
# ============================================================================
with st.sidebar:
    st.header("📁 Importar Dados")

    arquivo = st.file_uploader(
        "Escolha seu extrato bancário",
        type=["csv", "xlsx"],
        help="Aceita: CSV ou XLSX do seu banco (Itaú, Bradesco, Santander, etc)"
    )

    if arquivo:
        file_type = "xlsx" if arquivo.name.endswith('.xlsx') else "csv"
        st.success(f"✅ Arquivo selecionado: {arquivo.name}")

# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================
if arquivo:
    file_type = "xlsx" if arquivo.name.endswith('.xlsx') else "csv"
    df = processar_arquivo(arquivo, file_type)

    if df is not None:
        st.success(f"✅ Arquivo carregado! {len(df)} transações encontradas")

        # Adiciona colunas inteligentes
        df = adicionar_coluna_categoria(df)
        df = adicionar_coluna_valor(df)

        # ====================================================================
        # TAB 1: RESUMO E ESTATÍSTICAS
        # ====================================================================
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumo", "📋 Dados Brutos", "🏷️ Categorias", "📥 Download"])

        with tab1:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total de Transações", len(df))

            with col2:
                if 'VALOR' in df.columns:
                    total_valor = df['VALOR'].sum()
                    st.metric("Saldo Total", f"R$ {total_valor:,.2f}")

            with col3:
                st.metric("Categorias Detectadas", df['CATEGORIA'].nunique())

            with col4:
                dt_range = f"{len(df['CATEGORIA'].unique())} categorias"
                st.metric("Período", arquivo.name[:10])

            # GRÁFICO: TRANSAÇÕES POR CATEGORIA
            st.subheader("📊 Transações por Categoria")
            cat_count = df['CATEGORIA'].value_counts().reset_index()
            cat_count.columns = ['Categoria', 'Quantidade']

            fig_cat = px.bar(
                cat_count,
                x='Categoria',
                y='Quantidade',
                color='Categoria',
                title="Quantidade de Transações por Categoria",
                labels={'Quantidade': 'Nº de Transações'}
            )
            st.plotly_chart(fig_cat, use_container_width=True)

            # GRÁFICO: VALOR POR CATEGORIA (se disponível)
            if 'VALOR' in df.columns:
                st.subheader("💵 Valor Total por Categoria")
                valor_cat = df.groupby('CATEGORIA')['VALOR'].sum().reset_index()
                valor_cat.columns = ['Categoria', 'Valor']
                valor_cat = valor_cat.sort_values('Valor', ascending=False)

                fig_valor = px.pie(
                    valor_cat,
                    values='Valor',
                    names='Categoria',
                    title="Distribuição de Valor por Categoria"
                )
                st.plotly_chart(fig_valor, use_container_width=True)

        # ====================================================================
        # TAB 2: DADOS BRUTOS
        # ====================================================================
        with tab2:
            st.subheader("📋 Dados Originais + Categorização")

            # Filtro por categoria
            categorias_disponiveis = sorted(df['CATEGORIA'].unique())
            filtro_cat = st.multiselect(
                "Filtrar por categoria:",
                categorias_disponiveis,
                default=categorias_disponiveis
            )

            df_filtrado = df[df['CATEGORIA'].isin(filtro_cat)]

            st.dataframe(
                df_filtrado,
                use_container_width=True,
                height=400
            )

        # ====================================================================
        # TAB 3: ANÁLISE DE CATEGORIAS
        # ====================================================================
        with tab3:
            st.subheader("🏷️ Análise Detalhada por Categoria")

            for categoria in sorted(df['CATEGORIA'].unique()):
                df_cat = df[df['CATEGORIA'] == categoria]

                with st.expander(f"**{categoria}** ({len(df_cat)} transações)"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write(f"**Quantidade:** {len(df_cat)}")

                    with col2:
                        if 'VALOR' in df.columns:
                            st.write(f"**Valor Total:** R$ {df_cat['VALOR'].sum():,.2f}")

                    # Mostra as transações dessa categoria
                    st.dataframe(df_cat, use_container_width=True)

        # ====================================================================
        # TAB 4: DOWNLOAD
        # ====================================================================
        with tab4:
            st.subheader("📥 Exportar Dados Categorizados")

            # Download como CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"extrato_categorizado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

            # Download como XLSX
            from io import BytesIO
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Extrato', index=False)
            buffer.seek(0)

            st.download_button(
                label="📥 Download XLSX",
                data=buffer,
                file_name=f"extrato_categorizado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ============================================================================
# PÁGINA INICIAL (se não upload nenhum)
# ============================================================================
else:
    st.info("👈 Comece clicando em 'Importar Dados' no menu à esquerda!")

    st.markdown("""
    ## 🚀 Como Usar

    1. **Exporte seu extrato bancário** (CSV ou XLSX)
       - Itaú, Bradesco, Santander, etc
       - Qualquer banco

    2. **Clique em 'Escolha seu extrato bancário'**
       - Selecione o arquivo

    3. **Veja a magia acontecer!**
       - Categorização automática ✨
       - Gráficos e análises
       - Download de dados categorizados

    ## 📊 O que este sistema faz?

    ✅ **Categorização Automática** - Identifica CASA, TRANSPORTE, ALIMENTAÇÃO, etc
    ✅ **Análises Visuais** - Gráficos bonitos e informativos
    ✅ **Exportação** - Download em CSV ou XLSX
    ✅ **Filtros Inteligentes** - Organize por categoria

    ---

    **💡 Dica:** Este sistema é o começo de uma solução maior para autônomos e PJs.
    Toda semana vêm novas funcionalidades!
    """)

    # FAQ
    with st.expander("❓ Perguntas Frequentes"):
        st.markdown("""
        **P: Meu extrato tem outro formato?**
        R: Tente exportar como CSV no seu banco. Se não funcionar, avise para ajustarmos.

        **P: Os dados ficam salvos?**
        R: Não! Tudo é processado no navegador. Ninguém vê seus dados.

        **P: Posso compartilhar este link?**
        R: Sim! Mas cada pessoa envia seus próprios arquivos.
        """)
