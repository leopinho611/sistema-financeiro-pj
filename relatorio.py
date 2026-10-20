"""
Relatório Contas em Dia (área Plus): um PDF de 4 páginas, em linguagem simples.

1. Seu dinheiro em uma página: nota geral, números do período, destaques e o mês a mês
2. Para onde foi: categorias, subcategorias e maiores gastos
3. O que já está comprometido: próximos 3 meses, contas que se repetem e parcelas
4. Atenção, imposto e próximos passos: indicadores, prévia do IR, sugestões e como o
   relatório foi feito

montar_relatorio() calcula o conteúdo (testável, sem PDF); gerar_pdf() desenha.
Nada é guardado: o PDF é gerado na memória e entregue para download.
"""

import io
import math
import re
from datetime import datetime

import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

import plus
from financeiro import (CATEGORIA_APLICACAO, CATEGORIA_CARTAO, chave_fornecedor, formatar_reais, nao_identificado,
                        normalizar, resumo_categorias, resumo_mensal)

CATEGORIAS_VARIAVEIS = ["ALIMENTAÇÃO", "SHOPPING", "LAZER", "TRANSPORTE", "ASSINATURAS"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def rotulo_mes(mes):
    ano, m = str(mes).split("-")
    return f"{MESES[int(m) - 1]}/{ano[2:]}"


def _pct(v, casas=0):
    return f"{v:.{casas}f}%".replace(".", ",")


# ============================================================================
# CONTEÚDO
# ============================================================================
def _variacao_recente(t, meses_recentes=3, base_minima=300.0):
    """Categoria de saída que mais mudou: média dos últimos meses × média dos anteriores."""
    s = t[t["Tipo"] == "Saída"]
    meses = sorted(s["Mês"].unique())
    if len(meses) < meses_recentes + 2:
        return None
    por_mes = (s.assign(V=-s["Valor"]).pivot_table(index="Categoria", columns="Mês", values="V",
                                                 aggfunc="sum", fill_value=0))
    recente = por_mes[meses[-meses_recentes:]].mean(axis=1)
    anterior = por_mes[meses[:-meses_recentes]].mean(axis=1)
    base = anterior[anterior >= base_minima]
    if base.empty:
        return None
    var = ((recente[base.index] - base) / base * 100).sort_values()
    categoria = var.abs().idxmax()
    return {"categoria": categoria, "variacao": float(var[categoria]),
            "antes": float(base[categoria]), "agora": float(recente[categoria])}


def _nome_grupo(categoria, subcategoria):
    """Subcategoria quando ela diz algo; senão a categoria ("Viagens", "Educação")."""
    if subcategoria and subcategoria not in ("Outros", "Não identificados"):
        return subcategoria
    return categoria.capitalize()


# Palavras que não identificam quem recebeu ("PAGAMENTO PIX", "DEBITO CONVENIOS"...)
_GENERICAS = {"pagamento", "pagto", "pgto", "pix", "ted", "doc", "transferencia", "transf",
              "debito", "credito", "convenios", "convenio", "liquidacao", "boleto",
              "recebimento", "enviado", "enviada", "recebido", "recebida", "compra",
              "arrecadacao", "automatico", "conta", "nao", "identificado", "de", "da", "do",
              "por", "em", "cartao", "outros", "diversos", "titulo", "titulos"}


def fornecedor_generico(nome):
    """O nome do fornecedor só repete o tipo do lançamento (não diz quem recebeu)?"""
    palavras = [p for p in re.split(r"[^a-z0-9]+", normalizar(nome or "")) if p]
    return not palavras or all(p in _GENERICAS or p.isdigit() for p in palavras)


def qualidade_dos_dados(t):
    """O que falta nos extratos para o relatório ficar mais preciso."""
    s = t[t["Tipo"] == "Saída"].assign(V=lambda d: -d["Valor"])
    total = s["V"].sum()
    problemas = {"sem_nome": [], "faturas": 0.0, "faturas_n": 0}
    if total <= 0:
        return problemas
    for conta, g in s.groupby("Conta"):
        gen = g[g["Fornecedor"].map(fornecedor_generico)]
        if g["V"].sum() > 0 and gen["V"].sum() / g["V"].sum() >= 0.15 and gen["V"].sum() >= 500:
            problemas["sem_nome"].append({"conta": conta, "valor": gen["V"].sum(),
                                          "pct": gen["V"].sum() / g["V"].sum() * 100,
                                          "n": len(gen)})
    fat = s[s["Categoria"] == CATEGORIA_CARTAO]
    problemas["faturas"], problemas["faturas_n"] = fat["V"].sum(), len(fat)
    problemas["pct_faturas"] = fat["V"].sum() / total * 100
    return problemas


def _destaques(t, mensal, variacao, comprometido_mes, media_saidas, qualidade, n=3,
               juros=0.0, aplicacoes=None, entradas=0.0):
    """Os destaques mais relevantes deste caso, do mais para o menos importante.

    Cada candidato ganha uma nota pelo tamanho do efeito; frases com valores pequenos
    demais para importar não entram. Nada fala de renda: o que entrou pode ser salário,
    transferência ou reembolso; o que saiu é sempre gasto.
    """
    s = t[t["Tipo"] == "Saída"].assign(V=lambda d: -d["Valor"])
    candidatos = []   # (nota, frase)

    if juros >= 50:
        candidatos.append((85 + min(15, juros / max(media_saidas, 1) * 100),
            f"<b>{formatar_reais(juros)} foram para juros, IOF e encargos</b> no período. É "
            "dinheiro que não compra nada: se houver rotativo do cartão ou cheque especial, "
            "quitar essa dívida primeiro costuma ser o melhor investimento."))
    if aplicacoes and aplicacoes["tem"] and entradas > 0:
        liq = aplicacoes["liquido"]
        if liq < 0 and -liq >= 0.05 * entradas:
            candidatos.append((75,
                f"<b>Você resgatou {formatar_reais(-liq)} a mais do que aplicou.</b> As "
                f"aplicações ajudaram a cobrir gastos em {aplicacoes['meses_resgatando']} "
                f"de {aplicacoes['meses']} meses, e a reserva diminuiu."))
        # Acima de 80% do que entrou não é poupança plausível: há aplicação automática ou
        # dinheiro vindo de outras contas no meio, e o % enganaria
        elif liq > 0 and 0.05 <= liq / entradas <= 0.8:
            candidatos.append((40 + min(30, liq / entradas * 100),
                f"<b>Você guardou {formatar_reais(liq)} em aplicações</b> no período, "
                f"{_pct(liq / entradas * 100)} do que entrou. A referência comum é guardar "
                "de 10% a 20%."))

    if qualidade["faturas"] and qualidade["pct_faturas"] >= 5:
        candidatos.append((90 + qualidade["pct_faturas"],
            f"<b>{formatar_reais(qualidade['faturas'])} foram para pagar faturas de cartão</b> "
            f"({_pct(qualidade['pct_faturas'])} das saídas), mas as faturas não foram enviadas. "
            "Sem elas, não dá para saber em que esse dinheiro foi gasto nem prever as "
            "parcelas que ainda vêm."))
    for q in sorted(qualidade["sem_nome"], key=lambda x: -x["valor"]):
        candidatos.append((80 + q["pct"] / 2,
            f"No extrato <b>{q['conta']}</b>, {_pct(q['pct'])} das saídas "
            f"({formatar_reais(q['valor'])}, {q['n']} lançamentos) vêm sem o nome de quem "
            "recebeu, só \"Pagamento Pix\" ou parecido. Isso limita a análise de para onde "
            "foi o dinheiro."))

    if len(mensal) > 1 and media_saidas:
        caro = mensal.loc[mensal["Saídas"].idxmax()]
        acima = caro["Saídas"] - media_saidas
        if acima / media_saidas >= 0.15:
            grupos = s.groupby(["Categoria", "Subcategoria", "Mês"])["V"].sum().unstack(
                fill_value=0)
            pesou = ""
            if caro["Mês"] in grupos:
                excesso = grupos[caro["Mês"]] - grupos.mean(axis=1)
                cat, sub = excesso.idxmax()
                if not fornecedor_generico(sub or cat) and cat not in ("TRANSFERÊNCIA",):
                    pesou = (f", e o que mais pesou foi {_nome_grupo(cat, sub)} "
                             f"({formatar_reais(grupos.loc[(cat, sub), caro['Mês']])})")
            candidatos.append((40 + min(40, acima / media_saidas * 50),
                f"<b>{rotulo_mes(caro['Mês']).capitalize()} foi o mês mais caro</b>: "
                f"{formatar_reais(caro['Saídas'])}, {_pct(acima / media_saidas * 100)} acima "
                f"da sua média{pesou}."))

    if variacao and abs(variacao["variacao"]) >= 15 \
            and abs(variacao["agora"] - variacao["antes"]) >= 100:
        verbo = "subiu" if variacao["variacao"] > 0 else "caiu"
        cat = variacao["categoria"]
        meses = sorted(s["Mês"].unique())
        sc = s[s["Categoria"] == cat]
        por_sub = sc.groupby(["Subcategoria", "Mês"])["V"].sum().unstack(fill_value=0) \
            .reindex(columns=meses, fill_value=0)
        puxada = ""
        if len(por_sub) > 1:
            dif = por_sub[meses[-3:]].mean(axis=1) - por_sub[meses[:-3]].mean(axis=1)
            sub = dif.idxmax() if verbo == "subiu" else dif.idxmin()
            if sub and sub not in ("Outros", "Não identificados"):
                puxada = f", principalmente em {sub}"
        diferenca = abs(variacao["agora"] - variacao["antes"])
        candidatos.append((35 + min(40, diferenca / max(media_saidas, 1) * 200),
            f"<b>{cat.capitalize()} {verbo} {_pct(abs(variacao['variacao']))}</b> nos últimos "
            f"3 meses{puxada}: passou de {formatar_reais(variacao['antes'])} para "
            f"{formatar_reais(variacao['agora'])} por mês, uma diferença de "
            f"{formatar_reais(diferenca)} por mês."))

    if comprometido_mes and media_saidas and comprometido_mes / media_saidas >= 0.3:
        pct = comprometido_mes / media_saidas * 100
        candidatos.append((30 + pct / 3,
            f"<b>{_pct(pct)} do que você gasta por mês já está comprometido</b> com contas "
            f"fixas e parcelas ({formatar_reais(comprometido_mes)}). É o valor que sai antes "
            "de qualquer escolha, e o que sobra é a margem para o resto."))

    transf = s[s["Categoria"] == "TRANSFERÊNCIA"]["V"].sum()
    # Se o extrato já não traz o nome de quem recebeu, o aviso acima diz o mesmo
    if s["V"].sum() and transf / s["V"].sum() >= 0.25 and not qualidade["sem_nome"]:
        pct = transf / s["V"].sum() * 100
        candidatos.append((45 + pct / 3,
            f"<b>{_pct(pct)} das saídas foram transferências e Pix para pessoas</b> "
            f"({formatar_reais(transf)}). Se parte disso for pagamento de serviços ou "
            "compras, classificar esses lançamentos deixa o retrato mais fiel."))

    if not s.empty and media_saidas:
        maior = s.loc[s["V"].idxmax()]
        if maior["V"] >= 0.25 * media_saidas and not fornecedor_generico(maior["Fornecedor"]):
            candidatos.append((20 + min(30, maior["V"] / media_saidas * 30),
                f"Seu maior gasto único foi <b>{formatar_reais(maior['V'])}</b> em "
                f"{maior['Fornecedor']}, em {maior['Data']:%d/%m/%Y}: "
                f"{_pct(maior['V'] / media_saidas * 100)} de um mês médio de gastos."))

    candidatos.sort(key=lambda c: -c[0])
    return [f for _, f in candidatos[:n]]


def _onde_foi(t, cats, var_cat, n_categorias=5, n_subs=3, n_maiores=3):
    """Maiores categorias, com subcategorias e maiores gastos (% sobre a categoria)."""
    s = t[t["Tipo"] == "Saída"].assign(V=lambda d: -d["Valor"])
    blocos = []
    for _, c in cats.head(n_categorias).iterrows():
        sc = s[s["Categoria"] == c["Categoria"]]
        total = c["Total"]
        subs = []
        por_sub = sc.groupby("Subcategoria")["V"].sum().sort_values(ascending=False)
        if len(por_sub) > 1 or (len(por_sub) == 1 and por_sub.index[0]):
            for nome, v in por_sub.head(n_subs).items():
                subs.append({"nome": nome or "Outros", "total": v, "pct": v / total * 100})
            resto = por_sub.iloc[n_subs:]
            if not resto.empty:
                subs.append({"nome": f"Outras ({len(resto)})", "total": resto.sum(),
                             "pct": resto.sum() / total * 100})
        forn = (sc.assign(_k=sc["Fornecedor"].map(chave_fornecedor))
                .groupby("_k").agg(nome=("Fornecedor", "first"), total=("V", "sum"),
                                   vezes=("V", "count"))
                .sort_values("total", ascending=False).head(n_maiores))
        maiores = [{"nome": f.nome, "total": f.total, "vezes": int(f.vezes),
                    "pct": f.total / total * 100} for f in forn.itertuples()]
        blocos.append({"categoria": c["Categoria"], "total": total,
                       "pct": c["% das saídas"], "var": var_cat.get(c["Categoria"]),
                       "subs": subs, "maiores": maiores})
    resto = cats.iloc[n_categorias:]
    demais = ({"n": len(resto), "total": resto["Total"].sum(),
               "pct": resto["% das saídas"].sum()} if not resto.empty else None)
    return blocos, demais


def _sugestoes(itens, cats, parcelas, saidas_mes, pct_nao_id, guardado, qualidade, n=3):
    """Os próximos passos mais úteis para este caso, do mais para o menos importante."""
    status = {i["nome"]: i for i in itens}
    meses = max(1, saidas_mes["n"])
    media = saidas_mes["media"]
    candidatos = []   # (nota, frase)

    if qualidade["faturas"] and qualidade["pct_faturas"] >= 5:
        candidatos.append((95,
            "<b>Envie também as faturas do cartão.</b> Com elas, os "
            f"{formatar_reais(qualidade['faturas'])} pagos em faturas viram compras "
            "separadas por categoria, e as parcelas futuras entram na previsão do que já "
            "está comprometido."))
    if qualidade["sem_nome"]:
        contas = ", ".join(q["conta"] for q in qualidade["sem_nome"])
        candidatos.append((70,
            f"<b>Experimente outro formato do extrato {contas}.</b> Às vezes o OFX ou o CSV "
            "trazem o nome de quem recebeu o Pix, que o PDF não mostra. Assim o relatório "
            "mostra para onde foi esse dinheiro."))

    # Teto só para gasto do dia a dia e só quando o valor faz diferença no mês
    sobra = status.get("Quanto sobra das entradas")
    variaveis = cats[cats["Categoria"].isin(CATEGORIAS_VARIAVEIS)]
    if not variaveis.empty and media:
        maior = variaveis.iloc[0]
        por_mes = maior["Total"] / meses
        if por_mes >= max(300.0, 0.08 * media):
            corte = por_mes * 0.10
            urgente = sobra and sobra["status"] != plus.BOM
            candidatos.append((60 if urgente else 40,
                f"<b>Defina um teto mensal para {maior['Categoria'].capitalize()}.</b> É seu "
                f"maior gasto do dia a dia, com média de {formatar_reais(por_mes)} por mês. "
                f"Um corte de 10% libera {formatar_reais(corte)} por mês, ou "
                f"{formatar_reais(corte * 12)} em um ano."))

    reserva = status.get("Reserva de emergência")
    if media and (reserva is None or reserva["status"] != plus.BOM):
        if guardado:
            falta = max(0.0, media * 6 - guardado)
            texto = (f"Hoje ela cobre {reserva['valor'] if reserva else '—'}; faltam "
                     f"{formatar_reais(falta)} para chegar a 6 meses.") if falta else ""
        else:
            texto = "Informe quanto você tem guardado para o relatório calcular quanto falta."
        candidatos.append((50,
            f"<b>Monte uma reserva de emergência</b> de 3 a 6 meses de gastos, entre "
            f"{formatar_reais(media * 3)} e {formatar_reais(media * 6)}. {texto} Separe um "
            "valor fixo logo que o dinheiro entrar, antes dos outros gastos."))

    vermelho = status.get("Meses no vermelho")
    if vermelho and vermelho["status"] == plus.ALERTA:
        candidatos.append((55,
            f"<b>Olhe com calma os meses no vermelho</b> ({vermelho['valor']}). Ver o que "
            "foi diferente nesses meses (viagem, conta anual, compra grande) ajuda a se "
            "preparar para eles com antecedência."))

    if not parcelas.empty and parcelas["Total restante"].sum() >= 0.3 * media:
        fim = rotulo_mes(parcelas["Última parcela"].max())
        candidatos.append((35,
            f"<b>Segure novas compras parceladas até {fim}</b>, quando terminam as atuais. "
            f"Ainda faltam {formatar_reais(parcelas['Total restante'].sum())} a pagar."))

    if pct_nao_id > 10:
        candidatos.append((45,
            f"<b>Classifique os gastos não identificados</b> ({_pct(pct_nao_id)} das saídas) "
            "na aba ⭐ Classificar. O app lembra nas próximas vezes e o relatório fica mais "
            "preciso."))

    candidatos.sort(key=lambda c: -c[0])
    return [f for _, f in candidatos[:n]]


# Essenciais × escolhas (referência comum de educação financeira)
ESSENCIAIS = {"CASA", "SAÚDE", "TRANSPORTE", "EDUCAÇÃO", "IMPOSTOS E TAXAS",
              "TARIFAS BANCÁRIAS"}
ESCOLHAS = {"LAZER", "SHOPPING", "ASSINATURAS"}
ALIMENTACAO_ESSENCIAL = {"Supermercado", "Padaria", "Feira", "Hortifruti e açougue"}


def tipo_de_gasto(categoria, subcategoria):
    """"essencial", "escolha" ou "outros" (transferências, não identificados, faturas)."""
    if categoria == "ALIMENTAÇÃO":
        return "essencial" if subcategoria in ALIMENTACAO_ESSENCIAL else "escolha"
    if categoria in ESSENCIAIS:
        return "essencial"
    if categoria in ESCOLHAS:
        return "escolha"
    return "outros"


def _aplicacoes(t):
    """Aplicações e resgates (movimentação interna) e rendimentos recebidos."""
    a = t[t["Categoria"] == CATEGORIA_APLICACAO]
    aplicado = -a.loc[a["Valor"] < 0, "Valor"].sum()
    resgatado = a.loc[a["Valor"] > 0, "Valor"].sum()
    rend = t[(t["Tipo"] == "Entrada") & (t["Subcategoria"] == "Rendimentos")]["Valor"].sum()
    por_mes = a.groupby("Mês")["Valor"].sum()   # negativo = aplicou mais do que resgatou
    return {"tem": not a.empty or rend > 0, "aplicado": aplicado, "resgatado": resgatado,
            "liquido": aplicado - resgatado, "rendimentos": rend,
            "meses_resgatando": int((por_mes > 0).sum()), "meses": int(por_mes.size)}


def _juros_e_encargos(t):
    s = t[t["Tipo"] == "Saída"]
    j = s[(s["Subcategoria"] == "IOF e juros")
          | s["Descrição"].map(lambda d: bool(re.search(r"rotativ|juros|encargo|multa atraso",
                                                        normalizar(d))))]
    return float(-j["Valor"].sum())


def _melhorias(t, n_meses, qualidade, aplicacoes):
    """O que deixaria o relatório mais completo (para o fim do relatório)."""
    m = []
    if n_meses < 12:
        m.append(f"<b>Use pelo menos 12 meses de extrato</b> (este relatório tem {n_meses}). "
                 "Assim aparecem os gastos que só acontecem uma vez por ano: 13º, IPVA, IPTU, "
                 "férias, matrícula e fim de ano.")
    if qualidade["faturas"]:
        m.append("<b>Envie as faturas do cartão.</b> Os pagamentos de fatura aparecem, mas "
                 "sem as compras e sem as parcelas que ainda vêm.")
    for q in qualidade["sem_nome"]:
        m.append(f"<b>O extrato {q['conta']} não mostra o nome de quem recebeu</b> em "
                 f"{_pct(q['pct'])} das saídas. Se o banco oferecer OFX ou CSV, eles costumam "
                 "trazer esse nome.")
    if not aplicacoes["tem"]:
        m.append("<b>Não encontramos aplicações nem rendimentos.</b> Se você tem dinheiro "
                 "guardado em conta investimento, poupança ou corretora, envie esse extrato: o "
                 "relatório passa a calcular quanto você guarda por mês e o rendimento.")
    s = t[t["Tipo"] == "Saída"]
    carro = s[(s["Categoria"] == "TRANSPORTE")
              & s["Subcategoria"].isin(["Posto de gasolina", "Seguro"])]
    ipva = s["Descrição"].map(lambda d: "ipva" in normalizar(d)).any() \
        or (s["Subcategoria"] == "IPVA e multas").any()
    if len(carro) >= 3 and not ipva:
        m.append("<b>Há gastos com carro (combustível ou seguro), mas o IPVA não apareceu.</b> "
                 "Se ele foi pago por outra conta ou fora do período, não entrou nas contas; "
                 "vale reservar esse valor para o próximo ano.")
    casa = s[(s["Categoria"] == "CASA") & s["Subcategoria"].isin(["Condomínio", "Luz", "Água"])]
    iptu = s["Descrição"].map(lambda d: "iptu" in normalizar(d)).any()
    if n_meses >= 12 and len(casa) >= 6 and not iptu and \
            not (s["Subcategoria"] == "Aluguel").any():
        m.append("<b>O IPTU não apareceu.</b> Se você tem imóvel próprio, ele pode ter sido "
                 "pago por outra conta.")
    return m


LIMITES = ("Este relatório enxerga só o que passou pelas contas e cartões enviados. Ficam de "
           "fora: dívidas fora do cartão (empréstimos e financiamentos), bens (imóveis e "
           "veículos), previdência e qualquer renda ou gasto feito por outras contas.")


def montar_relatorio(t, guardado=None, hoje=None):
    """Tudo o que vai no relatório, calculado a partir das transações já processadas."""
    hoje = hoje or datetime.now()
    mov = t[t["Tipo"].isin(["Entrada", "Saída"])]
    entradas = t.loc[t["Tipo"] == "Entrada", "Valor"].sum()
    saidas = -t.loc[t["Tipo"] == "Saída", "Valor"].sum()
    mensal = resumo_mensal(t)
    n_meses = max(1, mensal["Mês"].nunique())
    cats = resumo_categorias(t)

    recorrentes = plus.gastos_recorrentes(t)
    compromissos = plus.compromissos_mensais(recorrentes)
    parcelas, cronograma = plus.parcelas_futuras(t)
    parcela_prox = float(cronograma["Valor"].iloc[0]) if not cronograma.empty else 0.0
    itens = plus.indicadores(t, compromissos, parcela_prox, guardado)

    # Nota geral: o pior dos indicadores, com quantos estão em cada situação
    contagem = {s: sum(i["status"] == s for i in itens) for s in (plus.BOM, plus.ATENCAO,
                                                                    plus.ALERTA)}
    nota = (plus.ALERTA if contagem[plus.ALERTA] >= 2 else
            plus.ATENCAO if contagem[plus.ALERTA] or contagem[plus.ATENCAO] else plus.BOM)

    s = t[t["Tipo"] == "Saída"]
    nao_id = s[[nao_identificado(c, sc) for c, sc in zip(s["Categoria"], s["Subcategoria"])]]
    pct_nao_id = nao_id["Valor"].sum() / s["Valor"].sum() * 100 if s["Valor"].sum() else 0

    variacao = _variacao_recente(t)
    qualidade = qualidade_dos_dados(t)
    aplicacoes = _aplicacoes(t)
    juros = _juros_e_encargos(t)
    gasto_tipo = s.assign(T=[tipo_de_gasto(c, sc) for c, sc in
                             zip(s["Categoria"], s["Subcategoria"])], V=-s["Valor"]) \
        .groupby("T")["V"].sum().to_dict()
    # Variação de cada categoria: últimos 3 meses × média anterior
    meses = sorted(s["Mês"].unique())
    var_cat = {}
    if len(meses) >= 5:
        pv = s.assign(V=-s["Valor"]).pivot_table(index="Categoria", columns="Mês", values="V",
                                                 aggfunc="sum", fill_value=0)
        rec, ant = pv[meses[-3:]].mean(axis=1), pv[meses[:-3]].mean(axis=1)
        var_cat = {c: (rec[c] - ant[c]) / ant[c] * 100 for c in pv.index if ant[c] >= 100}

    onde_foi, demais = _onde_foi(t, cats, var_cat)

    # Já comprometido nos próximos 3 meses: contas que se repetem + parcelas do cartão
    ultimo = pd.Period(t["Data"].max(), freq="M")
    proximos = [str(ultimo + i) for i in (1, 2, 3)]
    crono = dict(zip(cronograma["Mês"], cronograma["Valor"])) if not cronograma.empty else {}
    comprometido = [{"Mês": m, "Contas fixas": compromissos, "Parcelas": crono.get(m, 0.0)}
                    for m in proximos]

    # Séries mês a mês para os gráficos: contas que se repetem (histórico) e parcelas (futuro)
    fixos = recorrentes[(recorrentes["Situação"] == "Ativo")
                        & recorrentes["Tipo"].isin([plus.FIXO, plus.CONTA_MENSAL])]
    hist_fixos = plus.historico_recorrentes(t, fixos)
    serie_parcelas = plus.cronograma_por_compra(parcelas)

    anos = sorted(t["Data"].dt.year.unique())
    ir = plus.relatorio_ir(t, anos[-1]) if anos else None

    return {
        "gerado_em": hoje, "inicio": t["Data"].min(), "fim": t["Data"].max(),
        "contas": sorted(t["Conta"].unique()), "transacoes": len(mov),
        "entradas": entradas, "saidas": saidas, "sobra": entradas - saidas,
        "media_entradas": entradas / n_meses, "media_saidas": saidas / n_meses,
        "n_meses": n_meses, "mensal": mensal, "categorias": cats, "var_cat": var_cat,
        "onde_foi": onde_foi, "demais": demais, "hist_fixos": hist_fixos,
        "serie_parcelas": serie_parcelas, "recorrentes": recorrentes,
        "compromissos": compromissos,
        "parcelas": parcelas, "comprometido": comprometido, "indicadores": itens,
        "nota": nota, "contagem": contagem, "pct_nao_id": pct_nao_id, "guardado": guardado,
        "ano_ir": anos[-1] if anos else None, "ir": ir,
        "qualidade": qualidade, "aplicacoes": aplicacoes, "juros": juros,
        "gasto_tipo": {k: v / n_meses for k, v in gasto_tipo.items()},
        "melhorias": _melhorias(t, n_meses, qualidade, aplicacoes), "limites": LIMITES,
        "destaques": _destaques(t, mensal, variacao, compromissos + parcela_prox,
                                saidas / n_meses, qualidade, juros=juros,
                                aplicacoes=aplicacoes, entradas=entradas),
        "sugestoes": _sugestoes(itens, cats, parcelas,
                                {"n": n_meses, "media": saidas / n_meses}, pct_nao_id, guardado,
                                qualidade),
    }


# ============================================================================
# PDF
# ============================================================================
MARINHO = colors.HexColor("#14213d")
MARINHO_2 = colors.HexColor("#1b2a4a")
DOURADO = colors.HexColor("#c9a227")
OSSO = colors.HexColor("#f7f3ea")
OSSO_2 = colors.HexColor("#ece4d2")
CINZA = colors.HexColor("#5b6275")
LINHA = colors.HexColor("#d9d2c0")
COR_ENTRADAS = colors.HexColor("#3d6bc4")
COR_SAIDAS = colors.HexColor("#a8801f")
SINAL = {plus.BOM: (colors.HexColor("#0ca30c"), "Bom"),
         plus.ATENCAO: (colors.HexColor("#d99a00"), "Atenção"),
         plus.ALERTA: (colors.HexColor("#d03b3b"), "Alerta")}
NOTA_TEXTO = {plus.BOM: "Suas finanças estão saudáveis",
              plus.ATENCAO: "Suas finanças pedem atenção em alguns pontos",
              plus.ALERTA: "Suas finanças precisam de ajustes"}

LARGURA = A4[0] - 36 * mm


def _estilos():
    base = dict(fontName="Helvetica", textColor=MARINHO, leading=13, fontSize=9.5)
    return {
        "titulo": ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=15, leading=19,
                                 textColor=MARINHO, spaceBefore=4, spaceAfter=6),
        "sub": ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=11, leading=14,
                              textColor=MARINHO, spaceBefore=8, spaceAfter=4),
        "texto": ParagraphStyle("texto", **base),
        "pequeno": ParagraphStyle("pequeno", **{**base, "fontSize": 8, "leading": 10.5,
                                                "textColor": CINZA}),
        "item": ParagraphStyle("item", **{**base, "leftIndent": 10, "bulletIndent": 0,
                                          "spaceAfter": 4}),
        "kpi_rot": ParagraphStyle("kpi_rot", **{**base, "fontSize": 8, "textColor": CINZA}),
        "kpi_val": ParagraphStyle("kpi_val", **{**base, "fontName": "Helvetica-Bold",
                                                "fontSize": 13, "leading": 16}),
        "cel": ParagraphStyle("cel", **{**base, "fontSize": 8.5, "leading": 11}),
        "cel_dir": ParagraphStyle("cel_dir", **{**base, "fontSize": 8.5, "leading": 11,
                                                "alignment": TA_RIGHT}),
        "cel_cab": ParagraphStyle("cel_cab", **{**base, "fontSize": 8, "leading": 10,
                                                "textColor": CINZA}),
        "cel_cab_dir": ParagraphStyle("cel_cab_dir", **{**base, "fontSize": 8, "leading": 10,
                                                        "textColor": CINZA,
                                                        "alignment": TA_RIGHT}),
        "centro": ParagraphStyle("centro", **{**base, "alignment": TA_CENTER}),
    }


