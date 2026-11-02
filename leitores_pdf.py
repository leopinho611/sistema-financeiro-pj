"""
Leitores de extratos e faturas em PDF dos bancos (além da fatura BB e do Nubank,
que estão em financeiro.py).

Cada leitor recebe o texto do PDF e devolve a tabela padronizada de
montar_transacoes. Os extratos de conta usam o texto "em layout" do pypdf (as
colunas ficam na posição em que aparecem na página), porque é a posição que diz
se o valor é crédito, débito ou saldo.

Os PDFs que não têm lançamentos (extrato sem movimento, resumo de aplicação)
levantam SemLancamentos, para a tela dizer isso em vez de "não reconhecido".
"""

import io
import re

import pandas as pd
from pypdf import PdfReader

from financeiro import (CATEGORIA_ESTORNO, CATEGORIA_PADRAO, converter_valor, montar_transacoes,
                        normalizar)

VALOR = r"-?[\d.]+,\d{2}-?"
_VALOR = re.compile(rf"(?<![\w.,]){VALOR}(?![\w,])")
_PARCELA = re.compile(r"\b(\d{2,3})/(\d{2,3})$")
_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8,
          "set": 9, "out": 10, "nov": 11, "dez": 12}


class SemLancamentos(Exception):
    """O PDF foi reconhecido, mas não tem lançamentos (não é erro)."""

    def __init__(self, conta, motivo):
        super().__init__(motivo)
        self.conta = conta


def texto_em_layout(conteudo):
    paginas = PdfReader(io.BytesIO(conteudo)).pages
    texto = "\n".join(p.extract_text(extraction_mode="layout") or "" for p in paginas)
    return texto.replace("\xa0", " ")


def _tabela(lancamentos, conta, cartao=False):
    if not lancamentos:
        raise SemLancamentos(conta, "nenhum lançamento no período")
    bruto = pd.DataFrame(lancamentos)
    bruto["Data"] = bruto["Data"].dt.strftime("%Y-%m-%d")
    t = montar_transacoes(bruto, {"data": "Data", "descricao": ["Descrição"], "valor": "Valor"},
                          conta)
    if cartao:  # no cartão, valor positivo é estorno, não receita
        t.loc[t["Valor"] > 0, "Categoria"] = CATEGORIA_ESTORNO
        # "LOJA 04/10" no fim da descrição: parcela 4 de 10 (para as parcelas futuras)
        parc = t["Descrição"].str.extract(r"\b(\d{1,3})/(\d{1,3})\s*$").astype(float)
        valida = (parc[0] >= 1) & (parc[0] <= parc[1]) & (parc[1] > 1)
        t["Parcela"] = parc[0].where(valida)
        t["Parcelas"] = parc[1].where(valida)
    return t


def _data(dia, mes, ano_ref, mes_ref):
    """dd/mm sem ano: o ano do extrato, ou o anterior se o mês passa do mês do extrato."""
    ano = ano_ref if int(mes) <= mes_ref else ano_ref - 1
    return pd.Timestamp(ano, int(mes), int(dia))


def _limpa(texto):
    return re.sub(r"\s+", " ", texto).strip()


def _sem_movimento(conta, data, descricao):
    """Uma linha de valor zero, para a conta aparecer na planilha mesmo sem lançamentos."""
    return pd.DataFrame([{"Data": data, "Descrição": descricao, "Valor": 0.0,
                          "Categoria": CATEGORIA_PADRAO, "Tipo": "Entrada", "Fornecedor": "",
                          "Conta": conta, "Mês": data.strftime("%Y-%m")}])


def _movimento_aplicacao(data, aplicado=0.0, rendimento=0.0, iof=0.0, ir=0.0, resgate=0.0):
    """Lançamentos da conta de aplicação, do ponto de vista da aplicação.

    Entra (+) o que foi aplicado e o rendimento bruto; sai (-) o IOF e o IR retidos e o
    resgate líquido que voltou para a conta corrente (principal + rendimento líquido).
    """
    partes = [("Aplicação", aplicado), ("Rendimento bruto", rendimento), ("IOF retido", -iof),
              ("IR retido", -ir), ("Resgate", -resgate)]
    return [{"Data": data, "Descrição": d, "Valor": round(v, 2)} for d, v in partes if v]


def _juntar(*tabelas):
    tabelas = [t for t in tabelas if t is not None and not t.empty]
    return pd.concat(tabelas, ignore_index=True) if len(tabelas) > 1 else tabelas[0]


# ============================================================================
# BANCO DO BRASIL - extrato de conta corrente (Consultas - Extrato de conta corrente)
# ============================================================================
_LINHA_BB = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s+(?:\d{2}/\d{2}/\d{4}\s+)?\d{4}\s+\d{5}\s+\d{3}\s+"
                       r"(.+?)\s+([\d.]+,\d{2}) ([CD])(?:\s+[\d.]+,\d{2} [CD])?\s*$")


def eh_extrato_bb(texto):
    return "Extrato de conta corrente" in texto and "Dt. balancete" in texto


