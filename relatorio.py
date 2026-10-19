"""
Relatório Contas em Dia (área Plus): um PDF de 3 páginas, em linguagem simples.

1. Seu dinheiro em uma página: nota geral, números do período, destaques e o mês a mês
2. Para onde foi e o que já está comprometido: categorias, fornecedores, fixos e parcelas
3. Atenção, imposto e próximos passos: indicadores, prévia do IR, sugestões e como o
   relatório foi feito

montar_relatorio() calcula o conteúdo (testável, sem PDF); gerar_pdf() desenha.
Nada é guardado: o PDF é gerado na memória e entregue para download.
"""

import io
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
from financeiro import (chave_fornecedor, formatar_reais, nao_identificado, resumo_categorias,
                        resumo_mensal)

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


def _destaques(t, mensal, entradas, saidas, variacao):
    frases = []
    if entradas > 0:
        sobra = entradas - saidas
        if sobra >= 0:
            frases.append(f"Você guardou <b>{_pct(sobra / entradas * 100)}</b> do que entrou: "
                          f"{formatar_reais(sobra)} no período.")
        else:
            frases.append(f"Você gastou <b>{formatar_reais(-sobra)} a mais</b> do que recebeu "
                          "no período.")
    if len(mensal) > 1:
        caro = mensal.loc[mensal["Saídas"].idxmax()]
        s = t[(t["Tipo"] == "Saída") & (t["Mês"] == caro["Mês"])]
        puxou = s.groupby("Categoria")["Valor"].sum().idxmin() if not s.empty else ""
        frases.append(f"Seu mês mais caro foi <b>{rotulo_mes(caro['Mês'])}</b>: "
                      f"{formatar_reais(caro['Saídas'])}, puxado por {puxou.capitalize()}.")
    if variacao and abs(variacao["variacao"]) >= 10:
        verbo = "subiu" if variacao["variacao"] > 0 else "caiu"
        frases.append(f"<b>{variacao['categoria'].capitalize()}</b> {verbo} "
                      f"{_pct(abs(variacao['variacao']))} nos últimos 3 meses: de "
                      f"{formatar_reais(variacao['antes'])} para "
                      f"{formatar_reais(variacao['agora'])} por mês.")
    return frases[:3]


