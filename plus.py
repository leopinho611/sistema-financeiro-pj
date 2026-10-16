"""
Análises da área Plus: Imposto de Renda, gastos recorrentes, parcelas futuras do
cartão e indicadores de saúde financeira.

Tudo é calculado a partir das transações já processadas (financeiro.consolidar),
sem guardar nada.
"""

import re

import pandas as pd

from financeiro import chave_fornecedor, extrair_cnpj, normalizar

# ============================================================================
# PARCELAS FUTURAS DO CARTÃO
# ============================================================================
COLUNAS_PARCELAS = ["Fornecedor", "Conta", "Valor da parcela", "Parcela atual", "Parcelas",
                    "Restam", "Total restante", "Última parcela"]


def _referencia_por_conta(t):
    """Fechamento mais recente de cada cartão: a partir dele contam as parcelas futuras."""
    return t.groupby("Conta")["Data"].max()


def parcelas_futuras(t):
    """Compras parceladas que ainda têm parcelas a vencer.

    Retorna (tabela por compra, cronograma por mês). A mesma compra aparece em várias
    faturas (parcela 1/10, 2/10...); ela é identificada pelo fornecedor, pelo número de
    parcelas e pela data original da compra (o valor pode variar 1 centavo). Se faltar
    alguma fatura recente, a parcela atual é estimada pelos meses que se passaram.
    """
    if t.empty or "Parcela" not in t:
        return pd.DataFrame(columns=COLUNAS_PARCELAS), pd.DataFrame(columns=["Mês", "Valor"])
    p = t[(t["Tipo"] == "Saída") & t["Parcela"].notna() & t["Parcelas"].notna()].copy()
    if p.empty:
        return pd.DataFrame(columns=COLUNAS_PARCELAS), pd.DataFrame(columns=["Mês", "Valor"])
    referencia = _referencia_por_conta(t[t["Conta"].isin(p["Conta"])])
    p["_k"] = p["Fornecedor"].map(chave_fornecedor)
    # A compra é identificada pelo mês da 1ª parcela (mês da fatura - parcelas já pagas):
    # a data impressa nem sempre é a da compra (a anuidade traz a data de cada mês)
    # e o valor pode variar 1 centavo entre parcelas
    p["_compra"] = [d.to_period("M") - (int(k) - 1) for d, k in zip(p["Data"], p["Parcela"])]
    p = p.sort_values("Data")
    compras = (p.groupby(["Conta", "_k", "Parcelas", "_compra"])
               .agg(Fornecedor=("Fornecedor", "last"), Parcela=("Parcela", "max"),
                    Valor=("Valor", "last"), Data=("Data", "max"))
               .reset_index())

    linhas, cronograma = [], {}
    for c in compras.itertuples():
        ref = referencia[c.Conta]
        meses_depois = (ref.year - c.Data.year) * 12 + ref.month - c.Data.month
        atual = int(c.Parcela) + max(0, meses_depois)
        restam = int(c.Parcelas) - atual
        if restam <= 0:
            continue
        valor = abs(c.Valor)
        mes_ref = ref.to_period("M")
        for i in range(1, restam + 1):
            mes = str(mes_ref + i)
            cronograma[mes] = cronograma.get(mes, 0.0) + valor
        linhas.append({
            "Fornecedor": c.Fornecedor, "Conta": c.Conta, "Valor da parcela": valor,
            "Parcela atual": atual, "Parcelas": int(c.Parcelas), "Restam": restam,
            "Total restante": valor * restam, "Última parcela": str(mes_ref + restam),
        })
    tabela = pd.DataFrame(linhas, columns=COLUNAS_PARCELAS)
    tabela = tabela.sort_values("Total restante", ascending=False).reset_index(drop=True)
    meses = pd.DataFrame(sorted(cronograma.items()), columns=["Mês", "Valor"])
    return tabela, meses


# ============================================================================
# GASTOS RECORRENTES
# ============================================================================
COLUNAS_RECORRENTES = ["Fornecedor", "Categoria", "Tipo", "Por mês", "Meses", "Última",
                       "Próxima prevista", "Situação"]
