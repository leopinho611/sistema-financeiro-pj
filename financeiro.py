"""
Leitura, limpeza e categorização de extratos bancários.

Separado da interface (streamlit_app.py) para poder ser testado sem o Streamlit.
"""

import io
import re
import unicodedata
import warnings

import pandas as pd
from pypdf import PdfReader

# ============================================================================
# CATEGORIAS
# ============================================================================
# A ordem importa: a primeira categoria que casar vence. TRANSFERÊNCIA fica por
# último porque "PIX RESTAURANTE X" deve cair em ALIMENTAÇÃO, não em transferência.
# Palavras sem acento e em minúsculas; casam como palavra inteira (com plural "s").
# Terminada em "*", casa com o começo da palavra: "amazon*" pega "AMAZONMKTPLC".
CATEGORIAS = {
    "CASA": ["aluguel", "condominio", "agua", "luz", "energia", "cosern", "caern",
             "gas", "internet", "telefone", "celular", "claro", "vivo", "tim",
             "leroy merlin", "ferreira cost*", "tok stok", "casas bahia"],
    "TRANSPORTE": ["combustivel", "gasolina", "etanol", "posto*", "estacionamento",
                   "uber*", "99 ride", "99app", "onibus", "pedagio", "ipva", "detran",
                   "shell", "ipiranga", "youse", "seguro auto"],
    "ALIMENTAÇÃO": ["restaurante", "lanchonete", "comida", "mercado", "supermercado",
                    "padaria", "panificadora", "pao", "delivery", "ifood", "rappi",
                    "acougue", "carnes", "frios", "hortifruti", "sacolao", "nordestao",
                    "carrefour", "atacadao", "assai", "favorito", "pizzaria", "bolo",
                    "camaroes", "queijo", "gelateria", "sorveteria", "crepe*", "cafe",
                    "cafeteria", "burger*", "hamburgueria"],
    "SAÚDE": ["farmacia", "drogaria", "pague menos", "drogasil", "raia", "medico",
              "clinica", "dentista", "hospital", "laboratorio", "academia", "wellhub",
              "gympass", "unimed", "hapvida", "plano de saude", "barbearia", "estetica"],
    "EDUCAÇÃO": ["escola", "faculdade", "universidade", "curso", "livro", "livraria",
                 "papelaria", "papelpapelar*"],
    "ASSINATURAS": ["netflix", "spotify", "anthropic*", "claude", "openai", "chatgpt",
                    "youtube", "disney*", "hbo", "prime video", "globoplay",
                    "deezer", "apple com", "icloud", "google one", "microsoft", "adobe"],
    "LAZER": ["cinema", "teatro", "show", "viagem", "hotel", "airbnb", "booking",
              "ingresso", "gol linhas", "latam", "azul linhas", "zupper", "decolar",
              "aquario"],
    "SHOPPING": ["roupa", "sapato", "loja", "lojas", "vestuario", "shopping", "magazine",
                 "amazon*", "mercadolivre", "mercado livre", "shopee", "shein",
                 "renner", "riachuelo", "baby"],
    "IMPOSTOS E TAXAS": ["irpf", "irpj", "icms", "pis", "cofins", "iss", "inss", "darf",
                         "gps", "csll", "simples nacional", "gru", "sefaz", "pref mun",
                         "prefeitura", "receita federal", "rfb", "iptu",
                         "conselho regional"],
    "TARIFAS BANCÁRIAS": ["tarifa", "iof", "juros", "anuidade", "cesta", "encargo",
                          "multa"],
    "TRANSFERÊNCIA": ["pix", "ted", "doc", "transferencia", "transf"],
}
CATEGORIA_ENTRADA = "RECEITA"
CATEGORIA_PADRAO = "OUTRO"
CATEGORIA_ESTORNO = "ESTORNO"
CATEGORIA_CARTAO = "CARTÃO DE CRÉDITO"   # pagamento de fatura quando a fatura não foi importada

# Movimentações internas: o dinheiro continua seu, só muda de lugar.
# Não contam como entrada nem saída.
CATEGORIA_APLICACAO = "APLICAÇÃO/RESGATE"
CATEGORIA_FATURA = "PAGAMENTO DE FATURA"
CATEGORIA_ENTRE_CONTAS = "TRANSFERÊNCIA ENTRE CONTAS"
CATEGORIAS_INTERNAS = {CATEGORIA_APLICACAO, CATEGORIA_FATURA, CATEGORIA_ENTRE_CONTAS}