def _sugestoes(itens, cats, parcelas, saidas_mes, pct_nao_id, guardado):
    """Até 3 sugestões práticas, das mais importantes para as menos."""
    status = {i["nome"]: i for i in itens}
    sug = []
    sobra = status.get("Quanto sobra das entradas")
    # Teto só faz sentido para gasto do dia a dia (aluguel e escola não se cortam assim)
    variaveis = cats[cats["Categoria"].isin(CATEGORIAS_VARIAVEIS)]
    if sobra and sobra["status"] != plus.BOM and not variaveis.empty:
        maior = variaveis.iloc[0]
        meses = max(1, saidas_mes["n"])
        corte = maior["Total"] / meses * 0.10
        sug.append(f"<b>Defina um teto mensal para {maior['Categoria'].capitalize()}</b>, seu "
                   f"maior gasto do dia a dia ({formatar_reais(maior['Total'] / meses)} por "
                   f"mês). Cortar 10% libera cerca de {formatar_reais(corte)} por mês.")
    if guardado is None or status.get("Reserva de emergência", {}).get("status") != plus.BOM:
        sug.append(f"<b>Monte uma reserva de emergência</b> de 3 a 6 meses de gastos: entre "
                   f"{formatar_reais(saidas_mes['media'] * 3)} e "
                   f"{formatar_reais(saidas_mes['media'] * 6)}. Comece com um valor fixo "
                   "todo mês, logo que o dinheiro entrar.")
    dep = status.get("Dependência da maior fonte")
    if dep and dep["status"] == plus.ALERTA:
        sug.append(f"<b>Diversifique suas fontes de renda</b>: {dep['valor']} das entradas "
                   "vêm de uma única fonte.")
    if not parcelas.empty:
        fim = rotulo_mes(parcelas["Última parcela"].max())
        sug.append(f"<b>Evite novas compras parceladas</b> até {fim}, quando terminam as "
                   f"atuais ({formatar_reais(parcelas['Total restante'].sum())} ainda a pagar).")
    if pct_nao_id > 10:
        sug.append(f"<b>Classifique os gastos não identificados</b> ({_pct(pct_nao_id)} das "
                   "saídas) para o relatório ficar mais preciso.")
    return sug[:3]


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
    # Variação de cada categoria: últimos 3 meses × média anterior
    meses = sorted(s["Mês"].unique())
    var_cat = {}
    if len(meses) >= 5:
        pv = s.assign(V=-s["Valor"]).pivot_table(index="Categoria", columns="Mês", values="V",
                                                 aggfunc="sum", fill_value=0)
        rec, ant = pv[meses[-3:]].mean(axis=1), pv[meses[:-3]].mean(axis=1)
        var_cat = {c: (rec[c] - ant[c]) / ant[c] * 100 for c in pv.index if ant[c] >= 100}

    fornecedores = (s.assign(_k=s["Fornecedor"].map(chave_fornecedor), V=-s["Valor"])
                    .groupby("_k").agg(Fornecedor=("Fornecedor", "first"), Total=("V", "sum"),
                                       Vezes=("V", "count"), Categoria=("Categoria", "first"))
                    .sort_values("Total", ascending=False).head(5).reset_index(drop=True))

    # Já comprometido nos próximos 3 meses: contas que se repetem + parcelas do cartão
    ultimo = pd.Period(t["Data"].max(), freq="M")
    proximos = [str(ultimo + i) for i in (1, 2, 3)]
    crono = dict(zip(cronograma["Mês"], cronograma["Valor"])) if not cronograma.empty else {}
    comprometido = [{"Mês": m, "Contas fixas": compromissos, "Parcelas": crono.get(m, 0.0)}
                    for m in proximos]

    anos = sorted(t["Data"].dt.year.unique())
    ir = plus.relatorio_ir(t, anos[-1]) if anos else None

    return {
        "gerado_em": hoje, "inicio": t["Data"].min(), "fim": t["Data"].max(),
        "contas": sorted(t["Conta"].unique()), "transacoes": len(mov),
        "entradas": entradas, "saidas": saidas, "sobra": entradas - saidas,
        "media_entradas": entradas / n_meses, "media_saidas": saidas / n_meses,
        "n_meses": n_meses, "mensal": mensal, "categorias": cats, "var_cat": var_cat,
        "fornecedores": fornecedores, "recorrentes": recorrentes, "compromissos": compromissos,
        "parcelas": parcelas, "comprometido": comprometido, "indicadores": itens,
        "nota": nota, "contagem": contagem, "pct_nao_id": pct_nao_id, "guardado": guardado,
        "ano_ir": anos[-1] if anos else None, "ir": ir,
        "destaques": _destaques(t, mensal, entradas, saidas, variacao),
        "sugestoes": _sugestoes(itens, cats, parcelas,
                                {"n": n_meses, "media": saidas / n_meses}, pct_nao_id, guardado),
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
               f"{c[plus.ALERTA]} em alerta. Detalhes na página 3.")
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


def _grafico_mensal(mensal):
    altura = 150
    d = Drawing(LARGURA, altura + 22)
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 42, 18, LARGURA - 50, altura - 20
    g.data = [list(mensal["Entradas"]), list(mensal["Saídas"])]
    g.categoryAxis.categoryNames = [rotulo_mes(m) for m in mensal["Mês"]]
    g.categoryAxis.labels.fontSize = 7
    g.categoryAxis.labels.fontName = "Helvetica"
    g.valueAxis.labels.fontName = "Helvetica"
    g.categoryAxis.labels.fillColor = CINZA
    g.categoryAxis.strokeColor = LINHA
    g.valueAxis.valueMin = 0
    g.valueAxis.labels.fontSize = 7
    g.valueAxis.labels.fillColor = CINZA
    g.valueAxis.labelTextFormat = lambda v: f"{v:,.0f}".replace(",", ".")
    g.valueAxis.strokeColor = None
    g.valueAxis.visibleGrid = True
    g.valueAxis.gridStrokeColor = colors.HexColor("#ebe6da")
    g.bars[0].fillColor = COR_ENTRADAS
    g.bars[1].fillColor = COR_SAIDAS
    g.bars.strokeColor = None
    g.barSpacing = 1.5
    g.groupSpacing = 7
    d.add(g)
    # Legenda (cor + nome)
    for i, (nome, cor) in enumerate([("Entradas", COR_ENTRADAS), ("Saídas", COR_SAIDAS)]):
        x = 44 + i * 80
        d.add(Rect(x, altura + 8, 9, 9, fillColor=cor, strokeColor=None))
        d.add(String(x + 13, altura + 9, nome, fontName="Helvetica", fontSize=8,
                     fillColor=MARINHO))
    return d