def ler_extrato_bb(texto):
    ag = re.search(r"Agência\s+(\S+)", texto)
    cc = re.search(r"Conta corrente\s+(\d[\d.]*-[\dXx])", texto)
    conta = f"BB Conta Ag {ag.group(1)} Cc {cc.group(1)}" if ag and cc else "BB Conta"
    lancamentos = []
    for linha in texto.splitlines():
        m = _LINHA_BB.match(linha)
        if m:
            data, historico, valor, dc = m.groups()
            historico = re.sub(r"\s+[\d.]+$", "", historico.strip())  # tira o documento
            lancamentos.append({"Data": pd.to_datetime(data, format="%d/%m/%Y"),
                                "Descrição": _limpa(historico),
                                "Valor": converter_valor(valor) * (1 if dc == "C" else -1)})
        elif lancamentos and linha.strip() and linha.startswith(" " * 20) \
                and not _VALOR.search(linha):
            # Linha de detalhe (favorecido/remetente) do lançamento de cima
            lancamentos[-1]["Descrição"] += " - " + _limpa(linha)
        elif "OBSERVAÇÕES" in linha:
            break
    return _tabela(lancamentos, conta)


# ============================================================================
# BRADESCO - extrato de conta (Net Empresa)
# ============================================================================
_DETALHE_BRADESCO = re.compile(r"^(REM[:.]|REMET\.|DEST\.|CONTR |FAV[:.])")


def eh_extrato_bradesco(texto):
    return "Extrato de: Ag:" in texto and "Lançamento" in texto and "Dcto." in texto


def _colunas(cabecalho, nomes):
    return [cabecalho.index(n) for n in nomes]


_LINHA_BRADESCO = re.compile(rf"^\s*(?:(\d{{2}}/\d{{2}}/\d{{4}})\s+)?(.*?)(?:\s+\d+\s+({VALOR})"
                             rf"(?:\s+{VALOR})?)?\s*$")


def ler_extrato_bradesco(texto):
    m = re.search(r"Ag:\s*(\d+)\s*\|\s*CC:\s*([\d-]+)", texto)
    conta = f"Bradesco Ag {m.group(1)} Cc {m.group(2)}" if m else "Bradesco"
    lancamentos, pendentes, data, no_extrato = [], [], None, False
    for linha in texto.splitlines():
        if "Lançamento" in linha and "Dcto." in linha and "Saldo" in linha:
            no_extrato = True
            continue
        if not no_extrato or not linha.strip() or "Folha " in linha:
            continue
        if linha.strip().startswith("Total"):
            break  # o que vem depois ("Últimos Lançamentos") já é do mês seguinte
        d, descricao, valor = _LINHA_BRADESCO.match(linha).groups()
        if d:
            data = pd.to_datetime(d, format="%d/%m/%Y")
        descricao = _limpa(descricao)
        if normalizar(descricao).startswith("saldo"):
            continue
        if not valor:
            pendentes.append(descricao)
            continue
        # Linhas sem valor antes desta: o detalhe do lançamento anterior e/ou o título
        # deste (quando a quebra de página separou título e valor)
        if pendentes and lancamentos and (len(pendentes) > 1 or not _DETALHE_BRADESCO.match(descricao)):
            lancamentos[-1]["Descrição"] += " - " + pendentes.pop(0)
        lancamentos.append({"Data": data, "Descrição": " - ".join(pendentes + [descricao]),
                            "Valor": converter_valor(valor)})
        pendentes = []
    if pendentes and lancamentos:
        lancamentos[-1]["Descrição"] += " - " + " - ".join(pendentes)
    return _tabela(lancamentos, conta)


# ============================================================================
# BRADESCO - fatura de cartão empresarial (Net Empresa, "Detalhe do Extrato")
# ============================================================================
_LINHA_CARTAO_BRADESCO = re.compile(r"^(\d{2})/(\d{2}) (.+?) (-?[\d.]+,\d{2}) (-?[\d.]+,\d{2})$")


def eh_fatura_bradesco(texto):
    return "Detalhe do Extrato" in texto and "Número do cartão" in texto and "Bradesco" in texto


def _vencimento(texto):
    m = (re.search(r"Data de vencimento:\s*(\d{2}/\d{2}/\d{4})", texto)
         or re.search(r"(\d{2}/\d{2}/\d{4})\s*Data de vencimento", texto)
         or re.search(r"vencimento:?\s*(\d{2}/\d{2}/\d{4})", texto))
    if not m:
        raise ValueError("fatura sem data de vencimento.")
    return pd.to_datetime(m.group(1), format="%d/%m/%Y")


def _compras_do_cartao(itens, venc):
    """Parcela entra na data de vencimento (a impressa é a da compra original)."""
    lancamentos = []
    for dia, mes, descricao, valor in itens:
        descricao = _limpa(descricao)
        if normalizar(descricao).startswith(("pagamento", "pgto")):
            continue  # pagamento da fatura anterior (já está na conta corrente)
        parcela = _PARCELA.search(descricao)
        data = venc if parcela else _data(dia, mes, venc.year, venc.month)
        # Sem parcela, a compra é do mês da fatura. Data muito antiga é outra coisa (ex.: o
        # desconto da anuidade traz a data de aniversário do cartão): entra no vencimento
        if data < venc - pd.Timedelta(days=75):
            data = venc
        lancamentos.append({"Data": data, "Descrição": descricao, "Valor": -valor})
    return lancamentos


def ler_fatura_bradesco(texto):
    venc = _vencimento(texto)
    final = re.search(r"XXXX\.XXXX\.XXXX\.(\d{4})", texto)
    bandeira = re.search(r"- (VISA|ELO|MASTERCARD|MASTER|AMEX)", texto)
    conta = "Bradesco Cartão"
    if bandeira:
        conta += f" {bandeira.group(1).title()}"
    if final:
        conta += f" final {final.group(1)}"
    itens = []
    for linha in texto.splitlines():
        m = _LINHA_CARTAO_BRADESCO.match(linha.strip())
        if m:
            dia, mes, descricao, _dolar, reais = m.groups()
            itens.append((dia, mes, descricao, converter_valor(reais)))
    return _tabela(_compras_do_cartao(itens, venc), conta, cartao=True)


