"""
Códigos de acesso ao Plus: assinados, com validade e vinculados ao titular.

Formato: PLUS-AAAAMMDD-XXXX-SSSSSSSS
  AAAAMMDD  último dia de acesso
  XXXX      identificação do código (aleatória; serve para bloquear um código)
  SSSSSSSS  assinatura: HMAC da validade, da identificação e do nome do titular, com a
            chave secreta PLUS_CHAVE. Sem a chave não dá para criar nem alterar um código.

Nada é guardado: o app confere a assinatura, a data e o nome na hora. O nome não vai
escrito no código; quem usa precisa digitar o mesmo nome completo que o administrador
informou ao gerar (o nome do titular, como aparece no extrato).
"""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import date, datetime

from financeiro import normalizar

_FORMATO = re.compile(r"^PLUS-(\d{8})-([A-Z2-7]{4})-([A-Z2-7]{8})$")


def normalizar_nome(nome):
    """Sem acento, maiúsculas e espaços repetidos: "Maria  da Silva" = "MARIA DA SILVA"."""
    return " ".join(normalizar(nome or "").split())


def _assinatura(chave, validade, ident, nome):
    msg = f"{validade}|{ident}|{normalizar_nome(nome)}".encode()
    mac = hmac.new(chave.encode(), msg, hashlib.sha256).digest()
    return base64.b32encode(mac).decode()[:8]


def gerar_codigo(chave, nome, validade, ident=None):
    """Código para o titular `nome`, válido até `validade` (date), inclusive."""
    if not chave:
        raise ValueError("falta a chave PLUS_CHAVE nos Secrets.")
    if len(normalizar_nome(nome).split()) < 2:
        raise ValueError("informe nome e sobrenome do titular.")
    ident = ident or base64.b32encode(secrets.token_bytes(5)).decode()[:4]
    v = validade.strftime("%Y%m%d")
    return f"PLUS-{v}-{ident}-{_assinatura(chave, v, ident, nome)}"


def validar_codigo(chave, codigo, nome, hoje=None, bloqueados=()):
    """Confere um código. Retorna {"ok", "motivo", "validade", "ident"}."""
    hoje = hoje or date.today()
    codigo = re.sub(r"\s+", "", (codigo or "")).upper()
    m = _FORMATO.match(codigo)
    if not m or not chave:
        return {"ok": False, "motivo": "Código inválido.", "validade": None, "ident": None}
    v, ident, assinatura = m.groups()
    try:
        validade = datetime.strptime(v, "%Y%m%d").date()
    except ValueError:
        return {"ok": False, "motivo": "Código inválido.", "validade": None, "ident": None}
    if not hmac.compare_digest(assinatura, _assinatura(chave, v, ident, nome)):
        return {"ok": False, "validade": None, "ident": None,
                "motivo": "Código ou nome não conferem. Digite o nome completo do titular, "
                          "igual ao informado na compra."}
    if ident in bloqueados or codigo in bloqueados:
        return {"ok": False, "motivo": "Este código foi cancelado.", "validade": validade,
                "ident": ident}
    if validade < hoje:
        return {"ok": False, "validade": validade, "ident": ident,
                "motivo": f"Seu acesso venceu em {validade:%d/%m/%Y}. Renove para continuar."}
    return {"ok": True, "motivo": "", "validade": validade, "ident": ident}


def mesmo_titular(nome_codigo, nome_extrato):
    """O titular do extrato é a pessoa do código? Compara o primeiro e o último nome
    ("Maria Silva" = "MARIA DE SOUZA SILVA"), sem acento e sem maiúsculas."""
    a, b = normalizar_nome(nome_codigo).split(), normalizar_nome(nome_extrato).split()
    if not a or not b:
        return True   # sem nome para comparar
    return a[0] == b[0] and a[-1] == b[-1]