FIXO = "Valor fixo"
CONTA_MENSAL = "Conta mensal (valor varia)"
FREQUENTE = "Gasto frequente"


def gastos_recorrentes(t, min_meses=3, variacao_fixo=0.15, frequencia_minima=0.5):
    """Fornecedores que aparecem quase todo mês.

    - Valor fixo: valor parecido todo mês (assinatura, mensalidade, seguro)
    - Conta mensal: uma vez por mês, valor varia (luz, plano de saúde com coparticipação)
    - Gasto frequente: várias vezes por mês ou nem todo mês (padaria, mercado)
    Os dois primeiros ganham data prevista para o próximo. Quem não aparece desde antes
    do penúltimo mês dos extratos fica marcado como "Parou". Parcelas do cartão ficam de
    fora (estão em parcelas_futuras).
    """
    s = t[(t["Tipo"] == "Saída")].copy()
    if "Parcela" in s:
        s = s[s["Parcela"].isna()]
    if s.empty:
        return pd.DataFrame(columns=COLUNAS_RECORRENTES)
    todos_meses = pd.period_range(t["Data"].min(), t["Data"].max(), freq="M")
    s["_k"] = s["Fornecedor"].map(chave_fornecedor)
    s["_mes"] = s["Data"].dt.to_period("M")
    linhas = []
    for _, g in s.groupby("_k"):
        por_mes = g.groupby("_mes")["Valor"].sum().abs()
        if len(por_mes) < min_meses:
            continue
        primeiro, ultimo = por_mes.index.min(), por_mes.index.max()
        janela = [m for m in todos_meses if primeiro <= m <= ultimo]
        if len(por_mes) / max(1, len(janela)) < frequencia_minima:
            continue
        mediana = por_mes.median()
        # Fixo e conta mensal: um pagamento por mês (várias compras que somam parecido
        # todo mês continuam sendo gasto frequente)
        uma_vez_por_mes = len(g) / len(por_mes) <= 1.5
        fixo = (uma_vez_por_mes and mediana > 0
                and (por_mes - mediana).abs().max() / mediana <= variacao_fixo)
        conta = not fixo and uma_vez_por_mes and len(por_mes) / len(janela) >= 0.8
        tipo = FIXO if fixo else CONTA_MENSAL if conta else FREQUENTE
        ativo = ultimo >= todos_meses[-1] - 1
        ultima = g["Data"].max()
        proxima = ""
        if tipo != FREQUENTE and ativo:
            dia = int(g["Data"].dt.day.median())
            mes = ultimo + 1
            dia = min(dia, mes.days_in_month)
            proxima = f"{dia:02d}/{mes.month:02d}/{mes.year}"
        linhas.append({
            "Fornecedor": max(g["Fornecedor"].unique(), key=len),
            "Categoria": g["Categoria"].mode().iat[0],
            "Tipo": tipo,
            "Por mês": mediana if tipo != FREQUENTE else por_mes.sum() / len(janela),
            "Meses": f"{len(por_mes)} de {len(janela)}",
            "Última": ultima.strftime("%d/%m/%Y"),
            "Próxima prevista": proxima,
            "Situação": "Ativo" if ativo else f"Parou ({ultimo.month:02d}/{ultimo.year})",
        })
    tabela = pd.DataFrame(linhas, columns=COLUNAS_RECORRENTES)
    ordem = {FIXO: 0, CONTA_MENSAL: 1, FREQUENTE: 2}
    tabela["_o1"] = tabela["Situação"].ne("Ativo")
    tabela["_o2"] = tabela["Tipo"].map(ordem)
    return (tabela.sort_values(["_o1", "_o2", "Por mês"], ascending=[True, True, False])
            .drop(columns=["_o1", "_o2"]).reset_index(drop=True))


