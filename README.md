Contas em Dia
**Sistema de Controle Financeiro** · *Seus gastos na palma da mão*
Um aplicativo web que automatiza a categorização de extratos bancários e gera análises visuais para profissionais autônomos e PJs.
🚀 Funcionalidades
✅ Upload de Extratos - Vários arquivos de uma vez (meses e contas diferentes), CSV ou Excel de qualquer banco (detecta separador, acentuação, linhas de título e formato de valor brasileiro; aceita o ".excel" do BB)  
✅ OFX de qualquer banco e extratos em PDF do Nubank, Sicredi e Banco XP (o nome do titular é lido do PDF) - O mesmo mês em mais de um formato (CSV, OFX, PDF) não duplica  
✅ Fatura do cartão BB em PDF - Lê as compras, parcelas e estornos  
✅ Extratos em PDF de BB, Bradesco, Itaú, Santander, Sicoob, Caixa e BNB, faturas Bradesco, Itaú e Sicoob empresariais e as aplicações desses bancos (aplicação automática Itaú, Invest Fácil, CDB ContaMax)  
✅ Itaú SISPAG - O relatório de pagamentos (Excel) detalha o "Sispag" do extrato: quando os pagamentos do dia fecham com o total do extrato, o total dá lugar a cada pagamento (favorecido, CNPJ e tipo)  
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

🚀 Hospedar no Render (uso comercial)
O repositório tem um `Dockerfile` (com o OCR do tesseract) e o `iniciar.sh`.
1. Render → New → Web Service → conecte este repositório, branch `main`. O Render detecta o
   Dockerfile (Language: Docker). Plano Starter ou acima (o gratuito dorme sem uso).
2. Environment → Secret Files → arquivo `secrets.toml` com o mesmo conteúdo dos Secrets do
   Streamlit Cloud, mais `ENDERECO_APP = "https://seu-dominio/"` (link do botão Compartilhar).
3. Settings → Custom Domains → acrescente o domínio e copie os registros DNS para o
   Registro.br. O https é ativado sozinho.
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
- **Medição de uso (anônima):** cada visita recebe um código aleatório e o app anota só o uso:
  aparelho (celular/computador), de onde veio o link (`?utm_source=`), páginas e abas abertas,
  formato e banco de cada arquivo e se foi lido (ou o tipo do erro), exportações, cliques no
  Plus e um aviso a cada 30 segundos enquanto a página está aberta. **Nunca** valores, descrições,
  fornecedores, nome do titular, nome do arquivo ou IP. Veja "📈 Medição de uso" abaixo.
📈 Medição de uso
Abra o app com `?admin=1`, entre com a senha e veja a aba **📈 Uso do app**: quantas visitas,
até onde chegam (entrou → enviou extrato → viu o painel → abriu outra aba → exportou ou foi
ao Plus), **onde pararam** (a última página ou aba antes de fechar), quais formatos e bancos
deram erro de leitura, de onde vieram as visitas e o caminho de cada visita. O tempo de uso
vem de um aviso a cada 30 segundos enquanto a página está aberta: quando os avisos param, a pessoa
fechou. Visitas de menos de 30 segundos sem nenhum clique não contam (assim a recarga
automática do tema, na primeira visita, não vira uma visita a mais). As suas visitas como
administrador não contam.

Sem configuração, os eventos ficam na memória do servidor e somem quando ele reinicia (no
Render, a cada atualização). Para guardar de vez, use o Supabase (gratuito):
1. Crie um projeto em https://supabase.com → **SQL Editor** → rode:
```sql
create table eventos (
  id bigint generated always as identity primary key,
  momento timestamptz not null default now(),
  sessao text not null,
  evento text not null,
  dados jsonb not null default '{}'
);
create index eventos_momento on eventos (momento);
alter table eventos enable row level security;   -- sem políticas: só a chave do servidor acessa
```
2. Botão **Connect** (ou **Project Settings → API Keys**): copie a *Project URL* e a chave
   secreta, `sb_secret_...` (ou, em projetos antigos, a **service_role** `eyJ...`). Ela é
   secreta: fica só nos segredos do servidor, nunca no navegador.
3. Nos segredos do app (Render → Secret Files `secrets.toml`, ou Streamlit Cloud → Secrets):
```
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_CHAVE = "sb_secret_..."   # ou a service_role "eyJ..."; SUPABASE_SECRET_KEY também vale
CLARITY_ID = ""               # opcional, veja abaixo
```
Nos links de divulgação, acrescente a origem: `https://suascontasemdia.com.br/?utm_source=instagram`
(ou `whatsapp`, `tiktok`, `linkedin`...). Ela aparece em "De onde vêm".

**Gravação de sessão (opcional):** com `CLARITY_ID` (o código do projeto em
https://clarity.microsoft.com), o Microsoft Clarity grava a navegação (cliques, rolagem,
cliques repetidos de frustração). O app marca a página inteira com `data-clarity-mask`, então
todo o texto aparece escondido na gravação; deixe também **Settings → Masking → Strict** no
Clarity. Com o Clarity ligado, a pergunta "Meus dados ficam guardados?" da ajuda passa a citar
a gravação.

🔎 Google e prévia de links
O Streamlit entrega sempre o mesmo `index.html`, com título "Streamlit" e o corpo vazio (a
tela vem depois, pelo JavaScript). No build do Docker, `site/aplicar.py` troca nesse arquivo o
título, a descrição, as tags de prévia (WhatsApp, Instagram, LinkedIn) e coloca um texto sobre
o app no lugar do corpo vazio, que o próprio app substitui ao abrir. Também publica
`robots.txt`, `sitemap.xml` e `previa.png` (a imagem da prévia) na raiz do endereço. Para mudar
os textos, edite `site/cabecalho.html` e `site/conteudo.html`.

Depois de publicar, no [Google Search Console](https://search.google.com/search-console):
adicione a propriedade **Domínio** `suascontasemdia.com.br`, confirme com o registro TXT no
Registro.br, envie o sitemap (`https://suascontasemdia.com.br/sitemap.xml`) e, em **Inspeção
de URL**, peça a indexação da página inicial.

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