# ============================================================================
# ITAÚ - extrato mensal (conta corrente e aplicações automáticas)
# ============================================================================
def eh_extrato_itau(texto):
    return "extrato" in texto and "Minha agência" in texto and "Minha conta" in texto


def ler_extrato_itau(texto):
    m = re.search(r"ag (\d+) cc ([\d-]+) (jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez) (\d{4})",
                  texto)
    if not m:
        raise ValueError("extrato Itaú sem agência, conta e mês.")
    conta = f"Itaú Ag {m.group(1)} Cc {m.group(2)}"
    mes_ref, ano_ref = _MESES[m.group(3)], int(m.group(4))
    lancamentos, data, x = [], None, None
    for linha in texto.splitlines():
        if "descrição" in linha and "entradas" in linha and "saídas" in linha:
            x = _colunas(linha, ["data", "descrição", "entradas"])
            continue
        if x is None:
            continue
        if "totalizador de aplicações" in linha or "Aplicações Automáticas" in linha:
            break
        d = re.search(r"(\d{2})/(\d{2})\s*$", linha[:x[1] - 1])
        if d and d.start() >= x[0] - 2:
            data = _data(d.group(1), d.group(2), ano_ref, mes_ref)
        resto = linha[x[1] - 1:]
        valores = list(_VALOR.finditer(resto))
        if not valores or data is None:
            continue
        # "PIX QRS FULANO02/01": separa a data do Pix do nome
        descricao = re.sub(r"(\S)(\d{2}/\d{2})$", r"\1 \2", _limpa(resto[:valores[0].start()]))
        if not descricao or normalizar(descricao).startswith("saldo"):
            continue
        # O primeiro valor é o lançamento (saída termina com "-"); o segundo, o saldo
        lancamentos.append({"Data": data, "Descrição": descricao,
                            "Valor": converter_valor(valores[0].group())})
    return _juntar(_tabela(lancamentos, conta), _aplicacoes_itau(texto, conta, ano_ref, mes_ref))


def _aplicacoes_itau(texto, conta, ano_ref, mes_ref):
    """Tabela "movimentação - aplicações/resgates" das aplicações automáticas."""
    inicio = texto.find("movimentação - aplicações/resgates")
    if inicio < 0:
        return None
    lancamentos = []
    for linha in texto[inicio:].splitlines():
        if linha.strip().startswith("total"):
            break
        m = re.match(r"\s*(\d{2})/(\d{2})\s+((?:[\d.]+,\d{2}\s*){6,7})$", linha)
        if not m:
            continue
        # aplicações, principal resgatado, rendimento bruto, IOF, IRRF, rendimento líquido
        aplicado, principal, bruto, iof, ir, liquido = map(converter_valor, m.group(3).split()[:6])
        lancamentos += _movimento_aplicacao(_data(m.group(1), m.group(2), ano_ref, mes_ref),
                                            aplicado, bruto, iof, ir, principal + liquido)
    if not lancamentos:
        return None
    return _tabela(lancamentos, conta.replace("Itaú", "Itaú Aplic Aut Mais", 1))


# ============================================================================
# ITAÚ - fatura do cartão empresarial
# ============================================================================
_LINHA_CARTAO_ITAU = re.compile(r"^(\d{2})/(\d{2}) (.+?) (-?R\$\s?[\d.]+,\d{2})$")


def eh_fatura_itau(texto):
    return "ITAU EMPRESAS" in texto.upper() and "fatura do cartão" in texto \
        and "Lançamentos nacionais" in texto


def ler_fatura_itau(texto):
    venc = _vencimento(texto)
    final = re.search(r"\d{4}\.XXXX\.XXXX\.(\d{4})", texto)
    conta = f"Itaú Cartão final {final.group(1)}" if final else "Itaú Cartão"
    inicio = texto.find("\nLançamentos\n")
    fim = texto.find("Encargos desta fatura", inicio)
    itens = []
    for linha in texto[inicio:fim if fim > 0 else None].splitlines():
        m = _LINHA_CARTAO_ITAU.match(linha.strip())
        if m:
            dia, mes, descricao, valor = m.groups()
            # Internacional: tira moeda local, dólar e cotação da descrição
            descricao = re.sub(r"(\s+(?:[A-Z]{3}|US\$|R\$)\s?[\d.,]+)+$", "", descricao)
            itens.append((dia, mes, descricao, converter_valor(valor)))
    return _tabela(_compras_do_cartao(itens, venc), conta, cartao=True)


# ============================================================================
# SICOOB - fatura do cartão (Sicoobnet: Cartões → Detalhamento, "Extrato de fatura")
# ============================================================================
# Colunas fixas depois de "dd/mm  ": estabelecimento (22 letras), parcela (8) e cidade; o valor
# fica no fim. Compra internacional ocupa 2 linhas: a de baixo traz o valor em reais no fim.
_LINHA_SICOOB = re.compile(r"^(\d{2})/(\d{2})  (.*)$")
_FIM_VALOR = re.compile(rf"\s*({VALOR})\s*$")


def eh_fatura_sicoob(texto):
    return "EXTRATO DE FATURA DE CARTÃO DE CRÉDITO" in texto and "SICOOB" in texto.upper() \
        and "Movimentos" in texto


