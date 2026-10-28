#!/bin/sh
# Inicia o app no servidor (Docker/Render).
# No Render, os segredos vão em "Secret Files" com o nome secrets.toml e ficam em
# /etc/secrets; o Streamlit procura em .streamlit/secrets.toml
if [ -f /etc/secrets/secrets.toml ]; then
    mkdir -p .streamlit
    ln -sf /etc/secrets/secrets.toml .streamlit/secrets.toml
fi
exec streamlit run streamlit_app.py \
    --server.port "${PORT:-8501}" --server.address 0.0.0.0 \
    --server.headless true --browser.gatherUsageStats false