def _cabecalho_rodape(dados):
    periodo = f"{dados['inicio']:%d/%m/%Y} a {dados['fim']:%d/%m/%Y}"

    def desenhar(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(MARINHO_2)
        c.rect(0, h - 22 * mm, w, 22 * mm, stroke=0, fill=1)
        c.setFillColor(DOURADO)
        c.rect(0, h - 23 * mm, w, 1 * mm, stroke=0, fill=1)
        c.setFillColor(OSSO)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(18 * mm, h - 12 * mm, "Relatório Contas em Dia")
        c.setFont("Helvetica", 9)
        c.drawString(18 * mm, h - 17.5 * mm, f"Período: {periodo}  ·  "
                                             f"{', '.join(dados['contas'])}")
        c.setFillColor(DOURADO)
        c.setFont("Helvetica-Oblique", 9)
        c.drawRightString(w - 18 * mm, h - 12 * mm, "Seus gastos na palma da mão")
        c.setFillColor(CINZA)
        c.setFont("Helvetica", 7.5)
        c.drawString(18 * mm, 10 * mm, f"Gerado em {dados['gerado_em']:%d/%m/%Y %H:%M}. "
                                       "Os extratos não foram guardados. Confira os valores "
                                       "com seu contador antes de decisões fiscais.")
        c.drawRightString(w - 18 * mm, 10 * mm, f"Página {doc.page}")
        c.restoreState()
    return desenhar


def _tabela(linhas, larguras, cabecalho=True, zebra=True):
    t = Table(linhas, colWidths=larguras, hAlign="LEFT")
    estilo = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
              ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
              ("LINEBELOW", (0, -1), (-1, -1), 0.5, LINHA)]
    if cabecalho:
        estilo.append(("LINEBELOW", (0, 0), (-1, 0), 0.8, DOURADO))
    if zebra:
        for i in range(1 if cabecalho else 0, len(linhas)):
            if i % 2 == 0:
                estilo.append(("BACKGROUND", (0, i), (-1, i), OSSO))
    t.setStyle(TableStyle(estilo))
    return t