PALAVRAS_APLICACAO = ["rende facil", "rdb", "nu reserva", "valor mensal programado",
                      "caixinha", "poupanca", "aplicacao", "resgate", "fii", "acao",
                      "acoes", "tesouro", "cdb", "lci", "lca", "corretora", "bitcoin"]
PALAVRAS_FATURA = ["pagto cartao", "pagamento de fatura", "pagamento fatura",
                   "pgto fatura", "fatura do cartao", "fatura cartao"]
PADRAO_TRANSFERENCIA = re.compile(r"\b(?:pix|ted|doc|transf|transferencia)")

# Linhas de saldo não são transações (aparecem em quase todo extrato brasileiro;
# o BB escreve "S A L D O", por isso a comparação também é feita sem espaços)
PADRAO_SALDO = re.compile(r"\bsaldo\b")


def eh_linha_de_saldo(descricao):
    texto = normalizar(descricao)
    return bool(PADRAO_SALDO.search(texto)) or texto.replace(" ", "").startswith("saldo")


def normalizar(texto):
    """Minúsculas, sem acentos e com espaços simples."""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[.&*@/]", " ", sem_acento.lower())).strip()


def _padrao(palavras):
    partes = [re.escape(p[:-1]) + r"\w*" if p.endswith("*") else re.escape(p) + r"s?\b"
              for p in palavras]
    return re.compile(r"\b(?:" + "|".join(partes) + r")")


_PADROES = {categoria: _padrao(palavras) for categoria, palavras in CATEGORIAS.items()}
_PADRAO_APLICACAO = _padrao(PALAVRAS_APLICACAO)
_PADRAO_FATURA = _padrao(PALAVRAS_FATURA)


def categorizar(descricao, valor=None):
    """Categoria de uma transação. Entradas (valor > 0) viram RECEITA.

    Aplicações/resgates e pagamento de fatura são identificados primeiro,
    nos dois sentidos, porque são movimentações internas.
    """
    texto = normalizar(descricao)
    if _PADRAO_APLICACAO.search(texto):
        return CATEGORIA_APLICACAO
    if _PADRAO_FATURA.search(texto):
        return CATEGORIA_FATURA
    if valor is not None and valor > 0:
        return CATEGORIA_ENTRADA
    for categoria, padrao in _PADROES.items():
        if padrao.search(texto):
            return categoria
    return CATEGORIA_PADRAO


# ============================================================================
# LEITURA DO ARQUIVO
# ============================================================================
_NOMES_DATA = ("data", "dt ", "dt.", "date")
_NOMES_DESCRICAO = ("descri", "histor", "lancamento", "estabelecimento", "detalhe",
                    "memo", "titulo")
_NOMES_VALOR = ("valor", "quantia", "montante", "amount")
_NOMES_CREDITO = ("credito", "entrada")
_NOMES_DEBITO = ("debito", "saida")


def _eh_cabecalho(celulas):
    """Linha parece cabeçalho se tem 'data' e algo de descrição ou valor."""
    textos = [normalizar(c) for c in celulas if isinstance(c, str)]
    tem_data = any(t.startswith("data") or t in ("dt", "date") for t in textos)
    tem_outro = any(t.startswith(_NOMES_DESCRICAO + _NOMES_VALOR + _NOMES_CREDITO + _NOMES_DEBITO)
                    for t in textos)
    return tem_data and tem_outro


def _aplicar_cabecalho(bruto):
    """Bancos costumam pôr linhas de título antes do cabeçalho: procura a linha certa."""
    for i in range(min(len(bruto), 30)):
        if _eh_cabecalho(bruto.iloc[i].tolist()):
            df = bruto.iloc[i + 1:].copy()
            nomes = [str(c).strip() if pd.notna(c) else f"coluna_{j + 1}"
                     for j, c in enumerate(bruto.iloc[i])]
            df.columns = _nomes_unicos(nomes)
            return df.dropna(how="all").reset_index(drop=True)
    # Sem cabeçalho reconhecível: usa a primeira linha
    df = bruto.iloc[1:].copy()
    df.columns = _nomes_unicos([str(c) for c in bruto.iloc[0]])
    return df.dropna(how="all").reset_index(drop=True)