def compromissos_mensais(recorrentes):
    """Soma por mês do que é fixo ou conta mensal e ainda está ativo."""
    if recorrentes.empty:
        return 0.0
    ativos = recorrentes[(recorrentes["Situação"] == "Ativo")
                         & recorrentes["Tipo"].isin([FIXO, CONTA_MENSAL])]
    return float(ativos["Por mês"].sum())


# ============================================================================
# IMPOSTO DE RENDA
# ============================================================================
GRUPO_SAUDE = "Saúde (consultas, exames, hospitais, plano)"
GRUPO_EDUCACAO = "Educação (só ensino regular, com limite anual)"
GRUPO_PREVIDENCIA = "Previdência privada (PGBL)"
GRUPO_PENSAO = "Pensão alimentícia (judicial)"
SUBS_SAUDE_DEDUTIVEIS = {"Clínicas, consultas e exames", "Plano de saúde"}
_PADRAO_PGBL = re.compile(r"\b(pgbl|previdencia privada|previdencia complementar)\b")
_PADRAO_PENSAO = re.compile(r"\bpensao aliment")


def grupo_dedutivel(categoria, subcategoria, descricao):
    """Grupo de dedução do IRPF em que o gasto PODE entrar, ou None."""
    texto = normalizar(descricao)
    if _PADRAO_PGBL.search(texto):
        return GRUPO_PREVIDENCIA
    if _PADRAO_PENSAO.search(texto):
        return GRUPO_PENSAO
    if categoria == "SAÚDE" and subcategoria in SUBS_SAUDE_DEDUTIVEIS:
        return GRUPO_SAUDE
    if categoria == "EDUCAÇÃO":
        return GRUPO_EDUCACAO
    return None


def relatorio_ir(t, ano):
    """Possíveis deduções e rendimentos de um ano-calendário, para conferir com o contador.

    Retorna {"deducoes": por fornecedor, "rendimentos_pj": por fonte, "rendimentos_pf":
    por mês}. O CPF/CNPJ do prestador aparece quando está no extrato (Pix).
    """
    a = t[t["Data"].dt.year == ano]
    s = a[a["Tipo"] == "Saída"].copy()
    s["Grupo"] = [grupo_dedutivel(c, sc, d) for c, sc, d in
                  zip(s["Categoria"], s["Subcategoria"], s["Descrição"])]
    s = s.dropna(subset=["Grupo"])
    s["CNPJ"] = s["Descrição"].map(extrair_cnpj)
    deducoes = (s.groupby(["Grupo", "Fornecedor"])
                .agg(Total=("Valor", lambda v: -v.sum()), Pagamentos=("Valor", "count"),
                     CNPJ=("CNPJ", lambda v: next((x for x in v if x), "")))
                .reset_index().sort_values(["Grupo", "Total"], ascending=[True, False]))
    deducoes["CNPJ"] = deducoes["CNPJ"].map(formatar_cnpj)

    e = a[a["Tipo"] == "Entrada"].copy()
    pj = e[e["Subcategoria"] == "Recebido de empresas"].copy()
    pj["CNPJ"] = pj["Descrição"].map(extrair_cnpj)
    rend_pj = (pj.groupby("Fornecedor")
               .agg(Total=("Valor", "sum"), Pagamentos=("Valor", "count"),
                    CNPJ=("CNPJ", lambda v: next((x for x in v if x), "")))
               .reset_index().sort_values("Total", ascending=False))
    rend_pj["CNPJ"] = rend_pj["CNPJ"].map(formatar_cnpj)
    pf = e[e["Subcategoria"] == "Recebido de pessoas"]
    rend_pf = (pf.groupby("Mês")["Valor"].agg(Total="sum", Recebimentos="count")
               .reset_index())
    return {"deducoes": deducoes.reset_index(drop=True), "rendimentos_pj": rend_pj.reset_index(drop=True),
            "rendimentos_pf": rend_pf}


def formatar_cnpj(c):
    c = re.sub(r"\D", "", str(c or ""))
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else ""


