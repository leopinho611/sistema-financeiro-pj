"""
Medição de uso, anônima: o que cada visita fez no app, para achar onde as pessoas travam.

Cada visita recebe um código aleatório (não ligado a nome, e-mail ou IP) e o app anota
eventos como "entrou", "arquivo" (formato, banco, lido ou erro), "pagina", "exportou" e
"ativo" (a página continua aberta). Nunca entram valores, descrições, nomes de fornecedor,
nome do titular ou nome de arquivo.

Os eventos vão para uma tabela no Supabase (segredos SUPABASE_URL e SUPABASE_CHAVE); sem
eles, ficam só na memória do servidor até ele reiniciar. O envio é em segundo plano: se o
Supabase estiver fora do ar, o app segue normalmente.
"""

import json
import re
import secrets
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd

from financeiro import normalizar

TABELA = "eventos"
INTERVALO_ATIVO = 30          # segundos entre os avisos de "página aberta"
LIMITE_ATIVO = 120            # depois de 2 horas aberta, para de avisar
# Eventos que não são ação da pessoa: não contam como "onde parou"
PASSIVOS = {"ativo"}

# O app recarrega este módulo a cada atualização (importlib.reload); a memória e o envio
# em segundo plano sobrevivem ao recarregamento
_MEMORIA = globals().get("_MEMORIA") or deque(maxlen=50_000)
_ENVIO = globals().get("_ENVIO") or ThreadPoolExecutor(max_workers=2,
                                                       thread_name_prefix="uso")


def novo_codigo():
    return secrets.token_hex(6)


def agora():
    return datetime.now(timezone.utc)


# ============================================================================
# O QUE PODE SER ANOTADO (nada que identifique a pessoa ou o dinheiro dela)
# ============================================================================
BANCOS = [  # (palavra no nome da conta, nome anotado)
    ("nubank", "Nubank"), ("nu_", "Nubank"), ("itau", "Itaú"), ("sispag", "Itaú"),
    ("bradesco", "Bradesco"), ("santander", "Santander"), ("caixa", "Caixa"),
    ("sicoob", "Sicoob"), ("sicredi", "Sicredi"), ("bnb", "BNB"), ("nordeste", "BNB"),
    ("inter", "Inter"), ("c6", "C6"), ("xp", "XP"), ("btg", "BTG"), ("mercado pago", "Mercado Pago"),
    ("picpay", "PicPay"), ("pagbank", "PagBank"), ("pagseguro", "PagBank"),
    ("banco do brasil", "BB"), ("bb", "BB"),
]


def banco_da_conta(conta):
    """Só o nome do banco, de uma lista fixa; o resto vira "outro" (a conta pode vir do
    nome do arquivo, que às vezes traz o nome da pessoa)."""
    n = normalizar(str(conta or ""))
    for palavra, banco in BANCOS:
        if re.search(rf"(^|[^a-z]){re.escape(palavra)}", n):
            return banco
    return "outro"


def formato_do_arquivo(nome, conteudo=b""):
    ext = (nome or "").lower().rsplit(".", 1)[-1] if "." in (nome or "") else ""
    if conteudo[:4] == b"%PDF":
        return "pdf"
    if ext in {"csv", "txt"}:
        return "csv"
    if ext in {"xlsx", "xls", "excel"}:
        return "excel"
    if ext in {"ofx", "pdf", "zip", "xml"}:
        return ext
    return "sem extensão" if not ext else "outro"


# Mensagens fixas do próprio app (financeiro.py, leitores_pdf.py): podem ser anotadas.
# Qualquer outra mensagem pode trazer trechos do extrato e vira só o tipo do erro
ERROS = [  # (começo da mensagem, como é anotado)
    ("pdf não reconhecido", "PDF de banco não reconhecido"),
    ("pdf sem texto", "PDF sem texto (imagem)"),
    ("xml", "XML no lugar do extrato"),
    ("formato .", "formato não lido"),
    ("o arquivo está vazio", "arquivo vazio"),
    ("escolha as colunas", "colunas de data/descrição não identificadas"),
    ("escolha a coluna de valor", "coluna de valor não identificada"),
    ("nenhum lançamento", "nenhum lançamento encontrado"),
    ("o .zip", "problema no .zip"),
    ("o arquivo .zip", "problema no .zip"),
    ("relatório do sispag", "SISPAG sem pagamentos"),
]
# "extrato Itaú sem agência...", "fatura sem data de vencimento." etc.
_FIXA_SEM = re.compile(r"^(extrato|fatura|resumo)( [\w ]{1,20})? sem [\w ,]{3,60}\.?$")


def tipo_do_erro(erro):
    """Uma categoria fixa para o erro: a mensagem em si pode trazer trechos do extrato."""
    texto = str(erro).strip().lower()
    for comeco, tipo in ERROS:
        if texto.startswith(comeco):
            return tipo
    if _FIXA_SEM.match(texto):
        return texto.rstrip(".")
    return type(erro).__name__ if isinstance(erro, BaseException) else "outro"


