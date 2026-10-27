Contas em Dia
**Sistema de Controle Financeiro** · *Seus gastos na palma da mão*
Um aplicativo web que automatiza a categorização de extratos bancários e gera análises visuais para profissionais autônomos e PJs.
🚀 Funcionalidades
✅ Upload de Extratos - Vários arquivos de uma vez (meses e contas diferentes), CSV ou Excel de qualquer banco (detecta separador, acentuação, linhas de título e formato de valor brasileiro; aceita o ".excel" do BB)  
✅ OFX de qualquer banco e extratos em PDF do Nubank, Sicredi e Banco XP (o nome do titular é lido do PDF) - O mesmo mês em mais de um formato (CSV, OFX, PDF) não duplica  
✅ Fatura do cartão BB em PDF - Lê as compras, parcelas e estornos  
✅ Extratos em PDF de BB, Bradesco, Itaú, Santander, Sicoob, Caixa e BNB, faturas Bradesco, Itaú e Sicoob empresariais e as aplicações desses bancos (aplicação automática Itaú, Invest Fácil, CDB ContaMax)  
✅ PDF sem texto (escaneado, ou com as letras viradas desenho na impressão) - Lido por OCR quando o layout é conhecido (hoje o BNB), com os valores conferidos pelo saldo de cada linha. No Streamlit Cloud, o OCR vem do `packages.txt` (tesseract e poppler)  
✅ Movimentações internas - Aplicação/resgate automático (BB Rende Fácil, caixinhas Nubank), transferência entre suas contas e pagamento de fatura não contam como entrada nem saída  
✅ Identificação automática das colunas - Data, descrição, valor ou crédito/débito (ajustável na tela)  
✅ Categorização Automática - 11 categorias de saída + RECEITA para entradas  
✅ Painel - Resumo (entradas, saídas, saldo e aplicado; entrou e saiu mês a mês; "de onde vem" e "para onde vai"), Entradas e Saídas com escolha das categorias e detalhe por categoria → subcategoria → fornecedor/cliente  
✅ Entradas - Por mês e por tipo (recebido de empresas, de pessoas, salário, rendimentos, estornos), com as fontes que mais pagaram  
✅ Saídas - Por categoria, subcategoria e fornecedor  
✅ Subcategorias e fornecedores - Clique numa categoria para abrir, na própria linha, as subcategorias e os 10 maiores fornecedores de cada uma (o resto em "Outros fornecedores")  
✅ Mês a Mês - Entradas × saídas e categorias por mês  
✅ Tema escuro (padrão) ou claro - Azul-marinho, ciano, dourado e branco-osso; troque em ⋮ no canto superior direito  
✅ Exportação - CSV (padrão Excel brasileiro) ou XLSX com abas de resumo  
✅ Filtros - Contas e categorias em botões (marcar e desmarcar), período, e busca na descrição  
✅ CNPJ automático - Pix para empresas: ao enviar os extratos, o app consulta a atividade na Receita (dados públicos) e já classifica pelo CNAE; a revisão fica em Transações (vale até fechar o app; no Plus, pode lembrar)  

