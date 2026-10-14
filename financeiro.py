"""
Leitura, limpeza e categorização de extratos bancários.

Separado da interface (streamlit_app.py) para poder ser testado sem o Streamlit.
"""

import io
import re
import unicodedata

import pandas as pd

# ============================================================================
# CATEGORIAS
# ============================================================================
# A ordem importa: a primeira categoria que casar vence. TRANSFERÊNCIA fica por
# último porque "PIX RESTAURANTE X" deve cair em ALIMENTAÇÃO, não em transferência.
# Palavras sem acento e em minúsculas; casam como palavra inteira (com plural "s").
CATEGORIAS = {
    "CASA": ["aluguel", "condominio", "agua", "luz", "energia", "cosern", "caern",
             "gas", "internet", "telefone", "celular", "claro", "vivo", "tim"],
    "TRANSPORTE": ["combustivel", "gasolina", "etanol", "posto", "estacionamento",
                   "uber", "onibus", "pedagio", "ipva", "detran", "shell", "ipiranga"],
    "ALIMENTAÇÃO": ["restaurante", "lanchonete", "comida", "mercado", "supermercado",
                    "padaria", "delivery", "ifood", "rappi", "acougue", "hortifruti",
                    "nordestao", "carrefour", "atacadao", "assai", "pizzaria"],
    "SAÚDE": ["farmacia", "drogaria", "medico", "clinica", "dentista", "hospital",
              "laboratorio", "academia", "unimed", "hapvida", "plano de saude"],
    "EDUCAÇÃO": ["escola", "faculdade", "universidade", "curso", "livro", "livraria"],
    "LAZER": ["cinema", "teatro", "show", "viagem", "hotel", "airbnb", "netflix",
              "spotify", "ingresso"],
    "SHOPPING": ["roupa", "sapato", "loja", "vestuario", "shopping", "magazine",
                 "amazon", "mercadolivre", "shopee", "renner", "riachuelo"],
    "INVESTIMENTO": ["fii", "acao", "acoes", "tesouro", "cdb", "lci", "lca",
                     "aplicacao", "bitcoin", "corretora"],
    "IMPOSTO": ["irpf", "irpj", "icms", "pis", "cofins", "iss", "inss", "darf",
                "gps", "csll", "simples nacional"],
    "TARIFAS BANCÁRIAS": ["tarifa", "iof", "juros", "anuidade", "cesta", "encargo",
                          "multa"],
    "TRANSFERÊNCIA": ["pix", "ted", "doc", "transferencia", "transf"],
}
CATEGORIA_ENTRADA = "RECEITA"
CATEGORIA_PADRAO = "OUTRO"

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
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


_PADROES = {
    categoria: re.compile(r"\b(?:" + "|".join(re.escape(p) for p in palavras) + r")s?\b")
    for categoria, palavras in CATEGORIAS.items()
}


def categorizar(descricao, valor=None):
    """Categoria de uma transação. Entradas (valor > 0) viram RECEITA."""
    if valor is not None and valor > 0:
        return CATEGORIA_ENTRADA
    texto = normalizar(descricao)
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
    if nome.lower().endswith((".xlsx", ".xls")):
        bruto = pd.read_excel(io.BytesIO(conteudo), header=None, dtype=object)
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
def montar_transacoes(df, colunas):
    """Gera a tabela padronizada: Data, Descrição, Valor, Tipo, Categoria, Mês."""
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

    t["Tipo"] = t["Valor"].map(lambda v: "Entrada" if v > 0 else "Saída")
    t["Categoria"] = [categorizar(d, v) for d, v in zip(t["Descrição"], t["Valor"])]
    t["Mês"] = t["Data"].dt.to_period("M").astype(str)
    return t.sort_values("Data").reset_index(drop=True)


def resumo_categorias(t):
    """Total de saídas por categoria (valores positivos), do maior para o menor."""
    saidas = t[t["Valor"] < 0]
    tabela = (saidas.groupby("Categoria")["Valor"].agg(["sum", "count"])
              .rename(columns={"sum": "Total", "count": "Transações"}))
    tabela["Total"] = -tabela["Total"]
    total = tabela["Total"].sum()
    tabela["% das saídas"] = (tabela["Total"] / total * 100) if total else 0
    return tabela.sort_values("Total", ascending=False).reset_index()


def resumo_mensal(t):
    """Entradas, saídas e saldo por mês."""
    entradas = t[t["Valor"] > 0].groupby("Mês")["Valor"].sum()
    saidas = -t[t["Valor"] < 0].groupby("Mês")["Valor"].sum()
    tabela = pd.DataFrame({"Entradas": entradas, "Saídas": saidas}).fillna(0)
    tabela["Saldo"] = tabela["Entradas"] - tabela["Saídas"]
    return tabela.sort_index().reset_index().rename(columns={"index": "Mês"})


def formatar_reais(v):
    """1234.5 -> 'R$ 1.234,50'"""
    sinal = "-" if v < 0 else ""
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {texto}"
