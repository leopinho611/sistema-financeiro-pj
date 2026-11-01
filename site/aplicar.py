"""
Página que o Google, o WhatsApp e as redes sociais leem (rodado no build do Docker).

O Streamlit entrega sempre o mesmo index.html, com o título "Streamlit" e o corpo vazio: a
tela é montada depois, pelo JavaScript. Quem não roda JavaScript (prévia de link no WhatsApp,
Instagram e LinkedIn, vários robôs de busca e de IA) não via nada. Este script troca, no
index.html do Streamlit instalado:

- o título e as tags de descrição e de prévia (cabecalho.html);
- o corpo vazio por um texto sobre o app (conteudo.html), que o próprio app substitui ao abrir;
- o idioma, de "en" para "pt-BR".

E copia robots.txt, sitemap.xml e previa.png para a pasta que o Streamlit serve na raiz do
endereço (suascontasemdia.com.br/robots.txt...). Pode rodar mais de uma vez.

Uso: python site/aplicar.py
"""

import os
import re
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ARQUIVOS_NA_RAIZ = ["robots.txt", "sitemap.xml", "previa.png"]
MARCA = "<!-- Suas Contas em Dia -->"


def ler(nome):
    with open(os.path.join(AQUI, nome), encoding="utf-8") as f:
        return f.read()


def aplicar_no_html(html, cabecalho, conteudo):
    """index.html do Streamlit com o título, as tags e o texto do Suas Contas em Dia."""
    if MARCA in html:
        return html
    html = html.replace('<html lang="en">', '<html lang="pt-BR">', 1)
    html, n = re.subn(r"<title>.*?</title>", lambda _: f"{MARCA}\n    {cabecalho.strip()}",
                      html, count=1, flags=re.S)
    if not n:
        raise ValueError("index.html do Streamlit sem <title>: o formato mudou")
    html = re.sub(r"<noscript>.*?</noscript>\s*", "", html, count=1, flags=re.S)
    html, n = re.subn(r'<div id="root">\s*</div>',
                      lambda _: f'<div id="root">\n    {conteudo.strip()}\n    </div>', html,
                      count=1)
    if not n:
        raise ValueError('index.html do Streamlit sem <div id="root">: o formato mudou')
    return html


def pasta_do_streamlit():
    import streamlit
    return os.path.join(os.path.dirname(streamlit.__file__), "static")


def main():
    pasta = pasta_do_streamlit()
    indice = os.path.join(pasta, "index.html")
    with open(indice, encoding="utf-8") as f:
        html = f.read()
    with open(indice, "w", encoding="utf-8") as f:
        f.write(aplicar_no_html(html, ler("cabecalho.html"), ler("conteudo.html")))
    for nome in ARQUIVOS_NA_RAIZ:
        shutil.copyfile(os.path.join(AQUI, nome), os.path.join(pasta, nome))
    print(f"Página atualizada em {indice}")


if __name__ == "__main__":
    sys.exit(main())