def eh_boleto_fatura_sicoob(texto):
    return "EXTRATO DA FATURA DO CARTÃO DE CRÉDITO" in texto and "Ficha de compensação" in texto \
        and "sicoob" in texto.lower()


def _compra_sicoob(corpo):
    """(descrição, valor ou None) de uma linha de compra, sem a cidade."""
    valor = _FIM_VALOR.search(corpo)
    if re.match(r"^.{22}(\d{2}/\d{2}|\s{5})", corpo):
        nome, parcela = corpo[:22].strip(), corpo[22:30].strip()
    else:  # linha curta (IOF, anuidade): sem cidade
        resto = corpo[:valor.start()] if valor else corpo
        resto = re.sub(r"\(\d{4}\)", "", resto)
        p = re.search(r"\s(\d{2}/\d{2})\s*$", resto)
        nome, parcela = (resto[:p.start()] if p else resto).strip(), p.group(1) if p else ""
    descricao = _limpa(f"{nome} {parcela}" if re.fullmatch(r"\d{2}/\d{2}", parcela) else nome)
    return descricao, converter_valor(valor.group(1)) if valor else None


def ler_fatura_sicoob(texto):
    m = re.search(r"Vencimento:\s*(\d{2}/\d{2}/\d{4})", texto)
    if not m:
        raise ValueError("fatura sem data de vencimento.")
    venc = pd.to_datetime(m.group(1), format="%d/%m/%Y")
    # A conta do cartão é a mesma todo mês, mesmo com vários cartões (finais) na fatura
    numero = re.search(r"Conta Cartão:\s*(\d+)", texto)
    conta = f"Sicoob Cartão {numero.group(1)[-4:]}" if numero else "Sicoob Cartão"
    inicio = texto.find("Movimentos")
    itens, pendente = [], None
    for linha in texto[inicio:].splitlines():
        # Cada cartão da fatura ("GASTOS DE ... (final)") fecha com o seu TOTAL; a lista só
        # acaba nos encargos
        if "ENCARGOS FINANCEIROS" in linha or linha.startswith("Demostrativo"):
            break
        if re.match(r"^\s*TOTAL\b", linha):
            pendente = None
            continue
        m = _LINHA_SICOOB.match(linha)
        if m:
            dia, mes, corpo = m.groups()
            descricao, valor = _compra_sicoob(corpo)
            if valor is None:
                pendente = (dia, mes, descricao)   # internacional: o valor vem na linha de baixo
            else:
                itens.append((dia, mes, descricao, valor))
                pendente = None
        elif pendente and _FIM_VALOR.search(linha):
            itens.append((*pendente, converter_valor(_FIM_VALOR.search(linha).group(1))))
            pendente = None
    return _tabela(_compras_do_cartao(itens, venc), conta, cartao=True)


# ============================================================================
# SICOOB - extrato de conta corrente (Sicoobnet: Extrato, impresso do navegador)
# ============================================================================
# Cada lançamento começa com "dd/mm documento", tem o tipo ("PIX EMITIDO OUTRA IF") e o
# complemento (quem recebeu, o que foi pago) nas linhas seguintes, e termina no valor com
# C (crédito) ou D (débito). "SALDO DO DIA" não é lançamento
_DATA_SICOOB = re.compile(r"^(\d{2})/(\d{2})(?![/\d])\s*(.*)$")
_VALOR_CD = re.compile(r"R\$\s*([\d.]+,\d{2})([CD])\s*$")


# Nome curto de cada tipo de lançamento (o começo como o normalizar deixa: sem acento,
# pontuação nem maiúsculas). Fica antes do " - ", e o fornecedor sai do complemento depois
TIPOS_SICOOB = [
    ("pix emitido", "Pix enviado"), ("pix recebido", "Pix recebido"),
    ("deb tit compe", "Boleto pago"), ("deb pagamento de boleto", "Boleto pago"),
    ("cred ted", "TED recebida"), ("deb conv tributos", "Tributos federais"),
    ("deb conv telecomunicacoes", "Débito automático telefonia"),
    ("deb conv en eletrica", "Débito automático energia"), ("cheque pago", "Cheque pago"),
    ("compra nacional debit", "Compra no débito"),
    ("debito pacote servicos", "Tarifa pacote de serviços"),
    ("deb parcelas subsc", "Cota capital da cooperativa"),
]


def _descricao_sicoob(partes):
    """"Pix enviado - SERVICOS PLACA ..." a partir do tipo e do complemento."""
    tipo, complemento = partes[0], " ".join(partes[1:])
    complemento = re.sub(r"^(Pagamento|Recebimento) Pix\s*", "", complemento)
    chave = normalizar(tipo)
    curto = next((nome for comeco, nome in TIPOS_SICOOB if chave.startswith(comeco)), tipo)
    return _limpa(f"{curto} - {complemento}" if complemento else curto)


def eh_extrato_sicoob(texto):
    return "EXTRATO DE CONTA CORRENTE" in texto and "SICOOB" in texto.upper() \
        and "HISTÓRICO DE MOVIMENTAÇÃO" in texto


