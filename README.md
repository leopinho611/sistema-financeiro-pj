Sistema de Controle Financeiro
*Seus gastos na palma da mão*
Um aplicativo web que automatiza a categorização de extratos bancários e gera análises visuais para profissionais autônomos e PJs.
🚀 Funcionalidades
✅ Upload de Extratos - Vários arquivos de uma vez (meses e contas diferentes), CSV ou Excel de qualquer banco (detecta separador, acentuação, linhas de título e formato de valor brasileiro; aceita o ".excel" do BB)  
✅ OFX de qualquer banco e extrato Nubank em PDF - O mesmo mês em mais de um formato (CSV, OFX, PDF) não duplica  
✅ Fatura do cartão BB em PDF - Lê as compras, parcelas e estornos  
✅ Movimentações internas - Aplicação/resgate automático (BB Rende Fácil, caixinhas Nubank), transferência entre suas contas e pagamento de fatura não contam como entrada nem saída  
✅ Identificação automática das colunas - Data, descrição, valor ou crédito/débito (ajustável na tela)  
✅ Categorização Automática - 11 categorias de saída + RECEITA para entradas  
✅ Resumo em R$ - Entradas, saídas, saldo e gastos por categoria  
✅ Subcategorias e fornecedores - Clique numa categoria para abrir, na própria linha, as subcategorias e os 10 maiores fornecedores de cada uma (o resto em "Outros fornecedores")  
✅ Mês a Mês - Entradas × saídas e categorias por mês  
✅ Tema claro ou escuro - Azul-marinho, dourado e branco-osso; troque em ⋮ → Settings (por padrão segue o aparelho)  
✅ Exportação - CSV (padrão Excel brasileiro) ou XLSX com abas de resumo  
✅ Filtros - Por conta, período, categoria e busca na descrição  
✅ Classificar - Corrija a categoria por fornecedor e o app lembra; consulta de CNPJ na Receita com sugestão pelo CNAE
📋 Categorias Suportadas
Subcategorias: ALIMENTAÇÃO (Supermercado, Restaurante, Padaria, Hortifruti e açougue), SAÚDE (Drogaria, Plano de saúde, Academia, Cuidados pessoais, Clínicas e consultas), TRANSPORTE (Posto de gasolina, Seguro, Transporte por aplicativo, Estacionamento, IPVA e multas), CASA (Água, Luz, Internet, Gás, Condomínio, Aluguel, Telefone e celular, Manutenções), SHOPPING (Compras online, Vestuário, Infantil), LAZER (Viagens, Passeios e eventos), IMPOSTOS E TAXAS (Federais, Estaduais, Municipais, Conselho profissional), TARIFAS BANCÁRIAS (Anuidade do cartão, Pacote de serviços, IOF e juros); o que não se encaixa fica em "Outros"
🏠 CASA - Aluguel, condomínio, água, luz, gás, internet, etc
🚗 TRANSPORTE - Combustível, Uber, ônibus, estacionamento, etc
🍽️ ALIMENTAÇÃO - Restaurante, mercado, padaria, delivery, etc
💊 SAÚDE - Farmácia, médico, dentista, academia, etc
📚 EDUCAÇÃO - Escola, curso, livros, professor, etc
🎬 LAZER - Cinema, teatro, viagem, hotel, etc
👕 SHOPPING - Roupas, sapatos, loja, etc
💳 IMPOSTOS E TAXAS - IRPF, DARF, Simples Nacional, SEFAZ, Prefeitura, GRU, etc
📺 ASSINATURAS - Netflix, Spotify, Claude, etc
🧾 SERVIÇOS - Consultoria, assessoria, contabilidade, etc
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
🏷️ Regras compartilhadas (o app lembra)
Na aba "Classificar" você corrige a categoria de um fornecedor e o app passa a usar essa
categoria em todos os lançamentos dele, nos próximos extratos também. Fornecedores com CNPJ
no extrato podem ser consultados na Receita Federal (BrasilAPI, gratuita): o app sugere a
categoria pelo CNAE principal e você confirma antes de aplicar.

- **Empresas** (compra no cartão, boleto, débito ou CNPJ) vão para `regras/regras_fornecedores.csv`,
  compartilhado por todos que usam o app.
- **Pix para pessoas** ficam só nas suas regras pessoais, para não expor nomes de ninguém
  (o repositório é público). Para guardar de vez, cole-as no segredo `REGRAS_PESSOAIS` (a aba
  Classificar gera o texto pronto); elas passam a valer sempre, mas não são exibidas no app.

Para as regras compartilhadas serem gravadas de vez a partir do Streamlit Cloud:
1. Crie um token em https://github.com/settings/personal-access-tokens/new
   - Repository access: *Only select repositories* → este repositório
   - Permissions → Repository permissions → **Contents: Read and write**
2. No Streamlit Cloud: app → Settings → Secrets, acrescente:
```
GITHUB_TOKEN = "github_pat_..."
GITHUB_REPO = "seu-usuario/sistema-financeiro-pj"
GITHUB_BRANCH = "main"
```
Cada regra salva vira um commit no repositório: dá para ver quem mudou o quê e desfazer.
Sem o token, as regras novas valem até o app reiniciar.

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