# ============================================================================
# SAÚDE FINANCEIRA
# ============================================================================
BOM, ATENCAO, ALERTA = "bom", "atencao", "alerta"


def _status(valor, bom, atencao, maior_melhor=True):
    if maior_melhor:
        return BOM if valor >= bom else ATENCAO if valor >= atencao else ALERTA
    return BOM if valor <= bom else ATENCAO if valor <= atencao else ALERTA


def indicadores(t, fixos_por_mes=0.0, parcelas_proximo_mes=0.0, guardado=None):
    """Indicadores com semáforo. Cada item: nome, valor (texto), status e explicação.

    Os limites são referências comuns de educação financeira, não regras.
    """
    # Só meses com alguma entrada: meses com apenas o cartão (sem o extrato da conta)
    # fariam parecer que tudo foi gasto sem nada entrar
    meses_com_entrada = t.loc[t["Tipo"] == "Entrada", "Mês"].unique()
    t = t[t["Mês"].isin(meses_com_entrada)]
    entradas = t.loc[t["Tipo"] == "Entrada", "Valor"].sum()
    saidas = -t.loc[t["Tipo"] == "Saída", "Valor"].sum()
    meses = max(1, len(meses_com_entrada))
    ent_mes, sai_mes = entradas / meses, saidas / meses
    itens = []

    if entradas > 0:
        poupanca = (entradas - saidas) / entradas * 100
        itens.append({"nome": "Quanto sobra das entradas", "valor": f"{poupanca:.0f}%",
                      "status": _status(poupanca, 20, 10),
                      "explicacao": "Parte das entradas que não foi gasta. Referência: guardar "
                                    "pelo menos 10% a 20%."})

    mensal = t[t["Tipo"].isin(["Entrada", "Saída"])].groupby("Mês")["Valor"].sum()
    if len(mensal):
        vermelho = int((mensal < 0).sum())
        itens.append({"nome": "Meses no vermelho", "valor": f"{vermelho} de {len(mensal)}",
                      "status": _status(vermelho / len(mensal) * 100, 0, 25, maior_melhor=False),
                      "explicacao": "Meses em que saiu mais dinheiro do que entrou."})

    fontes = t[t["Tipo"] == "Entrada"].assign(_k=lambda d: d["Fornecedor"].map(chave_fornecedor))
    if entradas > 0 and not fontes.empty:
        maior = fontes.groupby("_k")["Valor"].sum().max() / entradas * 100
        itens.append({"nome": "Dependência da maior fonte", "valor": f"{maior:.0f}%",
                      "status": _status(maior, 30, 50, maior_melhor=False),
                      "explicacao": "Quanto das entradas veio de uma única fonte. Acima de 50%, "
                                    "perder esse cliente ou emprego pesa muito."})

    if ent_mes > 0 and fixos_por_mes:
        pct = fixos_por_mes / ent_mes * 100
        itens.append({"nome": "Compromissos mensais", "valor": f"{pct:.0f}%",
                      "status": _status(pct, 50, 70, maior_melhor=False),
                      "explicacao": "Contas, assinaturas e mensalidades que se repetem todo "
                                    "mês, sobre a média de entradas."})

    if ent_mes > 0 and parcelas_proximo_mes:
        pct = parcelas_proximo_mes / ent_mes * 100
        itens.append({"nome": "Parcelas do próximo mês", "valor": f"{pct:.0f}%",
                      "status": _status(pct, 10, 20, maior_melhor=False),
                      "explicacao": "Parcelas do cartão já contratadas para o próximo mês, "
                                    "comparadas com a média de entradas."})

    if guardado is not None and guardado > 0 and sai_mes > 0:
        reserva = guardado / sai_mes
        itens.append({"nome": "Reserva de emergência",
                      "valor": f"{reserva:.1f} meses".replace(".", ","),
                      "status": _status(reserva, 6, 3),
                      "explicacao": "Quantos meses de gastos o dinheiro guardado cobre. "
                                    "Referência: de 3 a 6 meses, ou mais para autônomos."})
    return itens