def ler_extrato_sicoob(texto):
    periodo = re.search(r"Periodo:\s*\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/(\d{2})/(\d{4})", texto)
    if not periodo:
        raise ValueError("extrato sem período.")
    mes_ref, ano_ref = int(periodo.group(1)), int(periodo.group(2))
    numero = re.search(r"Conta:\s*([\d.]+-\d)", texto)
    conta = f"Sicoob {numero.group(1)}" if numero else "Sicoob"
    inicio = texto.find("HISTÓRICO DE MOVIMENTAÇÃO")
    fim = texto.find("\nRESUMO", inicio)
    lancamentos, atual = [], None
    for linha in texto[inicio:fim if fim > 0 else None].splitlines():
        linha = linha.strip()
        # Cabeçalho e rodapé de cada página impressa
        if not linha or linha.startswith(("Data Documento", "https://")) \
                or re.match(r"\d{2}/\d{2}/\d{4},", linha):
            continue
        m = _DATA_SICOOB.match(linha)
        if m:
            atual = {"data": _data(m.group(1), m.group(2), ano_ref, mes_ref), "partes": []}
            linha = m.group(3)
            # O documento ("Pix", "362913286", "185.382", "41 - 16") não descreve o lançamento
            if re.fullmatch(r"Pix|[\d.\s-]+", linha):
                continue
        if atual is None:
            continue
        valor = _VALOR_CD.search(linha)
        if not valor:
            atual["partes"].append(linha)
            continue
        if linha[:valor.start()].strip():
            atual["partes"].append(linha[:valor.start()].strip())
        descricao = _descricao_sicoob(atual["partes"]) if atual["partes"] else ""
        if descricao and not descricao.upper().startswith("SALDO"):
            v = converter_valor(valor.group(1))
            lancamentos.append({"Data": atual["data"], "Descrição": descricao,
                                "Valor": v if valor.group(2) == "C" else -v})
        atual = None
    return _tabela(lancamentos, conta)


# ============================================================================
# CAIXA - extrato de conta (Internet Banking CAIXA, com data efetiva e saldo a cada linha)
# ============================================================================
# Cada lançamento: "dd/mm/aaaa" (data contábil), "dd/mm hh:mm documento histórico" e, às
# vezes, mais linhas de histórico, até "R$ valor R$ saldo C". O débito tem um "-" solto antes
# do valor; o sinal é tirado da diferença de saldo, que também confere o valor
_VALOR_SALDO_CAIXA = re.compile(r"R\$\s*([\d.]+,\d{2})\s+R\$\s*([\d.]+,\d{2})\s*([CD])\s*$")
_HISTORICOS_CAIXA = ("PIX RECEBIDO", "PIX ENVIADO", "RECEBIMENTO TED", "DEB PIX CHAVE",
                     "ENVIO TED", "PAG BOLETO", "PAG ORGAOS GOV")


def eh_extrato_caixa(texto):
    return "Data Efetiva Documento Histórico Valor Saldo" in texto \
        and "Saldo anterior ao período solicitado" in texto


def _saldo_caixa(valor, sinal):
    v = converter_valor(valor)
    return -v if sinal == "D" else v


def _descricao_caixa(partes):
    """"PIX RECEBIDO - Banco VR 78.626.983/0001-63" (histórico - de quem/para quem)."""
    texto = " ".join(partes)
    texto = re.sub(r"(/\d{4}-) (\d{2})\b", r"\1\2", texto)       # CNPJ quebrado na linha
    texto = re.sub(r"\s+-$", "", texto).strip()                     # o "-" do débito
    for historico in _HISTORICOS_CAIXA:
        if texto.startswith(historico):
            resto = texto[len(historico):].strip()
            return f"{historico} - {resto}" if resto else historico
    if len(partes) > 1:
        return f"{partes[0]} - {' '.join(partes[1:])}".strip(" -")
    return texto


def ler_extrato_caixa(texto):
    c = re.search(r"Agência:\s*(\d+)\s+Conta:\s*([\d-]+)", texto)
    conta = f"Caixa Ag {c.group(1)} Cc {c.group(2)}" if c else "Caixa"
    anterior = re.search(r"Saldo anterior ao período solicitado\s*R\$\s*([\d.]+,\d{2})\s*([CD])",
                         texto)
    saldo = _saldo_caixa(*anterior.groups()) if anterior else None
    lancamentos, data, partes = [], None, []
    for linha in texto.splitlines():
        linha = linha.strip()
        # Fim do CNPJ que quebrou de linha ("24.519.654/0001-" + "94")
        if partes and re.search(r"/\d{4}-$", partes[-1]) and re.fullmatch(r"\d{2}", linha):
            partes[-1] += linha
            continue
        if not linha or linha == "Data" or linha.startswith("Data Efetiva") \
                or re.fullmatch(r"\d{1,6}", linha):      # página e documento sozinhos
            continue
        m = re.match(r"^(\d{2}/\d{2}/\d{4})(.*)$", linha)
        if m:
            if "SALDO DIA" in m.group(2):
                continue
            data, partes = pd.to_datetime(m.group(1), format="%d/%m/%Y"), []
            continue
        if data is None:
            continue
        # "dd/mm hh:mm [documento] [histórico]": data efetiva e documento não descrevem
        linha = re.sub(r"^\d{2}/\d{2}\s+\d{2}:\d{2}\s*", "", linha)
        linha = re.sub(r"^\d{6}(\s+|$)", "", linha)
        if not linha:
            continue
        v = _VALOR_SALDO_CAIXA.search(linha)
        if not v:
            if linha and linha != "-":
                partes.append(linha)
            continue
        if linha[:v.start()].strip():
            partes.append(linha[:v.start()].strip())
        impresso = converter_valor(v.group(1))
        novo_saldo = _saldo_caixa(v.group(2), v.group(3))
        valor = round(novo_saldo - saldo, 2) if saldo is not None else None
        if valor is None or abs(abs(valor) - impresso) > 0.01:
            valor = -impresso if partes and partes[-1].endswith("-") else impresso
        saldo = novo_saldo
        lancamentos.append({"Data": data, "Descrição": _descricao_caixa(partes), "Valor": valor})
        data, partes = None, []
    return _tabela(lancamentos, conta)


