"""Testes da medição de uso. Todos os dados são inventados."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uso  # noqa: E402

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _ev(sessao, minuto, evento, **dados):
    return {"momento": (T0 + timedelta(minutes=minuto)).isoformat(), "sessao": sessao,
            "evento": evento, "dados": dados}


# ----------------------------------------------------------------------------
# O que pode ser anotado
# ----------------------------------------------------------------------------
def test_banco_so_da_lista_fixa():
    assert uso.banco_da_conta("Nubank") == "Nubank"
    assert uso.banco_da_conta("BB Conta") == "BB"
    assert uso.banco_da_conta("Itaú + Itaú Aplicação") == "Itaú"
    assert uso.banco_da_conta("Sicoob") == "Sicoob"
    # Conta tirada do nome do arquivo pode ter o nome da pessoa: não é anotada
    assert uso.banco_da_conta("extrato_maria_souza") == "outro"
    assert uso.banco_da_conta("jubbas") == "outro"


def test_formato():
    assert uso.formato_do_arquivo("a.CSV") == "csv"
    assert uso.formato_do_arquivo("a.xls") == "excel"
    assert uso.formato_do_arquivo("a.ofx") == "ofx"
    assert uso.formato_do_arquivo("sem_extensao", b"%PDF-1.4") == "pdf"
    assert uso.formato_do_arquivo("sem_extensao") == "sem extensão"


def test_erro_so_mensagens_fixas():
    assert uso.tipo_do_erro(ValueError("PDF não reconhecido (são lidos...)")) == \
        "PDF de banco não reconhecido"
    assert uso.tipo_do_erro(ValueError("extrato Itaú sem agência, conta e mês.")) == \
        "extrato itaú sem agência, conta e mês"
    # Mensagem de outra biblioteca pode trazer trecho do extrato: só o tipo do erro
    assert uso.tipo_do_erro(ValueError("could not convert string to float: 'JOAO'")) == \
        "ValueError"


def test_origem_limpa():
    assert uso.origem({"utm_source": "Instagram"}) == "instagram"
    assert uso.origem({"ref": "zap<script>"}) == "zapscript"
    assert uso.origem({}) == "direto"


# ----------------------------------------------------------------------------
# Gravar
# ----------------------------------------------------------------------------
def test_registro_uma_vez_e_mudou():
    estado = {}
    r = uso.Registro(estado)
    antes = len(uso._MEMORIA)
    r.uma_vez("entrou", "entrou", dispositivo="celular")
    r.uma_vez("entrou", "entrou", dispositivo="celular")
    r.mudou("pagina", "📊 Painel", "pagina", nome="📊 Painel")
    r.mudou("pagina", "📊 Painel", "pagina", nome="📊 Painel")
    r.mudou("pagina", "📥 Download", "pagina", nome="📥 Download")
    novos = list(uso._MEMORIA)[antes:]
    assert [x["evento"] for x in novos] == ["entrou", "pagina", "pagina"]
    assert {x["sessao"] for x in novos} == {r.codigo}


def test_entrou_so_e_gravado_com_o_proximo_evento():
    estado = {}
    r = uso.Registro(estado)
    antes = len(uso._MEMORIA)
    r.comecar(dispositivo="celular", origem="direto")
    r.comecar(dispositivo="celular", origem="direto")   # o script roda a cada clique
    # A recarga do tema na primeira visita: a sessão acaba aqui e nada é gravado
    assert len(uso._MEMORIA) == antes
    r.ainda_aberta()
    novos = list(uso._MEMORIA)[antes:]
    assert [x["evento"] for x in novos] == ["entrou", "ativo"]
    assert novos[0]["dados"] == {"dispositivo": "celular", "origem": "direto"}


def test_registro_desligado_nao_anota():
    r = uso.Registro({}, ativo=False)
    antes = len(uso._MEMORIA)
    r.anotar("entrou")
    assert len(uso._MEMORIA) == antes


# ----------------------------------------------------------------------------
# Ler
# ----------------------------------------------------------------------------
def _visitas():
    return uso.tabela_de_eventos([
        # a: saiu na tela inicial
        _ev("a", 0, "entrou", dispositivo="celular", origem="instagram"),
        _ev("a", 1, "ativo"),
        # b: PDF não lido, não chegou ao painel
        _ev("b", 0, "entrou", dispositivo="computador", origem="direto"),
        _ev("b", 1, "enviou", arquivos=1),
        _ev("b", 1, "arquivo", formato="pdf", banco="outro", ok=False,
            erro="PDF de banco não reconhecido"),
        # c: viu o painel, foi a Saídas e parou lá
        _ev("c", 0, "entrou", dispositivo="celular", origem="instagram"),
        _ev("c", 1, "enviou", arquivos=1),
        _ev("c", 1, "arquivo", formato="csv", banco="Nubank", ok=True),
        _ev("c", 1, "painel", transacoes=100),
        _ev("c", 1, "pagina", nome="📊 Painel"),
        _ev("c", 1, "visao", nome="Resumo"),
        _ev("c", 2, "visao", nome="Saídas"),
        _ev("c", 3, "ativo"),
        _ev("c", 4, "ativo"),
        # d: exportou
        _ev("d", 0, "entrou", dispositivo="computador", origem="whatsapp"),
        _ev("d", 1, "enviou", arquivos=2),
        _ev("d", 1, "arquivo", formato="ofx", banco="Itaú", ok=True),
        _ev("d", 1, "painel", transacoes=50),
        _ev("d", 1, "pagina", nome="📊 Painel"),
        _ev("d", 2, "pagina", nome="📥 Download"),
        _ev("d", 2, "exportou", tipo="XLSX"),
    ])


def test_resumo_das_visitas():
    s = uso.resumo_sessoes(_visitas()).set_index("sessao")
    assert s.loc["a", "parou_em"] == "Tela inicial (sem extrato)"
    assert s.loc["a", "etapa"] == "Entrou"
    assert s.loc["b", "parou_em"] == "Lendo o extrato (não chegou ao painel)"
    assert s.loc["b", "erros"] == 1
    assert s.loc["c", "parou_em"] == "Painel · Saídas"
    assert s.loc["c", "etapa"] == "Abriu outra aba"
    assert s.loc["c", "minutos"] == 4.0
    assert s.loc["d", "parou_em"] == "📥 Download"
    assert s.loc["d", "etapa"] == "Exportou ou foi ao Plus"
    assert "exportou XLSX" in s.loc["d", "caminho"]
    assert "ativo" not in s.loc["c", "caminho"]


def test_funil_inclui_etapas_seguintes():
    f = uso.funil(uso.resumo_sessoes(_visitas())).set_index("Etapa")["Visitas"]
    assert f.to_dict() == {"Entrou": 4, "Enviou extrato": 3, "Viu o painel": 2,
                           "Abriu outra aba": 2, "Exportou ou foi ao Plus": 1}


def test_leituras_e_erros():
    ev = _visitas()
    erros = uso.erros_de_leitura(ev)
    assert erros.to_dict("records") == [{"Formato": "pdf", "Banco": "outro",
                                         "Erro": "PDF de banco não reconhecido",
                                         "Arquivos": 1}]
    lidos = uso.leituras(ev).set_index(["Formato", "Banco"])
    assert lidos.loc[("pdf", "outro"), "Com erro"] == 1
    assert lidos.loc[("csv", "Nubank"), "Lidos"] == 1


def test_sem_eventos():
    ev = uso.tabela_de_eventos([])
    assert uso.resumo_sessoes(ev).empty
    assert uso.erros_de_leitura(ev).empty
    assert uso.funil(uso.resumo_sessoes(ev))["Visitas"].sum() == 0