def _barra_pct(pct, largura=60, cor=COR_SAIDAS):
    d = Drawing(largura, 8)
    d.add(Rect(0, 1, largura, 5, fillColor=colors.HexColor("#ebe6da"), strokeColor=None))
    d.add(Rect(0, 1, largura * min(1, max(0, pct / 100)), 5, fillColor=cor, strokeColor=None))
    return d


def _pagina1(dados, e):
    h = [Paragraph("Seu dinheiro em uma página", e["titulo"]), _nota_geral(dados, e),
         Spacer(1, 8), _cartoes_kpi(dados, e), Spacer(1, 4),
         Paragraph(f"Média por mês: entrou {formatar_reais(dados['media_entradas'])} e saiu "
                   f"{formatar_reais(dados['media_saidas'])}, em {dados['n_meses']} mês(es).",
                   e["pequeno"]),
         Paragraph("Destaques", e["sub"])]
    h += [Paragraph(f, e["item"], bulletText="•") for f in dados["destaques"]]
    h += [Paragraph("Entradas e saídas mês a mês", e["sub"]), _grafico_mensal(dados["mensal"])]
    linhas = [[Paragraph(x, e["cel_cab_dir"] if i else e["cel_cab"])
               for i, x in enumerate(["Mês", "Entrou", "Saiu", "Saldo"])]]
    for _, m in dados["mensal"].iterrows():
        cor = SINAL[plus.BOM][0] if m["Saldo"] >= 0 else SINAL[plus.ALERTA][0]
        linhas.append([Paragraph(rotulo_mes(m["Mês"]), e["cel"]),
                       Paragraph(formatar_reais(m["Entradas"]), e["cel_dir"]),
                       Paragraph(formatar_reais(m["Saídas"]), e["cel_dir"]),
                       Paragraph(f'<font color="{cor.hexval()}">{formatar_reais(m["Saldo"])}'
                                 "</font>", e["cel_dir"])])
    h.append(_tabela(linhas, [LARGURA * .22] + [LARGURA * .26] * 3))
    return h