def origem(parametros):
    """De onde veio a visita: ?utm_source=instagram (ou ?ref=...) no link divulgado."""
    valor = parametros.get("utm_source") or parametros.get("ref") or ""
    valor = re.sub(r"[^a-z0-9_\-.]", "", str(valor).lower())[:40]
    return valor or "direto"


# ============================================================================
# GRAVAR
# ============================================================================
class Registro:
    """Anota os eventos de uma visita. `estado` é o st.session_state (ou um dict, nos
    testes); `config` traz url e chave do Supabase (None = só memória)."""

    def __init__(self, estado, url=None, chave=None, ativo=True):
        self.estado, self.url, self.chave, self.ligado = estado, url, chave, ativo
        if "uso_codigo" not in estado:
            estado["uso_codigo"] = novo_codigo()
            estado["uso_inicio"] = agora()
            estado["uso_vistos"] = set()

    @property
    def codigo(self):
        return self.estado["uso_codigo"]

    def comecar(self, **dados):
        """A visita começou. Só é gravado junto do próximo evento (um clique ou o primeiro
        aviso de página aberta): na primeira visita o app recarrega a página sozinho para
        aplicar o tema, e aquela sessão de menos de um segundo não é uma visita."""
        if self.ligado and "uso_comecou" not in self.estado:
            self.estado["uso_comecou"] = True
            self.estado["uso_pendente"] = self._linha("entrou", dados)

    def _linha(self, evento, dados):
        return {"momento": agora().isoformat(timespec="seconds"), "sessao": self.codigo,
                "evento": evento, "dados": dados}

    def anotar(self, evento, **dados):
        if not self.ligado:
            return
        pendente = self.estado.pop("uso_pendente", None)
        for linha in ([pendente] if pendente else []) + [self._linha(evento, dados)]:
            self._gravar(linha)

    def _gravar(self, linha):
        _MEMORIA.append(linha)
        if self.url and self.chave:
            _ENVIO.submit(_enviar, self.url, self.chave, linha)

    def uma_vez(self, chave, evento, **dados):
        """Anota só na primeira vez nesta visita (o app roda o script a cada clique)."""
        if chave in self.estado["uso_vistos"]:
            return
        self.estado["uso_vistos"].add(chave)
        self.anotar(evento, **dados)

    def mudou(self, o_que, valor, evento, **dados):
        """Anota quando o valor muda (página, aba): o primeiro valor também conta."""
        chave = f"uso_ultimo_{o_que}"
        if self.estado.get(chave) == valor:
            return
        self.estado[chave] = valor
        self.anotar(evento, **dados)

    def ainda_aberta(self):
        """Chamado de tempos em tempos enquanto a página está aberta."""
        minutos = (agora() - self.estado["uso_inicio"]).total_seconds() / 60
        if minutos <= LIMITE_ATIVO:
            self.anotar("ativo")