def _cartoes_kpi(dados, e):
    def cartao(rotulo, valor, cor=MARINHO):
        return [Paragraph(rotulo, e["kpi_rot"]),
                Paragraph(f'<font color="{cor.hexval()}">{valor}</font>', e["kpi_val"])]
    sobra = dados["sobra"]
    reserva = (f"{dados['guardado'] / dados['media_saidas']:.1f} meses".replace(".", ",")
               if dados["guardado"] and dados["media_saidas"] else "não informada")
    celulas = [cartao("Entrou", formatar_reais(dados["entradas"])),
               cartao("Saiu", formatar_reais(dados["saidas"])),
               cartao("Sobrou" if sobra >= 0 else "Faltou", formatar_reais(abs(sobra)),
                      SINAL[plus.BOM][0] if sobra >= 0 else SINAL[plus.ALERTA][0]),
               cartao("Reserva de emergência", reserva)]
    t = Table([celulas], colWidths=[LARGURA / 4] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OSSO),
        ("LINEBEFORE", (0, 0), (-1, -1), 3, DOURADO),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _nota_geral(dados, e):
    cor, rotulo = SINAL[dados["nota"]]
    c = dados["contagem"]
    detalhe = (f"{c[plus.BOM]} indicador(es) bom(ns), {c[plus.ATENCAO]} em atenção e "
               f"{c[plus.ALERTA]} em alerta. Detalhes na última página.")
    d = Drawing(LARGURA, 46)
    d.add(Rect(0, 0, LARGURA, 46, fillColor=OSSO, strokeColor=None))
    d.add(Rect(0, 0, 5, 46, fillColor=cor, strokeColor=None))
    d.add(Rect(14, 15, 70, 18, rx=9, ry=9, fillColor=cor, strokeColor=None))
    d.add(String(49, 20.5, rotulo, fontName="Helvetica-Bold", fontSize=10,
                 fillColor=colors.white, textAnchor="middle"))
    d.add(String(96, 26, NOTA_TEXTO[dados["nota"]], fontName="Helvetica-Bold", fontSize=12,
                 fillColor=MARINHO))
    d.add(String(96, 12, detalhe, fontName="Helvetica", fontSize=8.5, fillColor=CINZA))
    return d


