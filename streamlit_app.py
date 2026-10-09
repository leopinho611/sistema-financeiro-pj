#!/usr/bin/env python3
"""
Automação SEI-SIGEF com Streamlit - SESAP/RN
Análise de processos de liquidação de despesa a partir do PDF do processo
(gerado no SEI) e do XML da NF-e.
Roda em Streamlit Cloud
"""

import base64
import io
import json
import os
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

import streamlit as st
from pypdf import PdfReader, PdfWriter

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

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
MODELO_CLAUDE = "claude-opus-5-5"
PRECO_ENTRADA_USD = 4.00 / 1_000_000   # por token
PRECO_SAIDA_USD = 20.00 / 1_000_000    # por token

LIMITE_PAGINAS = 600                   # limite da API por PDF
LIMITE_PDF_BYTES = 22 * 1024 * 1024    # ~22 MB (vira ~30 MB em base64; limite da API é 32 MB)
LIMITE_TEXTO_XML = 60_000              # caracteres de XML "desconhecido" enviados ao Claude

# Páginas com estas palavras são enviadas no modo econômico
PALAVRAS_RELEVANTES = [
    "nota fiscal", "danfe", "nf-e", "nfs-e", "nfse", "fatura",
    "empenho", "atesto", "atestamos", "atesta", "certifico", "certificamos",
    "recebimento", "visto", "despacho", "diligencia",
]
# Páginas com pouco texto costumam ser digitalizadas (imagem): sempre enviadas
MIN_CARACTERES_TEXTO = 80

DOCUMENTOS = {
    "nota_fiscal": "Nota Fiscal",
    "empenho": "Nota de Empenho",
    "atesto": "Atesto",
    "visto": "Visto",
    "despacho_diligencial": "Despacho Diligencial",
}

# ============================================================================
# FORMATO DA RESPOSTA (saída estruturada garante JSON válido)
# ============================================================================
SCHEMA_DOCUMENTO = {
    "type": "object",
    "properties": {
        "encontrado": {"type": "boolean"},
        "localizacao": {"type": "array", "items": {"type": "string"}},
        "dados": {"type": "string"},
        "problemas": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["encontrado", "localizacao", "dados", "problemas"],
    "additionalProperties": False
}

SCHEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["APROVADO", "DEVOLVIDO", "PENDENTE"]},
        "resumo_processo": {
            "type": "object",
            "properties": {
                "numero_processo": {"type": "string"},
                "fornecedor": {"type": "string"},
                "cnpj_fornecedor": {"type": "string"},
                "objeto": {"type": "string"},
                "numero_nf": {"type": "string"},
                "data_emissao_nf": {"type": "string"},
                "valor_nf": {"type": "string"},
                "numero_empenho": {"type": "string"},
                "valor_empenho": {"type": "string"}
            },
            "required": ["numero_processo", "fornecedor", "cnpj_fornecedor", "objeto",
                         "numero_nf", "data_emissao_nf", "valor_nf",
                         "numero_empenho", "valor_empenho"],
            "additionalProperties": False
        },
        "documentos": {
            "type": "object",
            "properties": {chave: SCHEMA_DOCUMENTO for chave in DOCUMENTOS},
            "required": list(DOCUMENTOS),
            "additionalProperties": False
        },
        "conferencias": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "resultado": {"type": "string",
                                  "enum": ["OK", "DIVERGENTE", "NAO_VERIFICAVEL"]},
                    "detalhe": {"type": "string"}
                },
                "required": ["item", "resultado", "detalhe"],
                "additionalProperties": False
            }
        },
        "riscos": {"type": "array", "items": {"type": "string"}},
        "recomendacao": {"type": "string"},
        "motivo_devolucao": {"type": "string"}
    },
    "required": ["status", "resumo_processo", "documentos", "conferencias",
                 "riscos", "recomendacao", "motivo_devolucao"],
    "additionalProperties": False
}