def _nomes_unicos(nomes):
    vistos = {}
    saida = []
    for n in nomes:
        if n in vistos:
            vistos[n] += 1
            saida.append(f"{n}_{vistos[n]}")
        else:
            vistos[n] = 0
            saida.append(n)
    return saida


def ler_extrato(nome, conteudo):
    """Lê CSV ou XLSX de qualquer banco e devolve um DataFrame com o cabeçalho certo."""
    if nome.lower().endswith((".xlsx", ".xls", ".excel")) or conteudo[:2] == b"PK":
        # O BB exporta XLSX com extensão ".excel"; XLSX sempre começa com "PK"
        with warnings.catch_warnings():
            # O Excel do BB não tem estilo padrão; o aviso do openpyxl é inofensivo
            warnings.simplefilter("ignore", UserWarning)
            bruto = pd.read_excel(io.BytesIO(conteudo), header=None, dtype=object,
                                  engine="openpyxl")
    else:
        try:
            texto = conteudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1")  # padrão de vários bancos brasileiros
        # Separador: o que aparece mais vezes numa mesma linha entre as primeiras
        amostra = texto.splitlines()[:30]
        separador = max([";", ",", "\t", "|"],
                        key=lambda s: max((l.count(s) for l in amostra), default=0))
        bruto = pd.read_csv(io.StringIO(texto), sep=separador, header=None, dtype=str,
                            engine="python", skip_blank_lines=True, on_bad_lines="skip")
    if bruto.empty:
        raise ValueError("O arquivo está vazio.")
    return _aplicar_cabecalho(bruto)


