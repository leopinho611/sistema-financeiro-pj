💰 Sistema de Controle Financeiro - PJ/Autônomo
Um aplicativo web que automatiza a categorização de extratos bancários e gera análises visuais para profissionais autônomos e PJs.
🚀 Funcionalidades
✅ Upload de Extratos - Aceita CSV ou XLSX de qualquer banco  
✅ Categorização Automática - 9 categorias principais (Casa, Transporte, Alimentação, etc)  
✅ Análises Visuais - Gráficos interativos com Plotly  
✅ Exportação - Baixa dados categorizados em CSV ou XLSX  
✅ Filtros Inteligentes - Organize e analise por categoria
📋 Categorias Suportadas
🏠 CASA - Aluguel, condomínio, água, luz, gás, internet, etc
🚗 TRANSPORTE - Combustível, Uber, ônibus, estacionamento, etc
🍽️ ALIMENTAÇÃO - Restaurante, mercado, padaria, delivery, etc
💊 SAÚDE - Farmácia, médico, dentista, academia, etc
📚 EDUCAÇÃO - Escola, curso, livros, professor, etc
🎬 LAZER - Cinema, teatro, viagem, hotel, etc
👕 SHOPPING - Roupas, sapatos, loja, etc
💰 INVESTIMENTO - FII, ações, tesouro, cripto, etc
💳 IMPOSTO - IRPF, IRPJ, ICMS, PIS, etc
🛠️ Tech Stack
Frontend: Streamlit
Dados: Pandas, NumPy
Gráficos: Plotly
Excel: openpyxl
Host: Streamlit Cloud (Gratuito)
📦 Como Instalar Localmente
```bash
# Clone o repositório
git clone https://github.com/seu-usuario/sistema-financeiro-pj.git
cd sistema-financeiro-pj

# Instale as dependências
pip install -r requirements.txt

# Execute o app
streamlit run streamlit_app.py
```
O app abrirá em `http://localhost:8501`
🌐 Usando Online
Acesse diretamente em:
https://sistema-financeiro-pj-cfzvrv3ryghyyfppncz97u.streamlit.app/
📱 Como Usar
Exporte seu extrato bancário em CSV ou XLSX
Qualquer banco (Itaú, Bradesco, Santander, Caixa, etc)
Clique em "Importar Dados" na barra lateral
Selecione seu arquivo e aguarde a análise
Veja os resultados:
Resumo com métricas
Gráficos por categoria
Dados detalhados
Exportar dados categorizados
🔒 Privacidade
Seus dados não são salvos no servidor
Tudo é processado no seu navegador
Nenhum terceiro tem acesso aos seus extratos
🎯 Roadmap (Próximas Semanas)
[ ] Integração com Google Drive API (importar extratos automaticamente)
[ ] SQLite para histórico de transações
[ ] Previsões de despesas com ML
[ ] Dashboard temporal (mês a mês)
[ ] Sugestões automáticas de economia
[ ] Relatório PDF automático
📧 Suporte
Dúvidas? Abra uma issue no GitHub ou envie um email.
📄 Licença
MIT License - Veja LICENSE.md
---
Desenvolvido para profissionais autônomos e PJs que querem entender melhor suas finanças.
