# 🚀 Guia Passo a Passo: GitHub + Streamlit Cloud

Você criou conta em GitHub e Streamlit. Agora vamos colocar o código rodando na nuvem!

---

## 📋 Arquivos que você vai colocar no GitHub

Você vai precisar de **4 arquivos**:

1. `streamlit_app.py` - **O programa Streamlit**
2. `requirements.txt` - **As dependências Python**
3. `README.md` - **A documentação**
4. `.gitignore` - **Arquivos a ignorar** (senhas, cache, etc)

---

## ✅ Passo 1: Criar um Novo Repositório no GitHub

1. **Vá para** https://github.com/new
2. **Nome do repositório:** `automacao-sei-sigef` (pode ser outro)
3. **Descrição:** "Automação de análise SEI-SIGEF com Streamlit e Claude AI"
4. **Público ou Privado:** Depende de você (público = qualquer um vê)
5. **Não marque** "Initialize this repository with a README"
6. **Clique em** "Create repository"

Pronto! Você terá uma URL como: `https://github.com/seu-usuario/automacao-sei-sigef`

---

## 📤 Passo 2: Adicionar os Arquivos no GitHub

### Opção A: Pela Web (Mais Fácil)

1. Na página do repositório que você criou, clique em "Add file" → "Create new file"
2. **Nome do arquivo:** `streamlit_app.py`
3. **Cola o conteúdo** do arquivo `streamlit_app.py` aqui
4. **Clique em** "Commit changes"

Repita para os outros 3 arquivos:
- `requirements.txt`
- `README.md`
- `.gitignore`

### Opção B: Pelo Git (Mais Profissional)

```bash
# 1. Clonar o repositório
git clone https://github.com/seu-usuario/automacao-sei-sigef.git
cd automacao-sei-sigef

# 2. Copiar os 4 arquivos para essa pasta
# (Coloque streamlit_app.py, requirements.txt, README.md, .gitignore aqui)

# 3. Fazer commit
git add .
git commit -m "Inicial: Automação SEI-SIGEF com Streamlit"

# 4. Fazer push
git push origin main
```

---

## 🌐 Passo 3: Deploy no Streamlit Cloud (O Mágico!)

1. **Vá para** https://streamlit.io/cloud
2. **Clique em** "New app"
3. **Selecione:**
   - Repositório: `seu-usuario/automacao-sei-sigef`
   - Branch: `main`
   - Main file path: `streamlit_app.py`
4. **Clique em** "Deploy"

**Aguarde 1-2 minutos...**

Pronto! Você terá um link como: `https://automacao-sei-sigef.streamlit.app`

---

## 🔐 Passo 4: Adicionar as Credenciais (Importante!)

1. No seu app Streamlit Cloud, **clique em** "Settings" (engrenagem, canto superior direito)
2. **Clique em** "Secrets"
3. **Cola isso e preenche:**

```
CLAUDE_API_KEY = "sk-ant-sua-chave-aqui"
```

**Onde obter CLAUDE_API_KEY:**
- Vá para https://console.anthropic.com
- Clique em "API Keys"
- Clique em "Create Key"
- Copie a chave (começa com `sk-ant-`)

4. **Clique em** "Save"
5. **Seu app vai reiniciar automaticamente**

---

## ✨ Passo 5: Usar o App!

1. **Clique no link** do seu app: `https://automacao-sei-sigef.streamlit.app`
2. **Preencha os dados** do processo:
   - Número do processo
   - Data da NF-e
   - CNPJ do fornecedor
   - Valor
   - Número do empenho
3. **Clique em** "🔍 Analisar Processo"
4. **Aguarde 3-5 segundos**
5. **Veja o resultado!**

---

## 🎉 Pronto!

Seu app está rodando **24/7 na nuvem** SEM custo algum (até 1 app grátis)!

---

## 💡 Dicas & Troubleshooting

### "Erro: CLAUDE_API_KEY not found"
- Verifique se adicionou no Streamlit Cloud Secrets
- Aguarde 1-2 minutos para o app reiniciar
- Recarregue a página

### "Erro ao conectar com Claude API"
- Verifique se a API Key está correta
- Verifique se você tem crédito na Claude (https://console.anthropic.com)

### "Quero adicionar mais recursos"
Você pode:
- Editar `streamlit_app.py` no GitHub
- O app vai **redeploar automaticamente** quando você fizer commit

---

## 🔄 Atualizar o App

Se você quer adicionar novos recursos:

1. **Edite o arquivo** no GitHub (ou localmente + git push)
2. **O Streamlit Cloud vai detectar** e fazer redeploy automaticamente
3. **Seu app está atualizado!**

---

## 🆓 Custos

- **GitHub**: Grátis
- **Streamlit Cloud**: Grátis (1 app)
- **Claude API**: ~R$ 1-2/mês com análises regulares
- **Total**: Praticamente GRÁTIS! 🚀

---

## 📞 Próximas Fases

Com o app rodando, você pode adicionar:

**Fase 2**: Preenchimento automático do SIGEF
**Fase 3**: Despacho automático para devoluções
**Fase 4**: Dashboard com histórico de análises

---

## ✅ Checklist Final

- [ ] Criei repositório no GitHub
- [ ] Adicionei os 4 arquivos (streamlit_app.py, requirements.txt, README.md, .gitignore)
- [ ] Fiz deploy no Streamlit Cloud
- [ ] Adicionei CLAUDE_API_KEY no Secrets
- [ ] Testei o app com um processo
- [ ] App está rodando! 🎉

---

**Pronto para começar?** [Criar repositório agora](https://github.com/new) 🚀

Se tiver dúvidas, veja o [README.md](README.md) completo ou entre em contato!
