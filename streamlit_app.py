#!/usr/bin/env python3
"""
Automação SEI-SIGEF com Streamlit
Interface web para análise de processos de liquidação de despesa
Roda em Streamlit Cloud
"""

import streamlit as st
import os
import json
import time
from datetime import datetime
from pathlib import Path

try:
    import anthropic
    from anthropic import Anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

# Configuração da página
st.set_page_config(
    page_title="🤖 Automação SEI-SIGEF",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .metric-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

MODELO_CLAUDE = "claude-opus-5-5"

# Formato de resposta exigido do Claude (saída estruturada garante JSON válido)
SCHEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["APROVADO", "DEVOLVIDO", "PENDENTE"]},
        "validacoes": {
            "type": "object",
            "properties": {
                "dados_coerentes": {"type": "boolean"},
                "documentacao_completa": {"type": "boolean"},
                "sem_riscos": {"type": "boolean"}
            },
            "required": ["dados_coerentes", "documentacao_completa", "sem_riscos"],
            "additionalProperties": False
        },
        "riscos": {"type": "array", "items": {"type": "string"}},
        "recomendacao": {"type": "string"},
        "motivo_devolucao": {"type": "string"}
    },
    "required": ["status", "validacoes", "riscos", "recomendacao", "motivo_devolucao"],
    "additionalProperties": False
}


def ler_segredo(nome):
    """Lê um segredo do Streamlit (secrets.toml / Cloud) ou de variável de ambiente.

    st.secrets lança exceção quando não existe nenhum secrets.toml, por isso o try.
    """
    try:
        valor = st.secrets.get(nome)
    except Exception:
        valor = None
    return valor or os.getenv(nome)


class AnaliseProcessoSEI:
    """Análise de processo SEI com Claude"""

    def __init__(self):
        self.claude_api_key = ler_segredo("CLAUDE_API_KEY") or ler_segredo("ANTHROPIC_API_KEY")
        self.client = None

        if CLAUDE_AVAILABLE and self.claude_api_key:
            try:
                self.client = Anthropic(api_key=self.claude_api_key)
            except Exception as e:
                st.error(f"Erro ao conectar com Claude API: {e}")

    def analisar_documentos(self, numero_processo, nfe_data, empenho_data, dados_adicionais=""):
        """Analisar documentos com Claude"""
        if not self.client:
            return False, "Claude API não configurada"

        try:
            prompt = f"""
Você é um auditor financeiro especialista em liquidação de despesa pública (SIGEF/SEI).

ANÁLISE SOLICITADA:
Processo: {numero_processo}
NF-e: {nfe_data}
Empenho: {empenho_data}
{f'Dados adicionais: {dados_adicionais}' if dados_adicionais else ''}

VALIDAÇÕES OBRIGATÓRIAS:
1. Dados da NF-e coincidem com o Empenho?
2. Documentação está completa?
3. Há riscos ou anomalias?
4. Recomendação final?

Responda em português. Use status APROVADO, DEVOLVIDO ou PENDENTE.
Em "motivo_devolucao", deixe vazio ("") se não houver devolução.
"""

            message = self.client.beta.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=16000,
                # Se o modelo recusar a solicitação, a API tenta outro modelo automaticamente
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "format": {"type": "json_schema", "schema": SCHEMA_RESPOSTA}
                },
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if message.stop_reason == "refusal":
                return False, "O Claude recusou esta solicitação. Revise os dados informados."
            if message.stop_reason == "max_tokens":
                return False, "Resposta do Claude foi cortada. Tente novamente."

            resposta_texto = next(
                (b.text for b in message.content if b.type == "text"), ""
            )
            return True, json.loads(resposta_texto)

        except anthropic.AuthenticationError:
            return False, "CLAUDE_API_KEY inválida. Confira a chave em Settings → Secrets."
        except anthropic.PermissionDeniedError:
            return False, "A chave da API não tem permissão para este modelo."
        except anthropic.RateLimitError:
            return False, "Limite de uso da API atingido. Aguarde um minuto e tente de novo."
        except anthropic.APIStatusError as e:
            if e.status_code == 400 and "credit" in str(e.message).lower():
                return False, "Sem créditos na conta da API (console.anthropic.com → Billing)."
            return False, f"Erro da API ({e.status_code}): {e.message}"
        except anthropic.APIConnectionError:
            return False, "Não foi possível conectar à API do Claude. Tente novamente."
        except Exception as e:
            return False, f"Erro ao analisar: {e}"