# ============================================================================
# BNB - extrato consolidado (Internet Banking BNB). Costuma chegar sem texto (as letras
# viram desenho na impressão) e ser lido por OCR, que às vezes troca dígitos (0 por 9, 2
# ou 8). Cada linha traz o saldo, e a sequência dos saldos corrige os valores
# ============================================================================
_LINHA_BNB = re.compile(r"^(?:(\d{1,2})\s+)?(.+?)\s+(\d+)\s+([\d.]+,\d{2})\s*([+-])\s+"
                        r"([\d.]+,\d{2})$")
_MESES_EXTENSO = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7,
                  "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def eh_extrato_bnb(texto):
    return "BNB" in texto and "DEMONSTRATIVO DA MOVIMENTACAO DE CONTA CORRENTE" in texto


def _corrigir_pelos_saldos(itens, saldo_anterior):
    """itens: [(valor com sinal, saldo)] lidos por OCR, que pode ter errado qualquer um.
    Escolhe a sequência de saldos que muda o menor número de números lidos (cada linha tem
    que fechar: saldo anterior + valor = saldo) e devolve [(valor, saldo)] corrigidos."""
    def c(x):
        return round(x, 2)

    if not itens:
        return []
    # Estados: saldo -> (custo, saldos escolhidos até aqui)
    primeiro = c(itens[0][1] - itens[0][0])
    estados = {primeiro: (0 if saldo_anterior in (None, primeiro) else 1, [primeiro])}
    if saldo_anterior is not None and c(saldo_anterior) != primeiro:
        estados[c(saldo_anterior)] = (0, [c(saldo_anterior)])
    for valor, saldo in itens:
        novos = {}
        for anterior, (custo, caminho, *_) in estados.items():
            # Ou o saldo lido está certo, ou o saldo é o anterior + o valor lido
            for x in {c(saldo), c(anterior + valor)}:
                extra = (x != c(saldo)) + (c(x - anterior) != c(valor))
                # Empate: prefere o saldo que fecha com o valor lido
                chave = (custo + extra, x != c(anterior + valor))
                if x not in novos or chave < novos[x][0]:
                    novos[x] = (chave, caminho + [x])
        estados = {x: (chave[0], caminho, chave[1]) for x, (chave, caminho) in novos.items()}
    _, caminho, _ = min(estados.values(), key=lambda e: (e[0], e[2]))
    return [(c(caminho[i + 1] - caminho[i]), caminho[i + 1]) for i in range(len(itens))]


def ler_extrato_bnb(texto):
    emissao = re.search(r"Data de Emiss[aã]o:\s*\d{2}/(\d{2})/(\d{4})", texto)
    referencia = re.search(r"REFERENCIA:\s*([A-Za-zÇç]{3})", texto)
    if not (emissao and referencia):
        raise ValueError("extrato BNB sem o mês de referência.")
    mes = _MESES_EXTENSO.get(normalizar(referencia.group(1))[:3])
    ano = int(emissao.group(2)) - (1 if mes > int(emissao.group(1)) else 0)
    lancamentos, conta, dentro, dia = [], "BNB", False, None
    itens, linhas = [], []

    def fechar():
        for (valor, _), (d, descricao) in zip(_corrigir_pelos_saldos(itens, anterior), linhas):
            lancamentos.append({"Data": pd.Timestamp(ano, mes, d), "Descrição": descricao,
                                "Valor": valor, "Conta": conta})
        itens.clear()
        linhas.clear()

    anterior = None
    for linha in texto.splitlines():
        linha = linha.strip()
        c = re.search(r"AGENCIA:\s*(\d+)\s+CONTA\s+([\d.]+-\d)", linha)
        if c:
            fechar()
            conta, dentro = f"BNB Ag {c.group(1)} Cc {c.group(2)}", False
            continue
        if "DEMONSTRATIVO DA MOVIMENTACAO DE CONTA CORRENTE" in linha:
            fechar()
            dentro, dia, anterior = True, None, None
            continue
        if not dentro:
            continue
        if linha.startswith((">", "***")):
            fechar()
            dentro = False
            continue
        s = re.match(r"SALDO ANTERIOR\s+[\d.]+,\d{2}\s+([\d.]+,\d{2})", linha)
        if s:
            anterior = converter_valor(s.group(1))
            continue
        m = _LINHA_BNB.match(linha)
        if not m:
            continue
        if m.group(1):
            dia = int(m.group(1))
        valor = converter_valor(m.group(4)) * (1 if m.group(5) == "+" else -1)
        itens.append((valor, converter_valor(m.group(6))))
        linhas.append((dia or 1, _limpa(m.group(2))))
    fechar()
    if not lancamentos:
        raise SemLancamentos(conta, "nenhum lançamento no período")
    tabelas = []
    for nome, grupo in pd.DataFrame(lancamentos).groupby("Conta", sort=False):
        tabelas.append(_tabela(grupo.drop(columns="Conta").to_dict("records"), nome))
    return _juntar(*tabelas)


LEITORES_OCR = [(eh_extrato_bnb, ler_extrato_bnb)]


def layout_ocr_conhecido(texto):
    """A 1ª página lida por OCR é de um layout que sabemos ler?"""
    return any(reconhece(texto) for reconhece, _ in LEITORES_OCR)