⭐ Área Plus (com código de acesso)
⭐ Relatório em PDF - 4 páginas em linguagem simples: nota geral, destaques, mês a mês e aplicações, para onde foi o dinheiro (categoria → subcategoria → maiores gastos), o que já está comprometido, pontos de atenção, prévia do IR, próximos passos e o que falta enviar para o relatório ficar mais completo. Na área aberta há um exemplo com dados fictícios para baixar  
⭐ Imposto de Renda - Possíveis deduções (saúde, educação, PGBL, pensão) com o CNPJ de quem recebeu, rendimentos de empresas e de pessoas; planilha para o contador  
⭐ Fixos e parcelas - Gastos que se repetem (valor fixo, conta mensal, frequente) com a data prevista do próximo; parcelas do cartão que ainda faltam, quanto e até quando  
⭐ Saúde financeira - Indicadores com semáforo: quanto sobra, meses no vermelho, dependência da maior fonte, compromissos, parcelas e reserva de emergência  
⭐ Classificar - Corrija a categoria por fornecedor e o app lembra nas próximas vezes
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
🧾 SERVIÇOS DE TERCEIROS - Consultoria, assessoria, contabilidade, advocacia, etc; e o que não foi identificado (subcategoria "Não identificados")
🏦 TARIFAS BANCÁRIAS - Tarifas, IOF, juros, anuidade, etc
🔁 TRANSFERÊNCIA - PIX, TED, DOC sem outra categoria identificada
💵 RECEITA - Todas as entradas
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
⭐ Área Plus
A área Plus abre com um código de acesso assinado, com validade e vinculado ao titular.
No Streamlit Cloud: app → Settings → Secrets:
```
PLUS_CHAVE = "..."          # chave que assina os códigos (a página de administração sugere uma)
ADMIN_SENHA = "..."         # senha da página de administração
PLUS_LINK = "https://..."   # link de pagamento ("Assinar área Plus")
CONTATO_CONSULTORIA = "https://wa.me/..."   # opcional: botão "Falar com um especialista"
CONTATO_EMAIL = "..."       # opcional: e-mail de atendimento (assinatura e "Reportar um problema")
PLUS_PRECO = "R$ 19,90 por mês"   # opcional: texto do preço na janela de assinatura
PLUS_BLOQUEADOS = ""        # opcional: códigos cancelados (as 4 letras do meio, por vírgula)
PLUS_CODIGOS = ["teste"]    # opcional: códigos fixos, sem validade (testes e cortesias)
```
**Venda:** em "⭐ Assinar área Plus" a pessoa paga pelo link e manda o comprovante, com o
nome do titular, pelo WhatsApp ou e-mail (mensagem já escrita). Quando o pagamento cai, abra o app com `?admin=1` no fim
do endereço, entre com a senha, informe o nome completo do titular e a validade, e envie o
código gerado no mesmo chat. O app não guarda nada: confere a assinatura, a validade e o nome na hora.
O código só funciona com o nome do titular, e o Plus é bloqueado quando um extrato em PDF
mostra outro titular. Não troque a `PLUS_CHAVE` depois de vender: os códigos deixariam de valer.

🏷️ Regras compartilhadas (o app lembra)
Na página "⭐ Classificar" você corrige a categoria de um fornecedor e o app passa a usar essa
categoria em todos os lançamentos dele, nos próximos extratos também. Fornecedores com CNPJ
no extrato podem ser consultados na Receita Federal (BrasilAPI, gratuita): o app sugere a
categoria pelo CNAE principal e você confirma antes de aplicar.

- **Empresas** (compra no cartão, boleto, débito ou CNPJ) vão para `regras/regras_fornecedores.csv`,
  compartilhado por todos que usam o app.
- **Pix para pessoas** ficam só nas suas regras pessoais, para não expor nomes de ninguém
  (o repositório é público). Para guardar de vez, cole-as no segredo `REGRAS_PESSOAIS` (a página
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
- **Extratos:** são enviados ao servidor do app (Streamlit Community Cloud) e processados
  **só na memória**, enquanto a página está aberta. O app não grava os extratos em disco nem
  em banco de dados; ao fechar a página (ou depois de um tempo sem uso), tudo é descartado.
- **O que fica guardado são só as regras de categoria** (nome do fornecedor → categoria),
  sem valores nem datas:
  - empresas: em `regras/regras_fornecedores.csv`, neste repositório (público);
  - pessoas (Pix, MEI): só no segredo `REGRAS_PESSOAIS`, que apenas o dono do app vê.
- **Consulta de CNPJ:** quando você clica no botão, só o CNPJ é enviado à BrasilAPI. Na
  área aberta, o resultado vale só até fechar o app; só a classificação do Plus grava regras.
- **Área Plus:** os relatórios são calculados na hora, a partir dos extratos abertos. O valor
  "quanto você tem guardado" não é salvo.
- O app não usa inteligência artificial nem envia extratos a terceiros.
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
