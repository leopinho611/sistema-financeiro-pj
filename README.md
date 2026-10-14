Sistema de Controle Financeiro
*Seus gastos na palma da mão*
Um aplicativo web que automatiza a categorização de extratos bancários e gera análises visuais para profissionais autônomos e PJs.
🚀 Funcionalidades
✅ Upload de Extratos - Vários arquivos de uma vez (meses e contas diferentes), CSV ou Excel de qualquer banco (detecta separador, acentuação, linhas de título e formato de valor brasileiro; aceita o ".excel" do BB)  
✅ Fatura do cartão BB em PDF - Lê as compras, parcelas e estornos  
✅ Movimentações internas - Aplicação/resgate automático (BB Rende Fácil, caixinhas Nubank), transferência entre suas contas e pagamento de fatura não contam como entrada nem saída  
✅ Identificação automática das colunas - Data, descrição, valor ou crédito/débito (ajustável na tela)  
✅ Categorização Automática - 11 categorias de saída + RECEITA para entradas  
✅ Resumo em R$ - Entradas, saídas, saldo e gastos por categoria  
✅ Fornecedores - Clique numa categoria para abrir, na própria linha, os 10 maiores fornecedores (o resto em "Outros fornecedores")  
✅ Mês a Mês - Entradas × saídas e categorias por mês  
✅ Tema claro ou escuro - Azul-marinho, dourado e branco-osso; troque em ⋮ → Settings (por padrão segue o aparelho)  
✅ Exportação - CSV (padrão Excel brasileiro) ou XLSX com abas de resumo  
✅ Filtros - Por conta, período, categoria e busca na descrição
📋 Categorias Suportadas
🏠 CASA - Aluguel, condomínio, água, luz, gás, internet, etc
🚗 TRANSPORTE - Combustível, Uber, ônibus, estacionamento, etc
🍽️ ALIMENTAÇÃO - Restaurante, mercado, padaria, delivery, etc
💊 SAÚDE - Farmácia, médico, dentista, academia, etc
📚 EDUCAÇÃO - Escola, curso, livros, professor, etc
🎬 LAZER - Cinema, teatro, viagem, hotel, etc
👕 SHOPPING - Roupas, sapatos, loja, etc
💳 IMPOSTOS E TAXAS - IRPF, DARF, Simples Nacional, SEFAZ, Prefeitura, GRU, etc
📺 ASSINATURAS - Netflix, Spotify, Claude, etc
🏦 TARIFAS BANCÁRIAS - Tarifas, IOF, juros, anuidade, etc
🔁 TRANSFERÊNCIA - PIX, TED, DOC sem outra categoria identificada
💵 RECEITA - Todas as entradas
❓ OUTRO - O que não foi identificado
🔄 Movimentações internas (fora de entradas e saídas): APLICAÇÃO/RESGATE, TRANSFERÊNCIA ENTRE CONTAS, PAGAMENTO DE FATURA
🛠️ Tech Stack
Frontend: Streamlit
Dados: Pandas, NumPy
Gráficos: Altair (incluso no Streamlit)
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

Para rodar os testes: `pip install pytest` e depois `pytest`
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
[x] Dashboard temporal (mês a mês)
[ ] Sugestões automáticas de economia
[ ] Relatório PDF automático
📧 Suporte
Dúvidas? Abra uma issue no GitHub ou envie um email.
📄 Licença
MIT License - Veja LICENSE.md
---
Desenvolvido para profissionais autônomos e PJs que querem entender melhor suas finanças.