INSTRUCOES_SISTEMA = """Você é analista de liquidação de despesa da Secretaria de Estado da Saúde \
Pública do Rio Grande do Norte (SESAP/RN). Sua tarefa é conferir um processo SEI de \
liquidação (Lei 4.320/64, art. 63) e apoiar o servidor responsável, que fará a \
conferência final.

O PDF anexado é o processo (ou parte dele). Os documentos de interesse ficam no meio \
de vários outros. Localize e analise:
1. NOTA FISCAL (NF-e/DANFE ou NFS-e): número, data de emissão, emitente e CNPJ, \
destinatário, valor total, descrição do objeto.
2. NOTA DE EMPENHO: número, data, credor e CNPJ, valor, objeto/elemento de despesa.
3. ATESTO: declaração de recebimento do material/serviço pelo fiscal ou comissão; \
verifique se identifica a NF atestada, se está assinado, quem assinou e a data.
4. VISTO: visto da chefia/autoridade competente sobre o atesto ou o processo; \
verifique se está assinado e datado.
5. DESPACHO DILIGENCIAL: despacho que solicita diligências/correções. Se existir, \
verifique o que foi pedido e se as pendências foram atendidas nos documentos \
posteriores. Se não existir, registre como não encontrado e diga isso em "dados".

Conferências cruzadas mínimas (inclua cada uma em "conferencias"):
- CNPJ e razão social do emitente da NF = credor do empenho
- Valor da NF dentro do saldo/valor do empenho
- Objeto da NF compatível com o objeto do empenho
- Data do empenho anterior ou igual à emissão da NF (empenho prévio)
- Atesto referencia a NF correta e é posterior à emissão da NF
- Atesto e visto assinados (assinatura eletrônica SEI ou física)
- Pendências de despacho diligencial atendidas (se houver)
- Se houver dados do XML da NF-e, conferir com o DANFE/NF do processo

Regras:
- Em "localizacao", use a referência de página ORIGINAL informada no mapa de páginas \
(ex.: "processo.pdf p. 37").
- Não invente dados. Se algo não estiver legível ou não constar, diga isso e use \
NAO_VERIFICAVEL.
- status APROVADO só se os documentos obrigatórios (NF, empenho, atesto, visto) \
estiverem presentes e todas as conferências estiverem OK. DEVOLVIDO quando houver \
falta de documento ou divergência que exija correção. PENDENTE quando houver dúvida \
que exija análise humana.
- Em "motivo_devolucao", escreva o texto que poderia ir no despacho de devolução; \
deixe vazio ("") se não houver devolução.
- Responda em português."""


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================
def ler_segredo(nome):
    """Lê um segredo do Streamlit (secrets.toml / Cloud) ou de variável de ambiente.

    st.secrets lança exceção quando não existe nenhum secrets.toml, por isso o try.
    """
    try:
        valor = st.secrets.get(nome)
    except Exception:
        valor = None
    return valor or os.getenv(nome)