# ============================================================================
# CONVERSÃO DE VALORES E DATAS
# ============================================================================
def converter_valor(v):
    """Converte '1.234,56', 'R$ -10,00', '(50,00)', '123,45 D', 1234.5 em float."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None

    negativo = False
    # Sufixo de débito/crédito usado por alguns bancos: "123,45 D", "123,45 C", "123,45-"
    sufixo = re.fullmatch(r"(.*?)\s*([DdCc-])", s)
    if sufixo and re.search(r"\d", sufixo.group(1)):
        s = sufixo.group(1)
        negativo = sufixo.group(2) in "Dd-"
    if s.startswith("(") and s.endswith(")"):
        negativo, s = True, s[1:-1]
    s = s.replace("R$", "").replace(" ", "").replace(" ", "")
    if s.startswith("-"):
        negativo, s = True, s[1:]
    elif s.startswith("+"):
        s = s[1:]

    if "," in s and "." in s:
        # O separador que aparece por último é o decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")  # 1.234 = mil duzentos e trinta e quatro

    try:
        numero = float(s)
    except ValueError:
        return None
    return -numero if negativo else numero


def converter_datas(serie):
    """Datas em dd/mm/aaaa (padrão brasileiro), aaaa-mm-dd ou datas do Excel."""
    def uma(v):
        if isinstance(v, pd.Timestamp):
            return v
        if hasattr(v, "year"):  # datetime/date vindo do Excel
            return pd.Timestamp(v)
        s = str(v).strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", s):
            return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")
        return pd.to_datetime(s, dayfirst=True, errors="coerce")
    return serie.map(uma)


# ============================================================================
# IDENTIFICAÇÃO DAS COLUNAS
# ============================================================================
def _casa(coluna, prefixo):
    n = normalizar(coluna)
    return n.startswith(prefixo) or f" {prefixo}" in f" {n}"


def _procura(colunas, prefixos, exceto=()):
    """Primeira coluna que casa, respeitando a ordem de prioridade dos prefixos."""
    for p in prefixos:
        for c in colunas:
            if c not in exceto and _casa(c, p):
                return c
    return None


def detectar_colunas(df):
    """Sugere quais colunas são data, descrição (lista), valor (ou crédito/débito)."""
    colunas = list(df.columns)
    data = _procura(colunas, _NOMES_DATA)
    if data is None:
        # Coluna onde a maioria das linhas vira data
        for c in colunas:
            if converter_datas(df[c].head(20)).notna().mean() > 0.8:
                data = c
                break

    credito = _procura(colunas, _NOMES_CREDITO, exceto=(data,))
    debito = _procura(colunas, _NOMES_DEBITO, exceto=(data, credito))
    valor = _procura(colunas, _NOMES_VALOR, exceto=(data, credito, debito))
    if valor is None and not (credito and debito):
        for c in colunas:
            if c == data:
                continue
            if df[c].head(20).map(converter_valor).notna().mean() > 0.8:
                valor = c
                break

    # Descrição pode ocupar mais de uma coluna (BB: "Lançamento" + "Detalhes")
    usadas = (data, valor, credito, debito)
    # (só nomes que COMEÇAM com a palavra: "Tipo Lançamento" não é descrição)
    descricao = [c for p in _NOMES_DESCRICAO for c in colunas
                 if c not in usadas and normalizar(c).startswith(p)]
    descricao = list(dict.fromkeys(descricao))  # sem repetir, na ordem de prioridade
    if not descricao:
        # Coluna de texto mais longa
        candidatas = [c for c in colunas if c not in usadas]
        if candidatas:
            descricao = [max(candidatas, key=lambda c: df[c].astype(str).str.len().mean())]

    usa_credito_debito = valor is None and credito is not None and debito is not None
    return {
        "data": data,
        "descricao": descricao,
        "valor": None if usa_credito_debito else valor,
        "credito": credito if usa_credito_debito else None,
        "debito": debito if usa_credito_debito else None,
    }


# ============================================================================
# MONTAGEM DAS TRANSAÇÕES
# ============================================================================
def definir_tipo(categoria, valor):
    if categoria in CATEGORIAS_INTERNAS:
        return "Interna"
    return "Entrada" if valor > 0 else "Saída"


def montar_transacoes(df, colunas, conta=""):
    """Gera a tabela padronizada: Data, Descrição, Valor, Tipo, Categoria, Conta, Mês."""
    if not colunas.get("data") or not colunas.get("descricao"):
        raise ValueError("Escolha as colunas de data e de descrição.")

    if colunas.get("valor"):
        valores = df[colunas["valor"]].map(converter_valor)
    elif colunas.get("credito") and colunas.get("debito"):
        cred = df[colunas["credito"]].map(converter_valor).fillna(0).abs()
        deb = df[colunas["debito"]].map(converter_valor).fillna(0).abs()
        valores = cred - deb
        valores[(df[colunas["credito"]].isna()) & (df[colunas["debito"]].isna())] = None
    else:
        raise ValueError("Escolha a coluna de valor (ou as de crédito e débito).")

    t = pd.DataFrame({
        "Data": converter_datas(df[colunas["data"]]),
        "Descrição": df[colunas["descricao"]].fillna("").astype(str).apply(
            lambda linha: " - ".join(v.strip() for v in linha if v.strip()), axis=1),
        "Valor": pd.to_numeric(valores, errors="coerce"),
    })
    t = t.dropna(subset=["Data", "Valor"])
    t = t[t["Valor"] != 0]
    t = t[~t["Descrição"].map(eh_linha_de_saldo)]

    t["Categoria"] = [categorizar(d, v) for d, v in zip(t["Descrição"], t["Valor"])]
    t["Tipo"] = [definir_tipo(c, v) for c, v in zip(t["Categoria"], t["Valor"])]
    t["Conta"] = conta
    t["Mês"] = t["Data"].dt.to_period("M").astype(str)
    return t.sort_values("Data").reset_index(drop=True)


def resumo_categorias(t):
    """Total de saídas por categoria (valores positivos), do maior para o menor."""
    saidas = t[t["Tipo"] == "Saída"]
    tabela = (saidas.groupby("Categoria")["Valor"].agg(["sum", "count"])
              .rename(columns={"sum": "Total", "count": "Transações"}))
    tabela["Total"] = -tabela["Total"]
    total = tabela["Total"].sum()
    tabela["% das saídas"] = (tabela["Total"] / total * 100) if total else 0
    return tabela.sort_values("Total", ascending=False).reset_index()


def resumo_mensal(t):
    """Entradas, saídas e saldo por mês."""
    entradas = t[t["Tipo"] == "Entrada"].groupby("Mês")["Valor"].sum()
    saidas = -t[t["Tipo"] == "Saída"].groupby("Mês")["Valor"].sum()
    tabela = pd.DataFrame({"Entradas": entradas, "Saídas": saidas}).fillna(0)
    tabela["Saldo"] = tabela["Entradas"] - tabela["Saídas"]
    return tabela.sort_index().reset_index().rename(columns={"index": "Mês"})


# ============================================================================
# FATURA DE CARTÃO DO BB (PDF)
# ============================================================================
# Seções da fatura do BB que já dizem a categoria
SECOES_FATURA_BB = {
    "supermercados": "ALIMENTAÇÃO",
    "restaurantes": "ALIMENTAÇÃO",
    "transporte": "TRANSPORTE",
    "vestuario": "SHOPPING",
    "viagens": "LAZER",
    "lazer": "LAZER",
    "saude": "SAÚDE",
    "educacao": "EDUCAÇÃO",
}
_LINHA_FATURA = re.compile(r"^(\d{2})/(\d{2})\s+(.+?)\s+R\$\s*(-?[\d.]+,\d{2})\s*$")


def eh_fatura_bb(texto):
    return "Lançamentos nesta fatura" in texto and "Total da Fatura" in texto


def ler_fatura_bb(texto, conta="BB Cartão"):
    """Lê as compras de uma fatura do cartão BB (texto extraído do PDF).

    O pagamento da fatura anterior é ignorado (já aparece na conta corrente).
    Parcelas usam a data de fechamento da fatura, porque a data impressa é a
    da compra original, que pode ser de meses atrás.
    """
    fechamento = re.search(r"Fatura fechada em (\d{2}/\d{2}/\d{4})", texto)
    if not fechamento:
        raise ValueError("Fatura sem data de fechamento.")
    data_fech = pd.to_datetime(fechamento.group(1), format="%d/%m/%Y")

    inicio = texto.find("Lançamentos nesta fatura")
    fim = texto.find("Total da Fatura", inicio)
    secao = None
    linhas = []
    for linha in texto[inicio:fim].splitlines():
        conteudo = linha.strip()
        m = _LINHA_FATURA.match(conteudo)
        if not m:
            if conteudo and len(conteudo) < 40 and not re.search(r"\d", conteudo):
                secao = normalizar(conteudo)  # cabeçalho de seção ("Supermercados")
            continue
        dia, mes, descricao, valor = m.groups()
        if normalizar(descricao).startswith("pgto"):
            continue  # pagamento da fatura anterior
        valor = -converter_valor(valor)  # compra = saída (negativo); estorno = positivo
        if re.search(r"\bPARC \d{2}/\d{2}\b", descricao):
            data = data_fech
        else:
            ano = data_fech.year if (int(mes), int(dia)) <= (data_fech.month, data_fech.day) \
                else data_fech.year - 1
            data = pd.Timestamp(year=ano, month=int(mes), day=int(dia))
        descricao = re.sub(r"\s+BR$", "", re.sub(r"\s+", " ", descricao))
        if valor > 0:
            categoria = CATEGORIA_ESTORNO
        else:
            categoria = SECOES_FATURA_BB.get(secao) or categorizar(descricao, valor)
            if categoria == "TRANSFERÊNCIA":
                categoria = CATEGORIA_PADRAO
        linhas.append({"Data": data, "Descrição": descricao, "Valor": valor,
                       "Categoria": categoria})

    t = pd.DataFrame(linhas, columns=["Data", "Descrição", "Valor", "Categoria"])
    t["Tipo"] = ["Entrada" if v > 0 else "Saída" for v in t["Valor"]]
    t["Conta"] = conta
    t["Mês"] = t["Data"].dt.to_period("M").astype(str)
    return t


# ============================================================================
# CARREGAMENTO DE VÁRIOS ARQUIVOS
# ============================================================================
def identificar_conta(nome, colunas=()):
    """Nome da conta a partir do nome do arquivo ou do formato do extrato."""
    n = normalizar(nome)
    if n.startswith("nu_") or "nubank" in n:
        return "Nubank"
    if {"Lançamento", "Detalhes"} <= set(colunas):
        return "BB Conta"
    if re.search(r"\b(bb|banco do brasil)\b", n):
        return "BB Conta"
    base = re.sub(r"\.[a-z]+$", "", nome)
    return re.sub(r"[\d_\-\s]+$", "", base).strip() or base


def carregar_arquivo(nome, conteudo):
    """Lê um arquivo enviado.

    Retorna {"tipo": "tabela", "bruto": DataFrame, "conta": str} para extratos
    em CSV/Excel (as colunas ainda precisam ser identificadas) ou
    {"tipo": "transacoes", "dados": DataFrame, "conta": str} para faturas em PDF.
    """
    ext = nome.lower().rsplit(".", 1)[-1]
    if ext == "ofx":
        raise ValueError("arquivo OFX ainda não é lido; envie o CSV do mesmo período.")
    if ext == "pdf" or conteudo[:4] == b"%PDF":
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(conteudo)).pages)
        if eh_fatura_bb(texto):
            return {"tipo": "transacoes", "dados": ler_fatura_bb(texto), "conta": "BB Cartão"}
        raise ValueError("PDF não reconhecido (só a fatura do cartão BB é lida em PDF); "
                         "envie o extrato em CSV ou Excel.")
    bruto = ler_extrato(nome, conteudo)
    return {"tipo": "tabela", "bruto": bruto, "conta": identificar_conta(nome, bruto.columns)}


def _marcar_transferencias_entre_contas(t, dias=2):
    """Pix/TED que sai de uma conta sua e entra em outra conta sua no mesmo valor."""
    candidatas = t[(t["Tipo"] != "Interna")
                   & ~t["Conta"].str.contains("Cartão")
                   & t["Descrição"].map(lambda d: bool(PADRAO_TRANSFERENCIA.search(normalizar(d))))]
    saidas = candidatas[candidatas["Valor"] < 0].sort_values("Data")
    entradas = candidatas[candidatas["Valor"] > 0]
    usadas = set()
    for i, s in saidas.iterrows():
        par = entradas[(entradas["Conta"] != s["Conta"])
                       & (entradas["Valor"].round(2) == round(-s["Valor"], 2))
                       & ((entradas["Data"] - s["Data"]).abs() <= pd.Timedelta(days=dias))
                       & ~entradas.index.isin(usadas)]
        if len(par):
            j = (par["Data"] - s["Data"]).abs().idxmin()
            usadas.add(j)
            t.loc[[i, j], "Categoria"] = CATEGORIA_ENTRE_CONTAS
            t.loc[[i, j], "Tipo"] = "Interna"
    return t


def _marcar_transferencias_para_si(t, nome_titular):
    """Pix/TED para (ou de) você mesmo em outro banco: dinheiro continua seu."""
    nome = normalizar(nome_titular)
    if len(nome.split()) < 2:
        return t  # exige nome e sobrenome para não pegar homônimos
    alvo = (t["Tipo"] != "Interna") & ~t["Conta"].str.contains("Cartão") & t["Descrição"].map(
        lambda d: nome in normalizar(d) and bool(PADRAO_TRANSFERENCIA.search(normalizar(d))))
    t.loc[alvo, "Categoria"] = CATEGORIA_ENTRE_CONTAS
    t.loc[alvo, "Tipo"] = "Interna"
    return t


def consolidar(tabelas, nome_titular=""):
    """Junta as transações de vários arquivos e trata o que envolve mais de uma conta.

    - Remove duplicatas entre arquivos (o mesmo período enviado duas vezes)
    - Marca transferências entre as suas contas como movimentação interna
    - Pix/TED para o próprio titular (nome informado) também é interno
    - Pagamento de fatura só é interno se a fatura do cartão foi enviada;
      senão ele é a única informação do gasto e conta como saída
    """
    tabelas = [x for x in tabelas if not x.empty]
    if not tabelas:
        return pd.DataFrame(columns=["Data", "Descrição", "Valor", "Tipo", "Categoria",
                                     "Conta", "Mês"])
    for n, x in enumerate(tabelas):
        x["_arquivo"] = n
    t = pd.concat(tabelas, ignore_index=True)

    # Duplicatas: mantém, para cada lançamento, a maior quantidade vista num mesmo arquivo
    chave = ["Conta", "Data", "Descrição", "Valor"]
    t["_ocorrencia"] = t.groupby(chave + ["_arquivo"]).cumcount()
    t = t.drop_duplicates(subset=chave + ["_ocorrencia"]).drop(columns=["_arquivo", "_ocorrencia"])
    t = t.reset_index(drop=True)

    if not t["Conta"].str.contains("Cartão").any():
        fatura = t["Categoria"] == CATEGORIA_FATURA
        t.loc[fatura, "Categoria"] = CATEGORIA_CARTAO
        t.loc[fatura, "Tipo"] = [definir_tipo(CATEGORIA_CARTAO, v) for v in t.loc[fatura, "Valor"]]

    t = _marcar_transferencias_entre_contas(t)
    if nome_titular:
        t = _marcar_transferencias_para_si(t, nome_titular)
    return t.sort_values(["Data", "Conta"]).reset_index(drop=True)


def formatar_reais(v):
    """1234.5 -> 'R$ 1.234,50'"""
    sinal = "-" if v < 0 else ""
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {texto}"