# Cores das linhas (validadas para contraste e daltonismo; mesma ordem do app)
CORES_SERIES = [colors.HexColor(c) for c in ("#3987e5", "#d95926", "#199e70", "#c98500",
                                             "#d55181", "#008300", "#9085e9", "#e66767")]
COR_TOTAL = colors.HexColor("#8c8c8c")


def _compacto(v):
    """Valor curto para rótulo de ponto: 850 / 7,3 mil / 12 mil."""
    if abs(v) >= 10000:
        return f"{v / 1000:.0f} mil"
    if abs(v) >= 1000:
        return f"{v / 1000:.1f} mil".replace(".", ",")
    return f"{v:.0f}"


def _topo(maximo):
    """Topo "redondo" do eixo com 4 faixas (passos redondos × 10ⁿ), com folga."""
    if maximo <= 0:
        return 1.0
    alvo = maximo * 1.12
    base = 10 ** int(f"{alvo / 4:e}".split("e")[1])
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10):
        if base * m * 4 >= alvo:
            return base * m * 4
    return alvo


def _afastar(posicoes, distancia, minimo, maximo):
    """Afasta rótulos (dict nome -> y) para não se sobreporem, dentro de [minimo, maximo]."""
    ordem = sorted(posicoes, key=posicoes.get)
    for a, b in zip(ordem, ordem[1:]):
        posicoes[b] = max(posicoes[b], posicoes[a] + distancia)
    if ordem and posicoes[ordem[-1]] > maximo:
        posicoes[ordem[-1]] = maximo
        for a, b in zip(reversed(ordem), list(reversed(ordem))[1:]):
            posicoes[b] = min(posicoes[b], posicoes[a] - distancia)
    for k in posicoes:
        posicoes[k] = max(posicoes[k], minimo)
    return posicoes