def normalizar(texto):
    """Minúsculas e sem acentos, para busca de palavras-chave."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def pagina_relevante(texto):
    """Decide se uma página deve ser enviada ao Claude no modo econômico."""
    if len(texto.strip()) < MIN_CARACTERES_TEXTO:
        return True  # provável digitalização (imagem): não dá para saber pelo texto
    texto_norm = normalizar(texto)
    return any(palavra in texto_norm for palavra in PALAVRAS_RELEVANTES)


def preparar_pdf(arquivos, so_relevantes):
    """Junta os PDFs enviados em um só, opcionalmente só com as páginas relevantes.

    Retorna (bytes do PDF, mapa de páginas [(arquivo, página original)], total de páginas).
    """
    writer = PdfWriter()
    mapa = []
    total = 0
    for arquivo in arquivos:
        try:
            reader = PdfReader(io.BytesIO(arquivo.getvalue()))
            if reader.is_encrypted:
                reader.decrypt("")
            paginas = list(reader.pages)
        except Exception as e:
            raise ValueError(f"Não foi possível ler '{arquivo.name}': {e}")

        for numero, pagina in enumerate(paginas, start=1):
            total += 1
            if so_relevantes:
                try:
                    texto = pagina.extract_text() or ""
                except Exception:
                    texto = ""
                if not pagina_relevante(texto):
                    continue
            writer.add_page(pagina)
            mapa.append((arquivo.name, numero))

    saida = io.BytesIO()
    writer.write(saida)
    return saida.getvalue(), mapa, total


def _texto(elemento, caminho, ns):
    achado = elemento.find(caminho, ns) if elemento is not None else None
    return achado.text.strip() if achado is not None and achado.text else ""


def ler_xml_nfe(conteudo):
    """Extrai os dados principais de um XML de NF-e (modelo 55/65).

    Retorna um dict; se não for NF-e no padrão nacional, retorna o XML bruto
    em "xml_bruto" para o Claude interpretar (ex.: NFS-e municipal).
    """
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido: {e}")

    ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
    inf = raiz.find(".//nfe:infNFe", ns)
    if inf is None:
        texto = conteudo.decode("utf-8", errors="replace")
        return {"tipo": "XML não reconhecido como NF-e", "xml_bruto": texto[:LIMITE_TEXTO_XML]}

    ide = inf.find("nfe:ide", ns)
    emit = inf.find("nfe:emit", ns)
    dest = inf.find("nfe:dest", ns)
    total = inf.find("nfe:total/nfe:ICMSTot", ns)

    itens = []
    for det in inf.findall("nfe:det", ns)[:100]:
        prod = det.find("nfe:prod", ns)
        itens.append({
            "descricao": _texto(prod, "nfe:xProd", ns),
            "quantidade": _texto(prod, "nfe:qCom", ns),
            "unidade": _texto(prod, "nfe:uCom", ns),
            "valor_unitario": _texto(prod, "nfe:vUnCom", ns),
            "valor_total": _texto(prod, "nfe:vProd", ns),
        })

    return {
        "tipo": "NF-e",
        "chave_acesso": inf.get("Id", "").replace("NFe", ""),
        "numero": _texto(ide, "nfe:nNF", ns),
        "serie": _texto(ide, "nfe:serie", ns),
        "data_emissao": _texto(ide, "nfe:dhEmi", ns) or _texto(ide, "nfe:dEmi", ns),
        "emitente_cnpj": _texto(emit, "nfe:CNPJ", ns),
        "emitente_nome": _texto(emit, "nfe:xNome", ns),
        "destinatario_cnpj": _texto(dest, "nfe:CNPJ", ns),
        "destinatario_nome": _texto(dest, "nfe:xNome", ns),
        "valor_total_nf": _texto(total, "nfe:vNF", ns),
        "valor_produtos": _texto(total, "nfe:vProd", ns),
        "informacoes_complementares": _texto(inf, "nfe:infAdic/nfe:infCpl", ns),
        "itens": itens,
    }


# ============================================================================
# ANÁLISE COM CLAUDE
# ============================================================================
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

    def analisar_processo(self, pdf_bytes, mapa_paginas, dados_xml, numero_processo="",
                          observacoes=""):
        """Envia o PDF (e os dados do XML) ao Claude e devolve (ok, resultado, uso)."""
        if not self.client:
            return False, "Claude API não configurada", None

        linhas_mapa = "\n".join(
            f"Página {i} do PDF anexo = {nome} p. {pag}"
            for i, (nome, pag) in enumerate(mapa_paginas, start=1)
        )
        partes = [f"MAPA DE PÁGINAS (use a referência original na resposta):\n{linhas_mapa}"]
        if numero_processo:
            partes.append(f"Número do processo informado pelo servidor: {numero_processo}")
        if dados_xml:
            partes.append("DADOS EXTRAÍDOS DO(S) XML DA NF-e:\n"
                          + json.dumps(dados_xml, ensure_ascii=False, indent=2))
        if observacoes:
            partes.append(f"Observações do servidor: {observacoes}")
        partes.append("Faça a análise de liquidação conforme as instruções.")

        try:
            message = self.client.beta.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=16000,
                system=INSTRUCOES_SISTEMA,
                # Se o modelo recusar a solicitação, a API tenta outro modelo automaticamente
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": "high",
                    "format": {"type": "json_schema", "schema": SCHEMA_RESPOSTA},
                },
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.standard_b64encode(pdf_bytes).decode("utf-8"),
                            },
                        },
                        {"type": "text", "text": "\n\n".join(partes)},
                    ],
                }],
            )

            uso = message.usage
            if message.stop_reason == "refusal":
                return False, "O Claude recusou esta solicitação. Revise os arquivos enviados.", uso
            if message.stop_reason == "max_tokens":
                return False, "Resposta do Claude foi cortada. Tente novamente.", uso

            resposta_texto = next(
                (b.text for b in message.content if b.type == "text"), ""
            )
            return True, json.loads(resposta_texto), uso

        except anthropic.AuthenticationError:
            return False, "CLAUDE_API_KEY inválida. Confira a chave em Settings → Secrets.", None
        except anthropic.PermissionDeniedError:
            return False, "A chave da API não tem permissão para este modelo.", None
        except anthropic.RateLimitError:
            return False, "Limite de uso da API atingido. Aguarde um minuto e tente de novo.", None
        except anthropic.APIStatusError as e:
            if e.status_code == 400 and "credit" in str(e.message).lower():
                return False, "Sem créditos na conta da API (console.anthropic.com → Billing).", None
            if e.status_code == 413:
                return False, "Arquivo grande demais para a API. Gere o PDF no SEI só com os documentos necessários.", None
            return False, f"Erro da API ({e.status_code}): {e.message}", None
        except anthropic.APIConnectionError:
            return False, "Não foi possível conectar à API do Claude. Tente novamente.", None
        except Exception as e:
            return False, f"Erro ao analisar: {e}", None


# ============================================================================
# EXIBIÇÃO DO RESULTADO
# ============================================================================
def custo_estimado(uso):
    if uso is None:
        return None
    return uso.input_tokens * PRECO_ENTRADA_USD + uso.output_tokens * PRECO_SAIDA_USD


def exibir_resultado(registro):
    resultado = registro["analise"]
    status = resultado.get("status", "PENDENTE")

    col1, col2, col3 = st.columns(3)
    with col1:
        if status == "APROVADO":
            st.success(f"**{status}**", icon="✅")
        elif status == "DEVOLVIDO":
            st.error(f"**{status}**", icon="❌")
        else:
            st.warning(f"**{status}**", icon="⚠️")
    with col2:
        docs = resultado.get("documentos", {})
        encontrados = sum(1 for d in docs.values() if d.get("encontrado"))
        st.metric("Documentos localizados", f"{encontrados}/{len(DOCUMENTOS)}")
    with col3:
        custo = registro.get("custo_usd")
        st.metric("Custo da análise", f"US$ {custo:.2f}" if custo is not None else "-")

    st.write("**Recomendação:**")
    st.info(resultado.get("recomendacao", "Sem recomendação"))

    if resultado.get("motivo_devolucao"):
        st.write("**Texto sugerido para devolução:**")
        st.code(resultado["motivo_devolucao"], language=None, wrap_lines=True)

    # Resumo
    resumo = resultado.get("resumo_processo", {})
    if resumo:
        st.subheader("🧾 Resumo do Processo")
        st.table([{"Campo": k.replace("_", " ").capitalize(), "Valor": v or "-"}
                  for k, v in resumo.items()])

    # Documentos
    st.subheader("📑 Documentos")
    for chave, nome in DOCUMENTOS.items():
        doc = resultado.get("documentos", {}).get(chave, {})
        icone = "✅" if doc.get("encontrado") else "❌"
        local = ", ".join(doc.get("localizacao", [])) or "não localizado"
        problemas = doc.get("problemas", [])
        titulo = f"{icone} {nome} — {local}" + (f"  ⚠️ {len(problemas)} problema(s)" if problemas else "")
        with st.expander(titulo):
            st.write(doc.get("dados", ""))
            for p in problemas:
                st.write(f"• {p}")

    # Conferências
    conferencias = resultado.get("conferencias", [])
    if conferencias:
        st.subheader("🔎 Conferências")
        icones = {"OK": "✅", "DIVERGENTE": "❌", "NAO_VERIFICAVEL": "❔"}
        st.table([{"": icones.get(c["resultado"], ""), "Item": c["item"],
                   "Resultado": c["resultado"], "Detalhe": c["detalhe"]}
                  for c in conferencias])

    riscos = resultado.get("riscos", [])
    if riscos:
        st.warning("**⚠️ Riscos Detectados:**")
        for risco in riscos:
            st.write(f"• {risco}")

    nome_arquivo = (registro.get("processo") or "analise").replace("/", "-")
    st.download_button(
        "📥 Download Resultado (JSON)",
        json.dumps(registro, indent=2, ensure_ascii=False),
        f"{nome_arquivo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        "application/json",
        width="stretch"
    )


# ============================================================================
# APP
# ============================================================================
def main():
    st.title("🤖 Automação SEI-SIGEF")
    st.markdown("**Análise de processos de liquidação de despesa — SESAP/RN**")

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
        so_relevantes = st.toggle(
            "Modo econômico",
            value=True,
            help="Envia ao Claude só as páginas que mencionam NF, empenho, atesto, "
                 "visto ou despacho, além das páginas digitalizadas (sem texto). "
                 "Desligue se algum documento não for localizado."
        )

    # Abas principais
    tab1, tab2 = st.tabs(["🚀 Analisar Processo", "📚 Como Usar"])

    # Tab 1: Analisar
    with tab1:
        st.header("Analisar Novo Processo")

        pdfs = st.file_uploader(
            "PDF do processo (gerado no SEI)",
            type=["pdf"],
            accept_multiple_files=True,
            help="No SEI: ícone 'Gerar Arquivo PDF do Processo'. Pode enviar mais de um PDF."
        )
        xmls = st.file_uploader(
            "XML da NF-e (opcional)",
            type=["xml"],
            accept_multiple_files=True,
            help="O XML permite conferir os dados oficiais da nota com o que está no processo."
        )

        col1, col2 = st.columns(2)
        with col1:
            numero_processo = st.text_input(
                "Número do Processo SEI (opcional)",
                placeholder="Ex: 00610029.010710/2026-06"
            )
        with col2:
            observacoes = st.text_input(
                "Observações (opcional)",
                placeholder="Algo que ajude na análise..."
            )

        if st.button("🔍 Analisar Processo", type="primary", width="stretch"):
            st.session_state.pop("ultimo_resultado", None)
            if not pdfs:
                st.error("Envie o PDF do processo.")
            elif not analise.client:
                st.error("Claude API não está configurada corretamente")
            else:
                try:
                    with st.spinner("📄 Lendo arquivos..."):
                        pdf_bytes, mapa, total = preparar_pdf(pdfs, so_relevantes)
                        dados_xml = [dict(arquivo=x.name, **ler_xml_nfe(x.getvalue())) for x in xmls]
                except ValueError as e:
                    st.error(str(e))
                    st.stop()

                st.caption(f"Páginas no processo: {total} — enviadas para análise: {len(mapa)}")

                if not mapa:
                    st.error("Nenhuma página relevante encontrada. Desligue o modo econômico e tente de novo.")
                elif len(mapa) > LIMITE_PAGINAS:
                    st.error(f"Foram selecionadas {len(mapa)} páginas; o limite é {LIMITE_PAGINAS}. "
                             "Ligue o modo econômico ou gere no SEI um PDF só com os documentos necessários.")
                elif len(pdf_bytes) > LIMITE_PDF_BYTES:
                    st.error(f"O PDF ficou com {len(pdf_bytes) / 1024 / 1024:.0f} MB; o limite é "
                             f"{LIMITE_PDF_BYTES // 1024 // 1024} MB. Ligue o modo econômico ou gere "
                             "no SEI um PDF só com os documentos necessários.")
                else:
                    with st.spinner("🔄 Analisando processo (pode levar 1-3 minutos)..."):
                        ok, resultado, uso = analise.analisar_processo(
                            pdf_bytes, mapa, dados_xml, numero_processo, observacoes
                        )
                    if ok:
                        st.session_state["ultimo_resultado"] = {
                            "processo": numero_processo or resultado.get(
                                "resumo_processo", {}).get("numero_processo", ""),
                            "data_analise": datetime.now().isoformat(),
                            "arquivos_pdf": [p.name for p in pdfs],
                            "arquivos_xml": [x.name for x in xmls],
                            "paginas_total": total,
                            "paginas_enviadas": len(mapa),
                            "custo_usd": custo_estimado(uso),
                            "xml_nfe": dados_xml,
                            "analise": resultado,
                        }
                    else:
                        st.error(f"❌ Erro na análise: {resultado}")

        # Guardado na sessão para não sumir ao clicar em "Download"
        if "ultimo_resultado" in st.session_state:
            st.divider()
            exibir_resultado(st.session_state["ultimo_resultado"])

    # Tab 2: Documentação
    with tab2:
        st.header("📚 Como Usar")

        st.markdown("""
        ### 1. Gere o PDF do processo no SEI
        - Abra o processo no SEI
        - Clique no ícone **"Gerar Arquivo PDF do Processo"**
        - Pode gerar o processo inteiro: o app procura os documentos no meio dos demais

        ### 2. Baixe o XML da NF-e (opcional, recomendado)
        - Normalmente enviado pelo fornecedor junto com a nota
        - Ou pelo Portal Nacional da NF-e, com a chave de acesso

        ### 3. Envie os arquivos e clique em "🔍 Analisar Processo"
        O Claude localiza e confere:
        - **Nota Fiscal** — número, data, emitente, valor, objeto
        - **Nota de Empenho** — credor, valor, objeto, data
        - **Atesto** — referência à NF, assinatura, data
        - **Visto** — assinatura e data
        - **Despacho Diligencial** — pendências e se foram atendidas

        E faz as conferências cruzadas (CNPJ, valor, objeto, datas, assinaturas).

        ### 4. Interpretação dos Resultados
        **✅ APROVADO** — documentos presentes e conferências OK; pode prosseguir com CE + NL

        **❌ DEVOLVIDO** — falta documento ou há divergência; o app sugere o texto da devolução

        **⚠️ PENDENTE** — há dúvida que exige análise manual

        A análise é um apoio: **a conferência final é sempre do servidor.**

        ### Modo econômico (barra lateral)
        Envia ao Claude só as páginas que mencionam os documentos procurados e as páginas
        digitalizadas. Reduz bastante o custo em processos grandes. Se algum documento
        não for localizado, desligue e analise de novo.

        ### Limites
        - Até 600 páginas enviadas por análise
        - PDF enviado de até ~22 MB (depois do filtro do modo econômico)
        """)


if __name__ == "__main__":
    main()
