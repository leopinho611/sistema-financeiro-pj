import streamlit as st
import pandas as pd
from datetime import datetime

# ============================================================================
# CONFIGURAÇÃO DO APP
# ============================================================================
st.set_page_config(
    page_title="Sistema Financeiro PJ",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("💰 Sistema de Controle Financeiro - PJ/Autônomo")
st.markdown("Importar extrato bancário e categorizar automaticamente")

# ============================================================================
# CATEGORIAS
# ============================================================================
CATEGORIAS = {
    "CASA": ["aluguel", "condominio", "agua", "luz", "gas", "internet", "telefone"],
    "TRANSPORTE": ["combustivel", "gasolina", "estacionamento", "uber", "onibus"],
    "ALIMENTAÇÃO": ["restaurante", "comida", "mercado", "padaria", "delivery"],
    "SAÚDE": ["farmacia", "medico", "dentista", "hospital", "academia"],
    "EDUCAÇÃO": ["escola", "universidade", "curso", "livro"],
    "LAZER": ["cinema", "teatro", "show", "viagem", "hotel"],
    "SHOPPING": ["roupa", "sapato", "loja", "vestuario"],
    "INVESTIMENTO": ["fii", "acao", "tesouro", "bitcoin"],
    "IMPOSTO": ["irpf", "irpj", "icms", "pis"],
    "OUTRO": []
}

# ============================================================================
# FUNÇÕES
# ============================================================================
def categorizar(descritivo):
    """Categoriza uma transação"""
    descritivo_lower = str(descritivo).lower().strip()
    for categoria, palavras in CATEGORIAS.items():
        for palavra in palavras:
            if palavra in descritivo_lower:
                return categoria
    return "OUTRO"

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
if arquivo:
    try:
        # Lê o arquivo
        if arquivo.name.endswith('.xlsx'):
            df = pd.read_excel(arquivo)
        else:
            df = pd.read_csv(arquivo, encoding='utf-8')

        st.success(f"✅ Arquivo carregado! {len(df)} transações encontradas")

        # Adiciona categoria
        df['CATEGORIA'] = df.iloc[:, 0].apply(categorizar)

        # Cria abas
        tab1, tab2, tab3 = st.tabs(["📊 Resumo", "📋 Dados", "📥 Download"])

        with tab1:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Transações", len(df))
            col2.metric("Categorias", df['CATEGORIA'].nunique())
            col3.metric("Arquivo", arquivo.name[:20] + "...")

            st.subheader("Transações por Categoria")
            cat_count = df['CATEGORIA'].value_counts()
            st.bar_chart(cat_count)

        with tab2:
            st.subheader("Dados Originais")
            st.dataframe(df, use_container_width=True)

        with tab3:
            st.subheader("Exportar")
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                csv,
                f"extrato_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv"
            )

    except Exception as e:
        st.error(f"Erro: {e}")

else:
    st.info("👈 Clique em 'Importar Dados' no menu")
    st.markdown("""
    ## 🚀 Como Usar
    1. Exporte seu extrato bancário (CSV ou XLSX)
    2. Clique em 'Importar Dados'
    3. Selecione o arquivo
    4. Veja a magia! ✨
    """)