def _grafico_linhas(series, meses, altura=170, valores="todos", largura_nomes=118):
    """Gráfico de linhas: uma linha por série, o nome no fim da linha.

    series: lista de (nome, cor, {mês: valor}, total?) na ordem do maior para o menor.
    valores="todos" escreve o valor em cada ponto; "fim" escreve só no fim, junto do nome.
    """
    from reportlab.graphics.shapes import Circle, Line, PolyLine
    esq, base, topo_px = 34, 16, altura - 8
    dir_ = LARGURA - largura_nomes
    d = Drawing(LARGURA, altura)
    maximo = max((v for _, _, pts, *_ in series for v in pts.values()), default=0)
    topo = _topo(maximo)
    passo_x = (dir_ - esq - 16) / max(1, len(meses) - 1)
    xs = {m: esq + 8 + i * passo_x for i, m in enumerate(meses)}

    def y(v):
        return base + (topo_px - base) * v / topo

    # Grade e eixos (discretos)
    for k in range(5):
        v = topo * k / 4
        d.add(Line(esq, y(v), dir_, y(v), strokeColor=colors.HexColor("#ebe6da"),
                   strokeWidth=0.5))
        d.add(String(esq - 4, y(v) - 2.5, f"{v:,.0f}".replace(",", "."), fontName="Helvetica",
                     fontSize=6.5, fillColor=CINZA, textAnchor="end"))
    for m, x in xs.items():
        d.add(String(x, base - 11, rotulo_mes(m), fontName="Helvetica", fontSize=6.5,
                     fillColor=CINZA, textAnchor="middle"))

    rotulos_ponto = {m: {} for m in meses}
    fins = {}
    for nome, cor, pts, *extra in series:
        total = bool(extra and extra[0])
        ms = [m for m in meses if m in pts]
        if not ms:
            continue
        coords = []
        for m in ms:
            coords += [xs[m], y(pts[m])]
        if len(ms) > 1:
            d.add(PolyLine(coords, strokeColor=cor, strokeWidth=2 if total else 1.6,
                           strokeDashArray=[4, 3] if total else None))
        for m in ms:
            d.add(Circle(xs[m], y(pts[m]), 2.3, fillColor=cor, strokeColor=colors.white,
                         strokeWidth=0.6))
            if valores == "todos":
                rotulos_ponto[m][nome] = (y(pts[m]), pts[m])
        fins.setdefault(ms[-1], {})[nome] = (y(pts[ms[-1]]), pts[ms[-1]], total)

    # Valor em cada ponto: o da linha mais alta vai em cima do ponto e os das outras
    # embaixo (assim o rótulo não encosta na linha de cima), afastados entre si
    for m, rot in rotulos_ponto.items():
        if not rot:
            continue
        alto = max(rot, key=lambda k: rot[k][0])
        abaixo = _afastar({k: v[0] - 10 for k, v in rot.items() if k != alto}, 9, base + 1,
                          altura - 4)
        for k, yy in list(abaixo.items()) + [(alto, rot[alto][0] + 5)]:
            d.add(String(xs[m], yy, _compacto(rot[k][1]), fontName="Helvetica", fontSize=6,
                         fillColor=MARINHO, textAnchor="middle"))
    # Nome no fim de cada linha
    for m, grupo in fins.items():
        pos = _afastar({k: v[0] - 2.5 for k, v in grupo.items()}, 9, base - 2, altura - 6)
        for k, yy in pos.items():
            texto = k if valores == "todos" else f"{k}  {formatar_reais(grupo[k][1])}"
            limite = 34 if m == meses[-1] else 26
            texto = texto if len(texto) <= limite else texto[:limite - 1] + "…"
            d.add(String(xs[m] + 6, yy, texto, fontSize=7, fillColor=MARINHO,
                         fontName="Helvetica-Bold" if grupo[k][2] else "Helvetica"))
    return d


def _series_de(longo, max_series=6, nome_total="Total"):
    """(nome, cor, {mês: valor}) por série a partir de Mês/Fornecedor/Valor, mais o total."""
    ordem = longo.groupby("Fornecedor")["Valor"].sum().sort_values(ascending=False).index
    if len(ordem) > max_series:
        resto = set(ordem[max_series:])
        longo = longo.assign(Fornecedor=longo["Fornecedor"].where(
            ~longo["Fornecedor"].isin(resto), f"Outros ({len(resto)})"))
        ordem = list(ordem[:max_series]) + [f"Outros ({len(resto)})"]
    por = longo.groupby(["Fornecedor", "Mês"])["Valor"].sum()
    total = longo.groupby("Mês")["Valor"].sum().to_dict()
    series = [(nome_total, COR_TOTAL, total, True)]
    series += [(n, CORES_SERIES[i % len(CORES_SERIES)], por[n].to_dict())
               for i, n in enumerate(ordem)]
    return series, sorted(longo["Mês"].unique())


def _barra_pct(pct, largura=60, cor=COR_SAIDAS):
    d = Drawing(largura, 8)
    d.add(Rect(0, 1, largura, 5, fillColor=colors.HexColor("#ebe6da"), strokeColor=None))
    d.add(Rect(0, 1, largura * min(1, max(0, pct / 100)), 5, fillColor=cor, strokeColor=None))
    return d


def _mil(v):
    """Valor em milhares para rótulo curto: 10 / 9,9 / 0,5 (com sinal)."""
    a = abs(v) / 1000
    if a < 0.05:
        return "0"
    texto = f"{a:.0f}" if a >= 10 else f"{a:.1f}".replace(".", ",")
    return ("+" if v >= 0 else "-") + texto


