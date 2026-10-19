"""Códigos Plus assinados. Nomes e chaves inventados."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from codigos import gerar_codigo, mesmo_titular, validar_codigo  # noqa: E402

CHAVE = "chave-de-teste"
HOJE = date(2026, 10, 19)


def test_codigo_valido_com_o_nome_do_titular():
    c = gerar_codigo(CHAVE, "Maria Exemplo da Silva", date(2026, 11, 30), ident="ABCD")
    assert c.startswith("PLUS-20261130-ABCD-")
    r = validar_codigo(CHAVE, c, "maria exemplo  da silva", hoje=HOJE)  # caixa e espaços
    assert r["ok"] and r["validade"] == date(2026, 11, 30)
    assert validar_codigo(CHAVE, c.lower(), "MARIA EXEMPLO DA SILVA", hoje=HOJE)["ok"]


def test_nome_errado_chave_errada_ou_codigo_alterado():
    c = gerar_codigo(CHAVE, "Maria Exemplo", date(2026, 11, 30))
    assert not validar_codigo(CHAVE, c, "João Exemplo", hoje=HOJE)["ok"]
    assert not validar_codigo("outra-chave", c, "Maria Exemplo", hoje=HOJE)["ok"]
    estendido = c.replace("20261130", "20271130")          # tentar mudar a validade
    assert not validar_codigo(CHAVE, estendido, "Maria Exemplo", hoje=HOJE)["ok"]
    assert not validar_codigo(CHAVE, "qualquer coisa", "Maria Exemplo", hoje=HOJE)["ok"]


def test_vencido_e_bloqueado():
    c = gerar_codigo(CHAVE, "Maria Exemplo", date(2026, 10, 18), ident="WXYZ")
    r = validar_codigo(CHAVE, c, "Maria Exemplo", hoje=HOJE)
    assert not r["ok"] and "venceu em 18/10/2026" in r["motivo"]
    assert validar_codigo(CHAVE, c, "Maria Exemplo", hoje=date(2026, 10, 18))["ok"]  # último dia
    c2 = gerar_codigo(CHAVE, "Maria Exemplo", date(2026, 12, 31), ident="BLOQ")
    assert not validar_codigo(CHAVE, c2, "Maria Exemplo", hoje=HOJE, bloqueados={"BLOQ"})["ok"]


def test_exige_nome_e_sobrenome():
    import pytest
    with pytest.raises(ValueError):
        gerar_codigo(CHAVE, "Maria", date(2026, 12, 31))


def test_mesmo_titular():
    assert mesmo_titular("Maria Silva", "MARIA DE SOUZA SILVA")
    assert mesmo_titular("Maria Exemplo da Silva", "Maria Exemplo Da Silva")
    assert not mesmo_titular("Maria Silva", "JOAO SILVA")
    assert mesmo_titular("Maria Silva", "")
