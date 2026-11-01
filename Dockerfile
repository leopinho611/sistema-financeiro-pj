# Servidor do app para hospedagens com Docker (Render). O Streamlit Community Cloud ignora
# este arquivo e usa o requirements.txt e o packages.txt.
FROM python:3.13-slim

# OCR dos PDFs sem texto (BNB): tesseract em português e o pdftoppm do poppler
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Título, descrição, prévia de link e texto para o Google no index.html do Streamlit, e
# robots.txt, sitemap.xml e previa.png na raiz do endereço
RUN python site/aplicar.py

CMD ["sh", "iniciar.sh"]