def _grafico_cascata_mensal(mensal, altura=260):
    """Cascata mês a mês com duas barras por mês: a entrada sobe (azul) e a saída desce
    (dourado), sempre a partir de onde o mês anterior terminou. A última barra (cinza) é o
    acumulado do período. Rótulos em R$ mil para caber."""
    from reportlab.graphics.shapes import Line
    meses = list(mensal.itertuples(index=False))
    esq, dir_, base, topo_px = 36, LARGURA - 4, 22, altura - 24
    vagas = 2 * len(meses) + 1.6            # 2 barras por mês + o acumulado (um pouco mais largo)
    vaga = (dir_ - esq) / (vagas + 0.35 * len(meses))   # e um respiro entre os meses
    barra, respiro = vaga * 0.86, vaga * 0.35
    niveis, nivel = [0.0], 0.0
    for m in meses:
        niveis += [nivel + m.Entradas, nivel + m.Entradas - m.Saídas]
        nivel = niveis[-1]
    vmin, vmax = min(niveis), max(niveis)
    passo = _topo((vmax - vmin) or 1) / 4
    vmax = math.ceil(vmax / passo) * passo
    vmin = math.floor(vmin / passo) * passo if vmin < 0 else 0
    faixa = (vmax - vmin) or 1

    def y(v):
        return base + (topo_px - base) * (v - vmin) / faixa

    d = Drawing(LARGURA, altura)
    for k in range(int(round(faixa / passo)) + 1):   # grade discreta
        v = vmin + passo * k
        d.add(Line(esq, y(v), dir_, y(v), strokeColor=colors.HexColor("#ebe6da"),
                   strokeWidth=0.5))
        d.add(String(esq - 4, y(v) - 2.5, f"{v:,.0f}".replace(",", "."), fontName="Helvetica",
                     fontSize=6, fillColor=CINZA, textAnchor="end"))
    if vmin < 0:
        d.add(Line(esq, y(0), dir_, y(0), strokeColor=CINZA, strokeWidth=0.6))

    def degrau(x, de, ate, cor, rotulo, largura=barra):
        baixo, alto = min(de, ate), max(de, ate)
        d.add(Rect(x, y(baixo), largura, max(0.8, y(alto) - y(baixo)), fillColor=cor,
                   strokeColor=None))
        d.add(String(x + largura / 2, y(alto) + 2.5, rotulo, fontName="Helvetica-Bold",
                     fontSize=5.6, fillColor=MARINHO, textAnchor="middle"))

    x, nivel, fim_anterior = esq + respiro / 2, 0.0, None
    for m in meses:
        if fim_anterior is not None:   # linha fina ligando um degrau ao próximo
            d.add(Line(fim_anterior, y(nivel), x, y(nivel), strokeColor=CINZA, strokeWidth=0.4))
        degrau(x, nivel, nivel + m.Entradas, COR_ENTRADAS, _mil(m.Entradas))
        topo = nivel + m.Entradas
        d.add(Line(x + barra, y(topo), x + vaga, y(topo), strokeColor=CINZA, strokeWidth=0.4))
        degrau(x + vaga, topo, topo - m.Saídas, COR_SAIDAS, _mil(-m.Saídas))
        d.add(String(x + vaga, base - 10, rotulo_mes(m.Mês), fontName="Helvetica",
                     fontSize=6, fillColor=MARINHO, textAnchor="middle"))
        nivel = topo - m.Saídas
        fim_anterior = x + vaga + barra
        x += 2 * vaga + respiro
    larg_total = barra * 1.6
    d.add(Line(fim_anterior, y(nivel), x, y(nivel), strokeColor=CINZA, strokeWidth=0.4))
    degrau(x, 0, nivel, COR_TOTAL, _mil(nivel), larg_total)
    d.add(String(x + larg_total / 2, base - 10, "Acumulado", fontName="Helvetica", fontSize=6,
                 fillColor=MARINHO, textAnchor="middle"))
    for k, (nome, cor) in enumerate([("Entrou", COR_ENTRADAS), ("Saiu", COR_SAIDAS),
                                     ("Acumulado do período", COR_TOTAL)]):
        lx = esq + k * 80
        d.add(Rect(lx, altura - 9, 8, 8, fillColor=cor, strokeColor=None))
        d.add(String(lx + 11, altura - 8, nome, fontName="Helvetica", fontSize=7,
                     fillColor=MARINHO))
    d.add(String(dir_, altura - 8, "valores nas barras em R$ mil", fontName="Helvetica-Oblique",
                 fontSize=6, fillColor=CINZA, textAnchor="end"))
    return d


def _pagina1(dados, e):
    h = [Paragraph("Seu dinheiro em uma página", e["titulo"]), _nota_geral(dados, e),
         Spacer(1, 8), _cartoes_kpi(dados, e), Spacer(1, 4),
         Paragraph(f"Média por mês: entrou {formatar_reais(dados['media_entradas'])} e saiu "
                   f"{formatar_reais(dados['media_saidas'])}, em {dados['n_meses']} mês(es). "
                   "O que entrou inclui tudo o que chegou às contas (salário, pagamentos, "
                   "transferências de outras pessoas e reembolsos).", e["pequeno"]),
         Paragraph("Destaques", e["sub"])]
    h += [Paragraph(f, e["item"], bulletText="•") for f in dados["destaques"]]
    h += [Paragraph("Quanto sobrou ou faltou em cada mês", e["sub"]),
          Paragraph("Em cada mês, a barra azul sobe com o que entrou e a dourada desce com o que "
                    "saiu, a partir de onde o mês anterior terminou. A barra cinza é o acumulado "
                    "do período.", e["pequeno"]), Spacer(1, 2),
          _grafico_cascata_mensal(dados["mensal"], altura=190)]
    gt = dados["gasto_tipo"]
    if gt:
        partes = []
        for chave, rotulo in [("essencial", "Essenciais (casa, mercado, saúde, transporte, "
                                            "educação, impostos)"),
                              ("escolha", "Escolhas (restaurantes, lazer, compras, "
                                          "assinaturas)"),
                              ("outros", "Sem classificação (transferências, faturas, não "
                                         "identificados)")]:
            if gt.get(chave):
                partes.append(f"{rotulo}: <b>{formatar_reais(gt[chave])}</b> por mês")
        h.append(Paragraph(" · ".join(partes) + ".", e["pequeno"]))
    return h + _secao_aplicacoes(dados, e)


def _secao_aplicacoes(dados, e):
    h = [Paragraph("Aplicações", e["sub"])]
    a = dados["aplicacoes"]
    if not a["tem"]:
        h.append(Paragraph("Não encontramos aplicações, resgates nem rendimentos nos extratos "
                           "enviados. Se você tem dinheiro guardado em conta investimento, "
                           "poupança ou corretora, envie esse extrato para o relatório "
                           "mostrar quanto você guarda e quanto rende.", e["texto"]))
        return h
    linhas = [[Paragraph("Movimento", e["cel_cab"]), Paragraph("Total", e["cel_cab_dir"])],
              [Paragraph("Aplicado", e["cel"]),
               Paragraph(formatar_reais(a["aplicado"]), e["cel_dir"])],
              [Paragraph("Resgatado", e["cel"]),
               Paragraph(formatar_reais(a["resgatado"]), e["cel_dir"])],
              [Paragraph("<b>Guardado no período (aplicado − resgatado)</b>", e["cel"]),
               Paragraph(f"<b>{formatar_reais(a['liquido'])}</b>", e["cel_dir"])],
              [Paragraph("Rendimentos recebidos", e["cel"]),
               Paragraph(formatar_reais(a["rendimentos"]), e["cel_dir"])]]
    h.append(_tabela(linhas, [LARGURA * .75, LARGURA * .25]))
    entradas = dados["entradas"]
    if a["liquido"] >= 0 and entradas and a["liquido"] / entradas > 0.8:
        txt = ("O valor guardado é maior do que quase tudo o que entrou: há aplicação e resgate "
               "automáticos (como o Rende Fácil) ou dinheiro vindo de outras contas no meio. "
               "Para saber quanto você realmente guarda, envie também o extrato da conta "
               "investimento e das outras contas.")
    elif a["liquido"] >= 0 and entradas:
        txt = (f"Você guardou {_pct(a['liquido'] / entradas * 100)} do que entrou. A "
               "referência comum é de 10% a 20%.")
    else:
        txt = (f"Saiu mais das aplicações do que entrou nelas: em {a['meses_resgatando']} de "
               f"{a['meses']} meses, os resgates passaram das aplicações. Se isso cobre gastos "
               "do dia a dia, é sinal de que o mês está fechando no vermelho.")
    h.append(Paragraph(txt + " Rendimento é receita do dinheiro aplicado, não salário.",
                       e["pequeno"]))
    return h