def ler_texto_ocr(texto):
    """Tabela de transações do texto lido por OCR, ou None se o layout não é conhecido."""
    for reconhece, ler in LEITORES_OCR:
        if reconhece(texto):
            return ler(texto)
    return None


# ============================================================================
# SANTANDER - extrato consolidado PJ básico ("Extrato_PJ_A4_Basico", texto em layout)
# ============================================================================
# Cada lançamento numa linha: "dd/mm" (só no primeiro do dia), descrição, nº do documento
# ("-" quando não há), valor com "-" no fim se for débito e, às vezes, o saldo. O nome de
# quem recebeu o Pix vem na linha de baixo. A movimentação vai do "SALDO EM dd/mm" inicial
# ao final
_LINHA_SANTANDER_PJ = re.compile(r"^(?:(\d{2})/(\d{2})\s+)?(.+?)\s+(?:-|\d+)\s+"
                                 r"([\d.]+,\d{2})(-?)(?:\s+[\d.]+,\d{2}-?)?$")
_CABECALHO_SANTANDER_PJ = ("Data ", "Créditos", "Extrato_PJ", "BALP_", "Pagina:",
                           "EXTRATO CONSOLIDADO")


def eh_extrato_santander_pj(texto):
    return "Extrato_PJ_A4_Basico" in texto and "Movimentação" in texto


def ler_extrato_santander_pj(texto):
    m = re.search(r"(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|"
                  r"novembro|dezembro)/(\d{4})", texto)
    if not m:
        raise ValueError("extrato Santander sem o mês.")
    mes_ref, ano_ref = _MESES[normalizar(m.group(1))[:3]], int(m.group(2))
    # No texto em layout a agência e a conta ficam lado a lado: "4543  13.009258-8"
    c = re.search(r"\b(\d{4})\s+(\d{2}\.\d{6}-\d)\b", texto)
    conta = f"Santander Ag {c.group(1)} Cc {c.group(2)}" if c else "Santander"
    inicio = re.search(r"SALDO EM \d{2}/\d{2}", texto)
    if not inicio:
        raise ValueError("extrato Santander sem a movimentação.")
    lancamentos, dia, ultimo = [], None, None
    for linha in texto[inicio.end():].splitlines():
        linha = _limpa(linha)
        if linha.startswith("SALDO EM"):          # saldo final: acabou a conta corrente
            break
        if not linha or linha.startswith(_CABECALHO_SANTANDER_PJ) \
                or re.fullmatch(r"\w+/\d{4}", linha):
            ultimo = None
            continue
        lin = _LINHA_SANTANDER_PJ.match(linha)
        if lin:
            if lin.group(1):
                dia = (lin.group(1), lin.group(2))
            if dia is None:
                continue
            valor = converter_valor(lin.group(4))
            ultimo = {"Data": _data(dia[0], dia[1], ano_ref, mes_ref),
                      "Descrição": lin.group(3), "Valor": -valor if lin.group(5) else valor}
            lancamentos.append(ultimo)
        elif ultimo is not None and not re.search(r"\d,\d{2}", linha):
            ultimo["Descrição"] += f" - {linha}"     # quem recebeu ou pagou
    return _tabela(lancamentos, conta)


# ============================================================================
# SANTANDER - extrato consolidado inteligente (PJ)
# ============================================================================
_LINHA_SANTANDER = re.compile(rf"^\s*(?:(\d{{2}})/(\d{{2}})\s+)?(.+?)\s+-?\s*({VALOR})"
                              rf"(?:\s+{VALOR})?\s*$")


def eh_extrato_santander(texto):
    return "EXTRATO CONSOLIDADO INTELIGENTE" in texto


def ler_extrato_santander(texto):
    m = re.search(r"(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|"
                  r"novembro|dezembro)/(\d{4})", texto)
    if not m:
        raise ValueError("extrato Santander sem o mês.")
    mes_ref, ano_ref = _MESES[normalizar(m.group(1))[:3]], int(m.group(2))
    c = re.search(r"\b(\d{4})\s+(\d{2}\.\d{6}-\d)\b", texto)
    conta = f"Santander Ag {c.group(1)} Cc {c.group(2)}" if c else "Santander"
    inicio = texto.find("Movimentação\n")
    if inicio < 0:
        raise SemLancamentos(conta, "extrato sem movimentação")
    lancamentos, data = [], None
    for linha in texto[inicio + 13:].splitlines():
        if linha.startswith(("Extrato_PJ", "Saldos por")) or "Pagina:" in linha:
            break
        if not linha.strip():
            continue
        m = _LINHA_SANTANDER.match(linha)
        if not m:
            if lancamentos:
                lancamentos[-1]["Descrição"] += " " + _limpa(linha)
            continue
        if m.group(1):
            data = _data(m.group(1), m.group(2), ano_ref, mes_ref)
        descricao = _limpa(m.group(3)).rstrip(" -")
        if data is None or normalizar(descricao).startswith("saldo"):
            continue
        lancamentos.append({"Data": data, "Descrição": descricao,
                            "Valor": converter_valor(m.group(4))})
    return _juntar(_tabela(lancamentos, conta), _aplicacoes_santander(texto, conta))


_MOV_SANTANDER = re.compile(r"^\s*(\d{2})/([A-Z]{3})/(\d{2})\s*\d{2}/[A-Z]{3}/\d{2}\s+\d+\s+"
                            r"((?:[\d.]+,\d{2}\s*){7})$")


