"""Testes da página lida pelo Google e pelas prévias de link (site/aplicar.py)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))

import aplicar  # noqa: E402

HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Streamlit</title>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>"""


def test_troca_titulo_idioma_e_corpo():
    html = aplicar.aplicar_no_html(HTML, "<title>Contas</title>", "<p>Texto</p>")
    assert "<title>Streamlit</title>" not in html
    assert "<title>Contas</title>" in html
    assert '<html lang="pt-BR">' in html
    assert "You need to enable JavaScript" not in html
    assert '<div id="root">\n    <p>Texto</p>\n    </div>' in html


def test_rodar_de_novo_nao_duplica():
    uma = aplicar.aplicar_no_html(HTML, "<title>Contas</title>", "<p>Texto</p>")
    assert aplicar.aplicar_no_html(uma, "<title>Contas</title>", "<p>Texto</p>") == uma


def test_arquivos_do_site_existem_e_tem_o_essencial():
    cab = aplicar.ler("cabecalho.html")
    for tag in ["<title>", 'name="description"', 'property="og:image"', "application/ld+json"]:
        assert tag in cab
    assert "Suas Contas em Dia" in aplicar.ler("conteudo.html")
    for nome in aplicar.ARQUIVOS_NA_RAIZ:
        assert os.path.exists(os.path.join(aplicar.AQUI, nome))


def test_index_do_streamlit_instalado_tem_o_formato_esperado():
    # Se o Streamlit mudar o index.html, o build do Docker falharia: este teste avisa antes
    with open(os.path.join(aplicar.pasta_do_streamlit(), "index.html"), encoding="utf-8") as f:
        original = f.read()
    html = aplicar.aplicar_no_html(original, aplicar.ler("cabecalho.html"),
                                   aplicar.ler("conteudo.html"))
    assert "Suas Contas em Dia" in html