def _pagina2(dados, e):
    recuo = {0: 4, 1: 16, 2: 30}

    def nome(texto, nivel, estilo="cel"):
        st = ParagraphStyle(f"n{nivel}{estilo}", parent=e[estilo], leftIndent=recuo[nivel])
        return Paragraph(texto, st)

    h = [Paragraph("Para onde foi o dinheiro", e["titulo"]),
         Paragraph("As 5 maiores categorias de gasto, com as subcategorias e os maiores gastos "
                   "de cada uma. Na linha da categoria, o % é sobre todas as saídas; nas linhas "
                   "de baixo, a categoria é o 100%. A variação compara a média dos últimos 3 "
                   "meses com a dos meses anteriores.", e["pequeno"]), Spacer(1, 5)]
    linhas = [[Paragraph(x, e["cel_cab_dir"] if i in (1, 3) else e["cel_cab"])
               for i, x in enumerate(["Categoria", "Total", "%", "Variação"])]]
    estilo_extra, n = [], 1
    for b in dados["onde_foi"]:
        v = b["var"]
        var = "—" if v is None else (("+" if v > 0 else "") + _pct(v))
        linhas.append([nome(f"<b>{b['categoria'].capitalize()}</b>", 0),
                       Paragraph(f"<b>{formatar_reais(b['total'])}</b>", e["cel_dir"]),
                       _pct_celula(b["pct"], e, COR_SAIDAS),
                       Paragraph(var, e["cel_dir"])])
        estilo_extra += [("BACKGROUND", (0, n), (-1, n), OSSO),
                         ("LINEABOVE", (0, n), (-1, n), 0.6, LINHA)]
        n += 1
        for sb in b["subs"]:
            linhas.append([nome(sb["nome"], 1), Paragraph(formatar_reais(sb["total"]),
                                                          e["cel_dir"]),
                           _pct_celula(sb["pct"], e, COR_ENTRADAS), Paragraph("", e["cel"])])
            n += 1
        if b["maiores"]:
            linhas.append([nome("<i>Maiores gastos</i>", 1, "cel_cab"), Paragraph("", e["cel"]),
                           Paragraph("", e["cel"]), Paragraph("", e["cel"])])
            n += 1
            for f in b["maiores"]:
                vezes = f"{f['vezes']} vez" + ("es" if f["vezes"] > 1 else "")
                linhas.append([nome(f"{f['nome']} <font color='#5b6275'>· {vezes}</font>", 2),
                               Paragraph(formatar_reais(f["total"]), e["cel_dir"]),
                               _pct_celula(f["pct"], e, COR_TOTAL), Paragraph("", e["cel"])])
                n += 1
    if dados["demais"]:
        dm = dados["demais"]
        linhas.append([nome(f"<i>Demais categorias ({dm['n']})</i>", 0),
                       Paragraph(formatar_reais(dm["total"]), e["cel_dir"]),
                       _pct_celula(dm["pct"], e, COR_SAIDAS), Paragraph("", e["cel"])])
    tab = _tabela(linhas, [LARGURA * .44, LARGURA * .18, LARGURA * .26, LARGURA * .12],
                  zebra=False)
    tab.setStyle(TableStyle(estilo_extra + [("TOPPADDING", (0, 1), (-1, -1), 1.4),
                                            ("BOTTOMPADDING", (0, 1), (-1, -1), 1.4)]))
    h.append(tab)
    return h


def _minigrafico(valores, largura=110, altura=16, cor=COR_ENTRADAS):
    """Linha pequena (sparkline) com os valores mês a mês; meses sem valor ficam em branco."""
    from reportlab.graphics.shapes import Circle, PolyLine
    d = Drawing(largura, altura)
    pts = [(i, v) for i, v in enumerate(valores) if v is not None]
    if not pts:
        return d
    vmin, vmax = min(v for _, v in pts), max(v for _, v in pts)
    faixa = (vmax - vmin) or max(vmax, 1)
    passo = (largura - 6) / max(1, len(valores) - 1)

    def xy(i, v):
        return 3 + i * passo, 3 + (altura - 6) * ((v - vmin) / faixa if vmax != vmin else 0.5)

    trecho = []
    for i, v in enumerate(valores + [None]):
        if v is None:
            if len(trecho) > 1:
                d.add(PolyLine(trecho, strokeColor=cor, strokeWidth=1.2))
            trecho = []
        else:
            trecho += list(xy(i, v))
    x, y = xy(*pts[-1])
    d.add(Circle(x, y, 1.8, fillColor=cor, strokeColor=None))
    return d


MAX_RECORRENTES = 6   # as demais contas que se repetem viram uma linha só


def _tabela_recorrentes(dados, e):
    """Contas que se repetem: nome, minigráfico, último mês, média e próxima data."""
    hist = dados["hist_fixos"]
    rec = dados["recorrentes"].set_index("Fornecedor")
    meses = sorted(hist["Mês"].unique())
    por = hist.pivot_table(index="Fornecedor", columns="Mês", values="Valor", aggfunc="sum")
    por = por.reindex(columns=meses)
    ordem = por.mean(axis=1).sort_values(ascending=False).index
    cab = ["Conta", f"{rotulo_mes(meses[0])} a {rotulo_mes(meses[-1])}", "Último mês",
           "Média", "Próxima"]
    linhas = [[Paragraph(x, e["cel_cab_dir"] if i in (2, 3) else e["cel_cab"])
               for i, x in enumerate(cab)]]
    def lista(serie):
        return [None if pd.isna(v) else float(v) for v in serie]

    for nome in ordem[:MAX_RECORRENTES]:
        vals = lista(por.loc[nome])
        presentes = [v for v in vals if v is not None]
        tipo = rec.loc[nome, "Tipo"] if nome in rec.index else ""
        rotulo = f"{nome}<br/><font size=7 color='#5b6275'>" + (
            "valor fixo" if tipo == plus.FIXO else "valor varia") + "</font>"
        linhas.append([Paragraph(rotulo, e["cel"]), _minigrafico(vals),
                       Paragraph(formatar_reais(presentes[-1]), e["cel_dir"]),
                       Paragraph(formatar_reais(sum(presentes) / len(presentes)), e["cel_dir"]),
                       Paragraph(rec.loc[nome, "Próxima prevista"] if nome in rec.index else "",
                                 e["cel"])])
    resto = ordem[MAX_RECORRENTES:]
    if len(resto):
        vals = lista(por.loc[resto].sum(axis=0, min_count=1))
        presentes = [v for v in vals if v is not None]
        linhas.append([Paragraph(f"<i>Outras contas ({len(resto)})</i>", e["cel"]),
                       _minigrafico(vals), Paragraph(formatar_reais(presentes[-1]), e["cel_dir"]),
                       Paragraph(formatar_reais(sum(presentes) / len(presentes)), e["cel_dir"]),
                       Paragraph("", e["cel"])])
    total = por.sum(axis=1, min_count=1)
    total_mes = lista(por.sum(axis=0, min_count=1))
    linhas.append([Paragraph("<b>Total por mês</b>", e["cel"]),
                   _minigrafico(total_mes, cor=COR_TOTAL),
                   Paragraph(f"<b>{formatar_reais(total_mes[-1] or 0)}</b>", e["cel_dir"]),
                   Paragraph(f"<b>{formatar_reais(total.sum() / len(meses))}</b>", e["cel_dir"]),
                   Paragraph("", e["cel"])])
    tab = _tabela(linhas, [LARGURA * .36, LARGURA * .24, LARGURA * .14, LARGURA * .13,
                           LARGURA * .13])
    tab.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, DOURADO)]))
    return tab


def _pct_celula(pct, e, cor):
    return Table([[_barra_pct(pct, 56, cor), Paragraph(_pct(pct, 1), e["cel"])]],
                 colWidths=[60, 40], style=[("LEFTPADDING", (0, 0), (-1, -1), 0),
                                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)])