def _aplicacoes_santander(texto, conta):
    """Movimentação mensal do CDB ContaMax (resgate automático)."""
    lancamentos = []
    for linha in texto.splitlines():
        m = _MOV_SANTANDER.match(linha)
        if m:
            # aplicações, principal resgatado, resgate bruto, rendimento, IOF, IR, líquido
            aplicado, _principal, _bruto, rend, iof, ir, liquido = map(converter_valor,
                                                                       m.group(4).split())
            data = pd.Timestamp(2000 + int(m.group(3)), _MESES[m.group(2).lower()],
                                int(m.group(1)))
            lancamentos += _movimento_aplicacao(data, aplicado, rend, iof, ir, liquido)
    if not lancamentos:
        return None
    return _tabela(lancamentos, conta.replace("Santander", "Santander CDB ContaMax", 1))


# ============================================================================
# PDFs sem lançamentos
# ============================================================================
def eh_extrato_caixa_sem_movimento(texto):
    return "NÃO CONSTA LANÇAMENTO" in texto.upper() and "CAIXA" in texto.upper()


def ler_extrato_caixa_sem_movimento(texto):
    c = re.search(r"Agência:\s*(\d+)\s+Conta:\s*([\d-]+)", texto)
    conta = f"Caixa Ag {c.group(1)} Cc {c.group(2)}" if c else "Caixa"
    fim = re.search(r"período de \d{2}/\d{2}/\d{4} à (\d{2}/\d{2}/\d{4})", texto)
    if not fim:
        raise SemLancamentos(conta, "extrato sem lançamentos no período")
    saldo = re.search(r"Saldo anterior[^\n]*?R\$\s*([\d.]+,\d{2}\s*[CD]?)", texto)
    descricao = "Sem lançamentos no período"
    if saldo:
        descricao += f" (saldo R$ {saldo.group(1).strip()})"
    return _sem_movimento(conta, pd.to_datetime(fim.group(1), format="%d/%m/%Y"), descricao)


def eh_resumo_invest_facil(texto):
    return "Investimentos Bradesco" in texto and "Total Aplicado" in texto


def ler_resumo_invest_facil(texto):
    """Resumo do mês do Invest Fácil: entra numa linha por item, no último dia do período."""
    c = re.search(r"Conta:\s*(\d+)\s*\|\s*(\d+)\s*-\s*(\d)", texto)
    conta = f"Bradesco Invest Fácil Ag {c.group(1)} Cc {c.group(2)}-{c.group(3)}" if c \
        else "Bradesco Invest Fácil"
    fim = re.search(r"\d{2}/\d{2}/\d{4} até (\d{2}/\d{2}/\d{4})", texto)
    linha = re.search(rf"INVEST FAC\s+({VALOR})\s+({VALOR})\s+({VALOR})\s+({VALOR})", texto)
    if not fim or not linha:
        raise ValueError("resumo do Invest Fácil sem período ou sem valores.")

    def campo(rotulo):
        m = re.search(rf"{rotulo}\s*({VALOR})", texto)
        return converter_valor(m.group(1)) if m else 0.0

    aplicado, _principal, _bruto, liquido = (converter_valor(v) for v in linha.groups())
    data = pd.to_datetime(fim.group(1), format="%d/%m/%Y")
    lancamentos = _movimento_aplicacao(data, aplicado, campo(r"Renda Bruta \(R\$\):"),
                                       campo(r"IOF\*:"), campo(r"IR \(R\$\):"), liquido)
    return _tabela(lancamentos, conta)


def sem_lancamentos(texto):
    """(conta, motivo) quando o PDF é reconhecido mas não tem o que importar."""
    if eh_boleto_fatura_sicoob(texto):
        return "Sicoob Cartão", ("é o boleto da fatura (só o total e o código de barras); envie "
                                 "a fatura detalhada: Sicoobnet → Cartões → Detalhamento")
    if re.search(r"Invest Fácil|INVEST FAC", texto) and "Valor Principal" in texto \
            and "Lançamento" not in texto and "Total Aplicado" not in texto:
        return "Bradesco Invest Fácil", ("só saldos mensais da aplicação; as aplicações, resgates "
                                         "e rendimentos vêm do resumo do período (Investimentos "
                                         "Bradesco)")
    return None


LEITORES = [
    (eh_extrato_caixa_sem_movimento, ler_extrato_caixa_sem_movimento, False),
    (eh_resumo_invest_facil, ler_resumo_invest_facil, True),
    (eh_extrato_bb, ler_extrato_bb, True),
    (eh_extrato_bradesco, ler_extrato_bradesco, True),
    (eh_fatura_bradesco, ler_fatura_bradesco, False),
    (eh_extrato_itau, ler_extrato_itau, True),
    (eh_fatura_itau, ler_fatura_itau, False),
    (eh_fatura_sicoob, ler_fatura_sicoob, False),
    (eh_extrato_sicoob, ler_extrato_sicoob, False),
    (eh_extrato_caixa, ler_extrato_caixa, False),
    (eh_extrato_santander, ler_extrato_santander, True),
    (eh_extrato_santander_pj, ler_extrato_santander_pj, True),
]


def ler_pdf_de_banco(texto, conteudo):
    """Tabela de transações do PDF, ou None se nenhum leitor daqui reconhece o layout.

    texto: o texto simples do pypdf (usado para reconhecer o banco).
    """
    texto = texto.replace("\xa0", " ")
    vazio = sem_lancamentos(texto)
    if vazio:
        raise SemLancamentos(*vazio)
    for reconhece, ler, layout in LEITORES:
        if reconhece(texto):
            return ler(texto_em_layout(conteudo) if layout else texto)
    return None
