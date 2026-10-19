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


def _nome_grupo(categoria, subcategoria):
    """Subcategoria quando ela diz algo; senão a categoria ("Viagens", "Educação")."""
    if subcategoria and subcategoria not in ("Outros", "Não identificados"):
        return subcategoria
    return categoria.capitalize()


def _destaques(t, mensal, variacao, comprometido_mes, media_saidas):
    """Até 3 frases sobre os gastos (o que saiu é sempre gasto; o que entrou pode ser
    renda, transferência ou reembolso, por isso as frases não falam de renda)."""
    s = t[t["Tipo"] == "Saída"].assign(V=lambda d: -d["Valor"])
    frases = []
    if len(mensal) > 1:
        caro = mensal.loc[mensal["Saídas"].idxmax()]
        acima = caro["Saídas"] - media_saidas
        # O que mais passou da própria média naquele mês
        grupos = s.groupby(["Categoria", "Subcategoria", "Mês"])["V"].sum().unstack(fill_value=0)
        if caro["Mês"] in grupos:
            excesso = grupos[caro["Mês"]] - grupos.mean(axis=1)
            cat, sub = excesso.idxmax()
            pesou = (f" O que mais pesou: {_nome_grupo(cat, sub)} "
                     f"({formatar_reais(grupos.loc[(cat, sub), caro['Mês']])}).")
        else:
            pesou = ""
        frases.append(f"Seu mês mais caro foi <b>{rotulo_mes(caro['Mês'])}</b>: "
                      f"{formatar_reais(caro['Saídas'])}, {formatar_reais(acima)} acima da sua "
                      f"média mensal.{pesou}")
    if variacao and abs(variacao["variacao"]) >= 10:
        verbo = "subiu" if variacao["variacao"] > 0 else "caiu"
        cat = variacao["categoria"]
        meses = sorted(s["Mês"].unique())
        sc = s[s["Categoria"] == cat]
        por_sub = sc.groupby(["Subcategoria", "Mês"])["V"].sum().unstack(fill_value=0)
        puxada = ""
        if len(por_sub) > 1 or (len(por_sub) == 1 and por_sub.index[0]):
            dif = (por_sub.reindex(columns=meses, fill_value=0)[meses[-3:]].mean(axis=1)
                   - por_sub.reindex(columns=meses, fill_value=0)[meses[:-3]].mean(axis=1))
            sub = dif.idxmax() if verbo == "subiu" else dif.idxmin()
            if sub:
                puxada = f", principalmente em {sub}"
        frases.append(f"<b>{cat.capitalize()}</b> {verbo} {_pct(abs(variacao['variacao']))} nos "
                      f"últimos 3 meses: de {formatar_reais(variacao['antes'])} para "
                      f"{formatar_reais(variacao['agora'])} por mês{puxada}.")
    if comprometido_mes and media_saidas:
        frases.append(f"Contas fixas e parcelas já somam <b>{formatar_reais(comprometido_mes)} "
                      f"por mês</b>: {_pct(comprometido_mes / media_saidas * 100)} do que você "
                      "gasta em média. É o valor que sai antes de qualquer escolha.")
    if len(frases) < 3 and not s.empty:
        maior = s.loc[s["V"].idxmax()]
        frases.append(f"Seu maior gasto único foi <b>{formatar_reais(maior['V'])}</b> em "
                      f"{maior['Fornecedor']} ({maior['Data']:%d/%m/%Y}).")
    return frases[:3]


def _onde_foi(t, cats, var_cat, n_categorias=5, n_subs=4, n_maiores=3):
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
        "destaques": _destaques(t, mensal, variacao, compromissos + parcela_prox,
                                saidas / n_meses),
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
               f"{c[plus.ALERTA]} em alerta. Detalhes na página 4.")
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

    # Valor em cada ponto: o da linha mais baixa vai embaixo do ponto, os outros em cima,
    # afastados para não se sobreporem
    for m, rot in rotulos_ponto.items():
        if not rot:
            continue
        baixo = min(rot, key=lambda k: rot[k][0]) if len(rot) > 1 else None
        if baixo is not None:
            d.add(String(xs[m], max(base + 1, rot[baixo][0] - 10), _compacto(rot[baixo][1]),
                         fontName="Helvetica", fontSize=6, fillColor=MARINHO,
                         textAnchor="middle"))
        pos = _afastar({k: v[0] + 5 for k, v in rot.items() if k != baixo}, 8, base + 2,
                       altura - 4)
        for k, yy in pos.items():
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


def _pagina1(dados, e):
    h = [Paragraph("Seu dinheiro em uma página", e["titulo"]), _nota_geral(dados, e),
         Spacer(1, 8), _cartoes_kpi(dados, e), Spacer(1, 4),
         Paragraph(f"Média por mês: entrou {formatar_reais(dados['media_entradas'])} e saiu "
                   f"{formatar_reais(dados['media_saidas'])}, em {dados['n_meses']} mês(es). "
                   "O que entrou inclui tudo o que chegou às contas (salário, pagamentos, "
                   "transferências de outras pessoas e reembolsos).", e["pequeno"]),
         Paragraph("Destaques", e["sub"])]
    h += [Paragraph(f, e["item"], bulletText="•") for f in dados["destaques"]]
    mensal = dados["mensal"]
    h += [Paragraph("Entrou e saiu, mês a mês", e["sub"]),
          _grafico_linhas([("Entrou", COR_ENTRADAS, dict(zip(mensal["Mês"], mensal["Entradas"]))),
                           ("Saiu", COR_SAIDAS, dict(zip(mensal["Mês"], mensal["Saídas"])))],
                          list(mensal["Mês"]), altura=300, largura_nomes=60)]
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
    tab.setStyle(TableStyle(estilo_extra + [("TOPPADDING", (0, 1), (-1, -1), 2),
                                            ("BOTTOMPADDING", (0, 1), (-1, -1), 2)]))
    h.append(tab)
    return h


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
        series, meses = _series_de(hist, nome_total="Total por mês")
        h += [Paragraph("Contas que se repetem", e["sub"]),
              Paragraph("Quanto cada conta custou em cada mês. No fim da linha, o valor do "
                        "último mês.", e["pequeno"]),
              _grafico_linhas(series, meses, altura=190, valores="fim", largura_nomes=150)]
    par = dados["serie_parcelas"]
    if not par.empty:
        series, meses = _series_de(par, nome_total="Total das parcelas")
        fim = {p["Fornecedor"]: p for _, p in dados["parcelas"].iterrows()}
        h += [Paragraph("Parcelas do cartão", e["sub"]),
              Paragraph("Quanto ainda vai sair em cada mês até a última parcela: " + "; ".join(
                  f"{n} ({fim[n]['Restam']} de {fim[n]['Parcelas']} restantes, "
                  f"{formatar_reais(fim[n]['Total restante'])})"
                  for n, *_ in series[1:] if n in fim) + ".", e["pequeno"]),
              _grafico_linhas(series, meses, altura=150, largura_nomes=110)]
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
                + _pagina_compromissos(dados, e) + [PageBreak()] + _pagina_atencao(dados, e))
    desenhar = _cabecalho_rodape(dados)
    doc.build(historia, onFirstPage=desenhar, onLaterPages=desenhar)
    return saida.getvalue()