def _pagina_compromissos(dados, e):
    h = [Paragraph("O que já está comprometido", e["titulo"])]
    comp = dados["comprometido"]
    meses = [c["Mês"] for c in comp]
    h += [Paragraph("Nos próximos 3 meses", e["sub"]),
          Paragraph("Contas que se repetem todo mês (valor fixo e contas mensais) e parcelas "
                    "do cartão já contratadas.", e["pequeno"]),
          _grafico_linhas([
              ("Total", COR_TOTAL, {c["Mês"]: c["Contas fixas"] + c["Parcelas"] for c in comp},
               True),
              ("Contas fixas", CORES_SERIES[0], {c["Mês"]: c["Contas fixas"] for c in comp}),
              ("Parcelas", CORES_SERIES[1], {c["Mês"]: c["Parcelas"] for c in comp})],
              meses, altura=150, largura_nomes=90)]
    hist = dados["hist_fixos"]
    if not hist.empty:
        h += [Paragraph("Contas que se repetem", e["sub"]),
              Paragraph("Uma linha por conta: o minigráfico mostra como o valor variou mês a "
                        "mês, do primeiro ao último mês dos extratos.", e["pequeno"]),
              Spacer(1, 4), _tabela_recorrentes(dados, e)]
    par = dados["serie_parcelas"]
    if not par.empty:
        total = par.groupby("Mês")["Valor"].sum().to_dict()
        meses = sorted(total)
        h += [Paragraph("Parcelas do cartão", e["sub"]),
              Paragraph("Quanto das parcelas já contratadas vai sair em cada mês, até a última.",
                        e["pequeno"]),
              _grafico_linhas([("Total das parcelas", COR_SAIDAS, total)], meses, altura=105,
                              largura_nomes=100),
              Spacer(1, 4)]
        linhas = [[Paragraph(x, e["cel_cab_dir"] if i in (1, 3) else e["cel_cab"])
                   for i, x in enumerate(["Compra", "Parcela", "Faltam", "Ainda a pagar",
                                          "Termina"])]]
        p_ = dados["parcelas"]
        for _, p in p_.head(6).iterrows():
            linhas.append([Paragraph(p["Fornecedor"], e["cel"]),
                           Paragraph(formatar_reais(p["Valor da parcela"]), e["cel_dir"]),
                           Paragraph(f"{p['Restam']} de {p['Parcelas']}", e["cel"]),
                           Paragraph(formatar_reais(p["Total restante"]), e["cel_dir"]),
                           Paragraph(rotulo_mes(p["Última parcela"]), e["cel"])])
        if len(p_) > 6:
            resto = p_.iloc[6:]
            linhas.append([Paragraph(f"<i>Outras ({len(resto)})</i>", e["cel"]),
                           Paragraph(formatar_reais(resto["Valor da parcela"].sum()),
                                     e["cel_dir"]), Paragraph("", e["cel"]),
                           Paragraph(formatar_reais(resto["Total restante"].sum()), e["cel_dir"]),
                           Paragraph(rotulo_mes(resto["Última parcela"].max()), e["cel"])])
        linhas.append([Paragraph("<b>Total</b>", e["cel"]),
                       Paragraph(f"<b>{formatar_reais(p_['Valor da parcela'].sum())}</b>",
                                 e["cel_dir"]), Paragraph("", e["cel"]),
                       Paragraph(f"<b>{formatar_reais(p_['Total restante'].sum())}</b>",
                                 e["cel_dir"]),
                       Paragraph(rotulo_mes(p_["Última parcela"].max()), e["cel"])])
        tab = _tabela(linhas, [LARGURA * .36, LARGURA * .16, LARGURA * .14, LARGURA * .18,
                               LARGURA * .16])
        tab.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, DOURADO)]))
        h.append(tab)
    return h


def _pagina_atencao(dados, e):
    h = [Paragraph("Pontos de atenção", e["titulo"])]
    linhas = []
    for i in dados["indicadores"]:
        cor, rotulo = SINAL[i["status"]]
        selo = Drawing(58, 14)
        selo.add(Rect(0, 1, 56, 12, rx=6, ry=6, fillColor=cor, strokeColor=None))
        selo.add(String(28, 4.2, rotulo, fontName="Helvetica-Bold", fontSize=7.5,
                        fillColor=colors.white, textAnchor="middle"))
        linhas.append([selo, Paragraph(f"<b>{i['nome']}</b>: {i['valor']}", e["cel"]),
                       Paragraph(i["explicacao"], e["pequeno"])])
    h.append(_tabela(linhas, [LARGURA * .13, LARGURA * .32, LARGURA * .55], cabecalho=False))

    ir = dados["ir"]
    if ir is not None:
        ano = dados["ano_ir"]
        meses_ano = sorted(m for m in dados["mensal"]["Mês"] if m.startswith(str(ano)))
        parcial = (f", {MESES[int(meses_ano[0][5:]) - 1]} a {MESES[int(meses_ano[-1][5:]) - 1]}"
                   if meses_ano and len(meses_ano) < 12 else "")
        h.append(Paragraph(f"Imposto de Renda {ano}{parcial} (prévia para a declaração de "
                           f"{ano + 1})", e["sub"]))
        linhas = [[Paragraph("Possíveis deduções", e["cel_cab"]),
                   Paragraph("Total", e["cel_cab_dir"])]]
        dedu = ir["deducoes"]
        for grupo, total in dedu.groupby("Grupo")["Total"].sum().items():
            linhas.append([Paragraph(grupo, e["cel"]),
                           Paragraph(formatar_reais(total), e["cel_dir"])])
        if dedu.empty:
            linhas.append([Paragraph("Nenhuma encontrada", e["cel"]), Paragraph("", e["cel"])])
        linhas.append([Paragraph("Rendimentos", e["cel_cab"]), Paragraph("", e["cel"])])
        linhas.append([Paragraph("Recebidos de empresas", e["cel"]),
                       Paragraph(formatar_reais(ir["rendimentos_pj"]["Total"].sum()),
                                 e["cel_dir"])])
        linhas.append([Paragraph("Recebidos de pessoas (pode exigir Carnê-Leão)", e["cel"]),
                       Paragraph(formatar_reais(ir["rendimentos_pf"]["Total"].sum()),
                                 e["cel_dir"])])
        tab = _tabela(linhas, [LARGURA * .75, LARGURA * .25])
        sep = len(linhas) - 3   # linha "Rendimentos": vira um subtítulo da tabela
        tab.setStyle(TableStyle([("LINEBELOW", (0, sep), (-1, sep), 0.8, DOURADO),
                                 ("BACKGROUND", (0, sep), (-1, sep), colors.white),
                                 ("TOPPADDING", (0, sep), (-1, sep), 8)]))
        h.append(tab)
        h.append(Paragraph("Só se deduz o que tem comprovação (nota fiscal ou recibo com "
                           "CPF/CNPJ). O detalhe por fornecedor, com CNPJ, está na planilha do "
                           "IR do app.", e["pequeno"]))

    if dados["sugestoes"]:
        h.append(Spacer(1, 10))
        h.append(Paragraph("Próximos passos sugeridos", e["sub"]))
        passo = ParagraphStyle("passo", parent=e["item"], leftIndent=26, bulletIndent=12,
                               spaceAfter=5)
        h += [Paragraph(s, passo, bulletText=f"{n}.")
              for n, s in enumerate(dados["sugestoes"], start=1)]

    contas = ", ".join(dados["contas"])
    transp = [
        f"<b>Contas incluídas:</b> {contas}.",
        f"<b>Período:</b> {dados['inicio']:%d/%m/%Y} a {dados['fim']:%d/%m/%Y}, "
        f"{dados['transacoes']} lançamentos.",
        "<b>Fora das contas:</b> aplicações e resgates automáticos, transferências entre suas "
        "contas e pagamento de fatura (o dinheiro só mudou de lugar).",
        f"<b>Não identificados:</b> {_pct(dados['pct_nao_id'], 1)} das saídas ficaram sem "
        "categoria reconhecida.",
        f"<b>Limites:</b> {dados['limites']} As referências dos indicadores são de educação "
        "financeira, não regras.",
    ]
    if dados["melhorias"]:
        melhorar = ParagraphStyle("melhorar", parent=e["pequeno"], leftIndent=10,
                                  bulletIndent=0, spaceAfter=2)
        h.append(KeepTogether([Paragraph("Para melhorar este relatório", e["sub"])]
                              + [Paragraph(m, melhorar, bulletText="•")
                                 for m in dados["melhorias"]]))
    bloco = [Paragraph("Como este relatório foi feito", e["sub"])]
    bloco += [Paragraph(x, e["pequeno"]) for x in transp]
    h.append(KeepTogether(bloco))

    cta = Table([[Paragraph("<b>Quer ajuda para colocar isso em prática?</b> Um especialista "
                            "financeiro/contábil revisa este relatório com você e monta um "
                            "plano. Fale pelo botão no app Contas em Dia.", e["texto"])]],
                colWidths=[LARGURA])
    cta.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), OSSO_2),
                             ("LINEBEFORE", (0, 0), (0, 0), 3, DOURADO),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10),
                             ("TOPPADDING", (0, 0), (-1, -1), 8),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    h += [Spacer(1, 10), cta]
    return h


def gerar_pdf(dados):
    """PDF do relatório (bytes)."""
    saida = io.BytesIO()
    doc = SimpleDocTemplate(saida, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=29 * mm, bottomMargin=16 * mm,
                            title="Relatório Contas em Dia", author="Contas em Dia")
    e = _estilos()
    historia = (_pagina1(dados, e) + [PageBreak()] + _pagina2(dados, e) + [PageBreak()]
                + _pagina_compromissos(dados, e) + [PageBreak()] + _pagina_atencao(dados, e))
    desenhar = _cabecalho_rodape(dados)
    doc.build(historia, onFirstPage=desenhar, onLaterPages=desenhar)
    return saida.getvalue()