def _pagina2(dados, e):
    h = [Paragraph("Para onde foi o dinheiro", e["titulo"]),
         Paragraph("As 5 maiores categorias de gasto. A variação compara a média dos últimos "
                   "3 meses com a dos meses anteriores.", e["pequeno"]), Spacer(1, 4)]
    cats = dados["categorias"]
    linhas = [[Paragraph(x, e["cel_cab_dir"] if i in (1, 3) else e["cel_cab"])
               for i, x in enumerate(["Categoria", "Total", "% das saídas", "Variação"])]]
    for _, c in cats.head(5).iterrows():
        v = dados["var_cat"].get(c["Categoria"])
        var = "—" if v is None else (("+" if v > 0 else "") + _pct(v))
        linhas.append([Paragraph(c["Categoria"].capitalize(), e["cel"]),
                       Paragraph(formatar_reais(c["Total"]), e["cel_dir"]),
                       Table([[_barra_pct(c["% das saídas"]),
                               Paragraph(_pct(c["% das saídas"], 1), e["cel"])]],
                             colWidths=[64, 40], style=[("LEFTPADDING", (0, 0), (-1, -1), 0)]),
                       Paragraph(var, e["cel_dir"])])
    resto = cats.iloc[5:]
    if not resto.empty:
        linhas.append([Paragraph(f"<i>Demais ({len(resto)})</i>", e["cel"]),
                       Paragraph(formatar_reais(resto["Total"].sum()), e["cel_dir"]),
                       Paragraph(_pct(resto["% das saídas"].sum(), 1), e["cel"]),
                       Paragraph("", e["cel"])])
    h.append(_tabela(linhas, [LARGURA * .34, LARGURA * .2, LARGURA * .3, LARGURA * .16]))

    h.append(Paragraph("Quem mais recebeu", e["sub"]))
    linhas = [[Paragraph(x, e["cel_cab_dir"] if i >= 2 else e["cel_cab"])
               for i, x in enumerate(["Fornecedor", "Categoria", "Vezes", "Total"])]]
    for _, f in dados["fornecedores"].iterrows():
        linhas.append([Paragraph(f["Fornecedor"], e["cel"]),
                       Paragraph(f["Categoria"].capitalize(), e["cel"]),
                       Paragraph(str(f["Vezes"]), e["cel_dir"]),
                       Paragraph(formatar_reais(f["Total"]), e["cel_dir"])])
    h.append(_tabela(linhas, [LARGURA * .42, LARGURA * .26, LARGURA * .12, LARGURA * .2]))

    h.append(Paragraph("Já comprometido nos próximos 3 meses", e["sub"]))
    h.append(Paragraph("Contas que se repetem todo mês (valor fixo e contas mensais) e parcelas "
                       "do cartão que já estão contratadas.", e["pequeno"]))
    h.append(Spacer(1, 4))
    linhas = [[Paragraph(x, e["cel_cab_dir"] if i else e["cel_cab"])
               for i, x in enumerate(["Mês", "Contas fixas", "Parcelas", "Total"])]]
    for c in dados["comprometido"]:
        linhas.append([Paragraph(rotulo_mes(c["Mês"]), e["cel"]),
                       Paragraph(formatar_reais(c["Contas fixas"]), e["cel_dir"]),
                       Paragraph(formatar_reais(c["Parcelas"]), e["cel_dir"]),
                       Paragraph(f"<b>{formatar_reais(c['Contas fixas'] + c['Parcelas'])}</b>",
                                 e["cel_dir"])])
    h.append(_tabela(linhas, [LARGURA * .22] + [LARGURA * .26] * 3))

    rec = dados["recorrentes"]
    fixos = rec[(rec["Situação"] == "Ativo") & rec["Tipo"].isin([plus.FIXO, plus.CONTA_MENSAL])]
    if not fixos.empty:
        h.append(Paragraph("Contas que se repetem", e["sub"]))
        linhas = [[Paragraph(x, e["cel_cab_dir"] if i == 2 else e["cel_cab"])
                   for i, x in enumerate(["Conta", "Tipo", "Por mês", "Próxima"])]]
        for _, r in fixos.head(6).iterrows():
            linhas.append([Paragraph(r["Fornecedor"], e["cel"]),
                           Paragraph("Valor fixo" if r["Tipo"] == plus.FIXO else "Valor varia",
                                     e["cel"]),
                           Paragraph(formatar_reais(r["Por mês"]), e["cel_dir"]),
                           Paragraph(r["Próxima prevista"], e["cel"])])
        h.append(_tabela(linhas, [LARGURA * .42, LARGURA * .2, LARGURA * .18, LARGURA * .2]))

    par = dados["parcelas"]
    if not par.empty:
        h.append(Paragraph("Parcelas do cartão", e["sub"]))
        linhas = [[Paragraph(x, e["cel_cab_dir"] if i in (1, 3) else e["cel_cab"])
                   for i, x in enumerate(["Compra", "Parcela", "Faltam", "Ainda a pagar",
                                          "Termina"])]]
        for _, p in par.head(4).iterrows():
            linhas.append([Paragraph(p["Fornecedor"], e["cel"]),
                           Paragraph(formatar_reais(p["Valor da parcela"]), e["cel_dir"]),
                           Paragraph(f"{p['Restam']} de {p['Parcelas']}", e["cel"]),
                           Paragraph(formatar_reais(p["Total restante"]), e["cel_dir"]),
                           Paragraph(rotulo_mes(p["Última parcela"]), e["cel"])])
        h.append(_tabela(linhas, [LARGURA * .36, LARGURA * .16, LARGURA * .14, LARGURA * .18,
                                  LARGURA * .16]))
    return h


def _pagina3(dados, e):
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
        h.append(Paragraph("Próximos passos sugeridos", e["sub"]))
        h += [Paragraph(s, e["item"], bulletText=f"{n}.")
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
        "<b>Limites:</b> o relatório só enxerga o que está nos extratos enviados. Parcelas vêm "
        "da fatura do cartão em PDF. As referências dos indicadores são de educação "
        "financeira, não regras.",
    ]
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
                + _pagina3(dados, e))
    desenhar = _cabecalho_rodape(dados)
    doc.build(historia, onFirstPage=desenhar, onLaterPages=desenhar)
    return saida.getvalue()
