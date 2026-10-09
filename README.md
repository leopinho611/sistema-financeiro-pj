# 🤖 Automação SEI-SIGEF com Streamlit

**Análise inteligente de processos de liquidação de despesa usando Claude AI**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://seu-app.streamlit.app)

## 🎯 O que faz?

Automatiza a análise de processos de liquidação de despesa:

```
Você insere dados do processo
  ↓
Claude analisa os documentos
  ↓
Sistema recomenda: APROVADO / DEVOLVIDO / PENDENTE
  ↓
Você faz a conferência final
```

**Resultado**: O que levava 30-40 minutos agora leva **3-5 minutos** ⚡

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
- Insira os dados do processo
- Clique em "Analisar"
- Pronto! ✅

---

## 📊 Exemplo de Análise

**Entrada:**
```
Processo: 00610029.010710/2026-06
NF-e: 23/09/2026
CNPJ: 61.703.774/0001-73
Valor: R$ 12.300,00
Empenho: 2026NE005156
```

**Saída:**
```json
{
  "status": "APROVADO",
  "validacoes": {
    "dados_coerentes": true,
    "documentacao_completa": true,
    "sem_riscos": true
  },
  "recomendacao": "Processo apto para emissão de CE e NL",
  "riscos": []
}
```

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
- **Claude API**: ~R$ 1-2/mês (5 processos/dia)
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