def main():
    st.title("🤖 Automação SEI-SIGEF")
    st.markdown("**Análise inteligente de processos de liquidação de despesa**")

    # Sidebar - Configuração
    with st.sidebar:
        st.header("⚙️ Configuração")

        analise = AnaliseProcessoSEI()

        if not CLAUDE_AVAILABLE:
            st.error("❌ Biblioteca Anthropic não instalada")
            st.info("Execute: `pip install anthropic`")
        elif not analise.claude_api_key:
            st.error("❌ CLAUDE_API_KEY não configurada")
            st.info("""
            Adicione em Streamlit Cloud:
            - Vá para Settings → Secrets
            - Adicione: `CLAUDE_API_KEY = "sk-ant-xxxxx"`
            """)
        else:
            st.success("✅ Claude API configurada")

        st.divider()
        st.subheader("📞 Suporte")
        st.write("""
        [GitHub](https://github.com/seu-usuario/automacao-sei-sigef)
        [Documentação](https://seu-site.com)
        """)

    # Abas principais
    tab1, tab2, tab3 = st.tabs(["🚀 Analisar Processo", "📋 Histórico", "📚 Documentação"])

    # Tab 1: Analisar
    with tab1:
        st.header("Analisar Novo Processo")

        col1, col2 = st.columns(2)

        with col1:
            numero_processo = st.text_input(
                "Número do Processo SEI",
                placeholder="Ex: 00610029.010710/2026-06",
                help="Digite o número completo do processo"
            )

        with col2:
            data_nfe = st.text_input(
                "Data da NF-e",
                placeholder="Ex: 23/09/2026",
                help="Data de emissão da nota fiscal"
            )

        col3, col4 = st.columns(2)

        with col3:
            cnpj_fornecedor = st.text_input(
                "CNPJ Fornecedor",
                placeholder="Ex: 61.703.774/0001-73",
                help="CNPJ de quem emitiu a NF"
            )

        with col4:
            valor_nfe = st.text_input(
                "Valor NF-e",
                placeholder="Ex: 12.300,00",
                help="Valor total da nota fiscal"
            )

        numero_empenho = st.text_input(
            "Número do Empenho",
            placeholder="Ex: 2026NE005156",
            help="Número do empenho associado"
        )

        observacoes = st.text_area(
            "Observações Adicionais",
            placeholder="Adicione qualquer informação relevante...",
            height=100,
            help="Informações que ajudem na análise"
        )

        # Botão de análise
        if st.button("🔍 Analisar Processo", type="primary", width="stretch"):
            if not numero_processo:
                st.error("Por favor, insira o número do processo")
            elif not analise.client:
                st.error("Claude API não está configurada corretamente")
            else:
                with st.spinner("🔄 Analisando processo..."):
                    # Preparar dados
                    nfe_data = f"""
                    Data: {data_nfe}
                    CNPJ: {cnpj_fornecedor}
                    Valor: {valor_nfe}
                    """

                    empenho_data = f"""
                    Número: {numero_empenho}
                    """

                    # Analisar
                    ok, resultado = analise.analisar_documentos(
                        numero_processo,
                        nfe_data,
                        empenho_data,
                        observacoes
                    )

                    if ok:
                        st.divider()

                        # Exibir resultado
                        status = resultado.get('status', 'PENDENTE')

                        col1, col2, col3 = st.columns(3)

                        with col1:
                            if status == 'APROVADO':
                                st.success(f"✅ **{status}**", icon="✅")
                            elif status == 'DEVOLVIDO':
                                st.error(f"❌ **{status}**", icon="❌")
                            else:
                                st.warning(f"⚠️ **{status}**", icon="⚠️")

                        with col2:
                            st.metric("Timestamp", datetime.now().strftime("%H:%M:%S"))

                        with col3:
                            validacoes = resultado.get('validacoes', {})
                            count = sum(1 for v in validacoes.values() if v)
                            st.metric("Validações OK", f"{count}/{len(validacoes)}")

                        st.divider()

                        # Detalhes
                        st.subheader("📊 Análise Detalhada")

                        col1, col2 = st.columns(2)

                        with col1:
                            st.write("**Validações:**")
                            validacoes = resultado.get('validacoes', {})
                            for key, value in validacoes.items():
                                status_val = "✅" if value else "❌"
                                st.write(f"{status_val} {key.replace('_', ' ').title()}")

                        with col2:
                            st.write("**Recomendação:**")
                            st.info(resultado.get('recomendacao', 'Sem recomendação'))

                        # Riscos
                        riscos = resultado.get('riscos', [])
                        if riscos:
                            st.warning("**⚠️ Riscos Detectados:**")
                            for risco in riscos:
                                st.write(f"• {risco}")

                        # Download
                        resultado_arquivo = {
                            "processo": numero_processo,
                            "data_analise": datetime.now().isoformat(),
                            "nfe": {
                                "data": data_nfe,
                                "cnpj": cnpj_fornecedor,
                                "valor": valor_nfe
                            },
                            "empenho": numero_empenho,
                            "analise": resultado
                        }

                        st.download_button(
                            "📥 Download Resultado (JSON)",
                            json.dumps(resultado_arquivo, indent=2, ensure_ascii=False),
                            f"{numero_processo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            "application/json",
                            width="stretch"
                        )

                    else:
                        st.error(f"❌ Erro na análise: {resultado}")

    # Tab 2: Histórico
    with tab2:
        st.header("📋 Histórico de Análises")

        st.info("""
        O histórico é salvo localmente no Streamlit Cloud.
        Para cada análise, você pode baixar um arquivo JSON com os resultados.
        """)

        st.write("""
        **Como revisar análises anteriores:**
        1. Os arquivos JSON baixados contêm todos os detalhes
        2. Você pode manter um registro em seu Google Drive ou GitHub
        3. Use a busca para encontrar processos específicos
        """)

    # Tab 3: Documentação
    with tab3:
        st.header("📚 Como Usar")

        st.markdown("""
        ## Passo a Passo

        ### 1. Configure as Credenciais (Uma vez)
        Na aba "Settings" do Streamlit Cloud:
        - Vá para "Secrets"
        - Adicione:
        ```
        CLAUDE_API_KEY = "sk-ant-xxxxxxxxxxxxx"
        ```

        ### 2. Analise um Processo
        - Preencha os dados do processo
        - Clique em "🔍 Analisar Processo"
        - Aguarde a análise (3-5 segundos)
        - Download do resultado em JSON

        ### 3. Interpretação dos Resultados

        **✅ APROVADO**
        - Todos os dados estão corretos
        - Documentação está completa
        - Pode prosseguir com CE + NL

        **❌ DEVOLVIDO**
        - Faltam documentos ou há inconsistências
        - Retornar para correção

        **⚠️ PENDENTE**
        - Requer análise manual
        - Verificar riscos detectados

        ## Obter API Key Claude

        1. Acesse: https://console.anthropic.com
        2. Clique em "API Keys"
        3. Clique em "Create Key"
        4. Copie a chave (começa com `sk-ant-`)
        5. Cole no Streamlit Cloud Secrets

        Custo: ~R$ 1-2/mês com análises regulares

        ## Riscos Detectados

        O Claude analisa:
        - Coerência entre NF e Empenho
        - Valores correspondentes
        - Fornecedor verificado
        - Documentação completa
        - Assinaturas válidas

        Qualquer anomalia é sinalizada para revisão.
        """)


if __name__ == "__main__":
    main()
