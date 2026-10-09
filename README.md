# 🤖 Automação SEI-SIGEF com Streamlit

**Análise inteligente de processos de liquidação de despesa usando Claude AI**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://seu-app.streamlit.app)

## 🎯 O que faz?

Automatiza a conferência de processos de liquidação de despesa da SESAP/RN:

```
Você envia o PDF do processo (gerado no SEI) + XML da NF-e (opcional)
  ↓
O app separa as páginas relevantes (modo econômico)
  ↓
Claude localiza NF, Empenho, Atesto, Visto e Despacho Diligencial
e faz as conferências cruzadas (CNPJ, valores, objeto, datas, assinaturas)
  ↓
Sistema recomenda: APROVADO / DEVOLVIDO / PENDENTE
(com página de cada documento e texto sugerido para devolução)
  ↓
Você faz a conferência final
```

---

## 🚀 Começar em 5 Minutos

### 1. Criar uma Conta (Grátis!)

- [GitHub](https://github.com/signup) - para o código
- [Streamlit Cloud](https://streamlit.io/cloud) - para rodar
- [Claude API](https://console.anthropic.com) - para análise

### 2. Clonar este Repositório

```bash
git clone https://github.com/SEU-USUARIO/automacao-sei-sigef.git
cd automacao-sei-sigef
```

### 3. Deploy no Streamlit Cloud

1. Vá para [Streamlit Cloud](https://streamlit.io/cloud)
2. Clique em "New app"
3. Conecte seu GitHub
4. Selecione este repositório
5. Clique em "Deploy"

### 4. Configurar Secrets

1. No Streamlit Cloud, vá para "Settings"
2. Clique em "Secrets"
3. Copie e cole:

```
CLAUDE_API_KEY = "sk-ant-xxxxxxxxxxxxx"
```

(Obtenha a API Key em https://console.anthropic.com)

### 5. Usar!

- Acesse `https://seu-app.streamlit.app`
- Envie o PDF do processo e o XML da NF-e
- Clique em "Analisar Processo"
- Pronto! ✅

---

## 📊 Exemplo de Análise

**Entrada:** `processo.pdf` (processo inteiro gerado no SEI) + `nfe.xml`

**Saída:**
- Status: ✅ APROVADO / ❌ DEVOLVIDO / ⚠️ PENDENTE
- Cada documento com a página onde foi encontrado (ex.: "Atesto — processo.pdf p. 37")
- Tabela de conferências (OK / DIVERGENTE / NÃO VERIFICÁVEL)
- Texto sugerido para o despacho de devolução
- Custo da análise e download do resultado em JSON

---

## 🔧 Configuração Local (Opcional)

Para testar localmente:

```bash
# Instalar dependências
pip install -r requirements.txt

# Criar o arquivo de segredos (não vai para o GitHub, está no .gitignore)
mkdir -p .streamlit
echo 'CLAUDE_API_KEY = "sk-ant-sua-chave-aqui"' > .streamlit/secrets.toml

# Rodar
streamlit run streamlit_app.py
```

Acesse `http://localhost:8501`

---

## 💰 Custos

- **Streamlit Cloud**: Grátis (1 app)
- **Claude API**: cobrado por análise; o valor aparece na tela após cada análise (processos grandes custam mais — use o modo econômico)
- **GitHub**: Grátis
- **Total**: Praticamente grátis! 🎉

---

## 📈 Impacto Esperado

| Métrica | Manual | Automático |
|---------|--------|-----------|
| Tempo/processo | 30-40 min | 3-5 min |
| Processos/dia | 5 | 50+ |
| Total/dia | 2.5h | 15 min |
| Redução | - | **87%** |

---

## 🔐 Segurança

✅ **Credenciais protegidas** no Streamlit Cloud Secrets
✅ **Sem armazenamento** de dados sensíveis
✅ **HTTPS** em todas as comunicações
✅ **Logs limpos** (sem dados confidenciais)

---

## 📞 Suporte

- 📚 [Documentação Claude](https://docs.claude.com)
- 🎬 [Streamlit Docs](https://docs.streamlit.io)
- 💬 [Claude Community](https://www.anthropic.com/community)

---

## 📝 Licença

MIT - Livre para usar, modificar e distribuir

---

## 🤝 Contribuições

Melhorias são bem-vindas! Faça um fork e envie um PR.

---

**Desenvolvido com** ❤️ **para automação de liquidação de despesas**

Pronto para começar? [Deploy Agora](https://streamlit.io/cloud) 🚀