def _enviar(url, chave, linha):
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/rest/v1/{TABELA}", data=json.dumps(linha).encode(),
            method="POST",
            headers={"apikey": chave, "Authorization": f"Bearer {chave}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception:  # noqa: BLE001 - medição nunca derruba o app
        pass


# ============================================================================
# LER (página de administração)
# ============================================================================
def carregar(url=None, chave=None, dias=30):
    """Eventos dos últimos `dias`: do Supabase quando configurado, senão da memória."""
    desde = agora() - timedelta(days=dias)
    if url and chave:
        linhas, inicio, lote = [], 0, 1000
        while True:
            req = urllib.request.Request(
                f"{url.rstrip('/')}/rest/v1/{TABELA}?select=momento,sessao,evento,dados"
                f"&momento=gte.{desde.isoformat(timespec='seconds').replace('+', '%2B')}"
                f"&order=momento.asc",
                headers={"apikey": chave, "Authorization": f"Bearer {chave}",
                         "Range-Unit": "items", "Range": f"{inicio}-{inicio + lote - 1}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                parte = json.loads(r.read())
            linhas += parte
            if len(parte) < lote:
                break
            inicio += lote
    else:
        linhas = [x for x in list(_MEMORIA) if x["momento"] >= desde.isoformat()]
    return tabela_de_eventos(linhas)


def tabela_de_eventos(linhas):
    ev = pd.DataFrame(linhas, columns=["momento", "sessao", "evento", "dados"])
    ev["momento"] = pd.to_datetime(ev["momento"], utc=True, format="ISO8601")
    ev["dados"] = ev["dados"].map(lambda d: d if isinstance(d, dict)
                                  else json.loads(d) if isinstance(d, str) and d else {})
    return ev.sort_values(["sessao", "momento"], kind="stable").reset_index(drop=True)


def _rotulo(evento, dados):
    """Como o passo aparece no caminho da visita."""
    if evento == "pagina":
        return dados.get("nome", "página")
    if evento == "visao":
        return f"Painel · {dados.get('nome', '')}"
    if evento == "arquivo":
        return (f"{dados.get('formato', '')} {dados.get('banco', '')}"
                f" {'ok' if dados.get('ok') else '✗ ' + dados.get('erro', '')}").strip()
    if evento == "exportou":
        return f"exportou {dados.get('tipo', '')}"
    if evento == "plus":
        return f"Plus: {dados.get('acao', '')}"
    return evento


ETAPAS = [  # funil: (nome, a visita chegou lá se teve algum destes eventos)
    ("Entrou", {"entrou"}),
    ("Enviou extrato", {"enviou"}),
    ("Viu o painel", {"painel"}),
    ("Abriu outra aba", {"pagina_outra", "visao_outra"}),
    ("Exportou ou foi ao Plus", {"exportou", "plus"}),
]


def resumo_sessoes(ev):
    """Uma linha por visita: início, duração, dispositivo, origem, até onde foi e onde
    parou (o último passo antes de fechar)."""
    colunas = ["sessao", "inicio", "fim", "minutos", "dispositivo", "origem", "etapa",
               "parou_em", "erros", "caminho"]
    if ev.empty:
        return pd.DataFrame(columns=colunas)
    linhas = []
    for sessao, g in ev.groupby("sessao", sort=False):
        entrou = g[g["evento"] == "entrou"]
        info = entrou["dados"].iat[0] if not entrou.empty else {}
        acoes = g[~g["evento"].isin(PASSIVOS)]
        passos = [_rotulo(e, d) for e, d in zip(acoes["evento"], acoes["dados"])]
        # As primeiras página e aba são as de abertura; só uma mudança conta como "outra"
        tem = set(g["evento"])
        if (g["evento"] == "pagina").sum() > 1:
            tem.add("pagina_outra")
        if (g["evento"] == "visao").sum() > 1:
            tem.add("visao_outra")
        etapa = next((nome for nome, eventos in reversed(ETAPAS) if tem & eventos), "—")
        # Onde estava ao sair: a última página ou aba aberta (ou a tela inicial)
        lugares = acoes[acoes["evento"].isin({"pagina", "visao"})]
        if "painel" not in tem:
            parou = "Tela inicial (sem extrato)" if "enviou" not in tem \
                else "Lendo o extrato (não chegou ao painel)"
        elif lugares.empty:
            parou = "📊 Painel"
        else:
            parou = _rotulo(lugares["evento"].iat[-1], lugares["dados"].iat[-1])
        erros = int(sum(1 for e, d in zip(g["evento"], g["dados"])
                        if e == "arquivo" and not d.get("ok")))
        inicio, fim = g["momento"].min(), g["momento"].max()
        linhas.append({
            "sessao": sessao, "inicio": inicio, "fim": fim,
            "minutos": round((fim - inicio).total_seconds() / 60, 1),
            "dispositivo": info.get("dispositivo", "?"), "origem": info.get("origem", "?"),
            "etapa": etapa, "parou_em": parou, "erros": erros,
            "caminho": " → ".join(_sem_repetir(passos)),
        })
    return pd.DataFrame(linhas, columns=colunas).sort_values("inicio", ascending=False,
                                                             ignore_index=True)


def _sem_repetir(passos):
    saida = []
    for p in passos:
        if not saida or saida[-1] != p:
            saida.append(p)
    return saida


def funil(sessoes):
    """Quantas visitas chegaram a cada etapa (cada etapa inclui as seguintes)."""
    nomes = [n for n, _ in ETAPAS]
    alcance = sessoes["etapa"].map({n: i for i, n in enumerate(nomes)}).fillna(-1)
    total = len(sessoes)
    linhas = []
    for i, nome in enumerate(nomes):
        n = int((alcance >= i).sum())
        linhas.append({"Etapa": nome, "Visitas": n,
                       "% das visitas": round(100 * n / total, 1) if total else 0.0})
    return pd.DataFrame(linhas)


def erros_de_leitura(ev):
    """Arquivos que o app não conseguiu ler, por formato, banco e tipo de erro."""
    arq = ev[ev["evento"] == "arquivo"]
    linhas = [{"Formato": d.get("formato", "?"), "Banco": d.get("banco", "?"),
               "Erro": d.get("erro", "?")} for d in arq["dados"] if not d.get("ok")]
    if not linhas:
        return pd.DataFrame(columns=["Formato", "Banco", "Erro", "Arquivos"])
    return (pd.DataFrame(linhas).value_counts().rename("Arquivos").reset_index()
            .sort_values("Arquivos", ascending=False, ignore_index=True))


def leituras(ev):
    """Arquivos enviados por formato e banco: quantos lidos e quantos com erro."""
    arq = ev[ev["evento"] == "arquivo"]
    if arq.empty:
        return pd.DataFrame(columns=["Formato", "Banco", "Lidos", "Com erro"])
    t = pd.DataFrame([{"Formato": d.get("formato", "?"), "Banco": d.get("banco", "?"),
                       "ok": bool(d.get("ok"))} for d in arq["dados"]])
    r = t.groupby(["Formato", "Banco"])["ok"].agg(Lidos="sum", Total="count").reset_index()
    r["Com erro"] = r["Total"] - r["Lidos"]
    return (r.drop(columns="Total").sort_values(["Com erro", "Lidos"], ascending=False,
                                                ignore_index=True))
