name: Folhetos - Lidl

on:
  workflow_dispatch:
  schedule:
    # Todas as segundas-feiras às 6:00 UTC, tal como o do Continente
    - cron: "0 6 * * 1"

permissions:
  contents: write

jobs:
  atualizar:
    runs-on: ubuntu-latest
    steps:
      - name: Descarregar o código do repositório
        uses: actions/checkout@v4

      - name: Preparar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Instalar dependências
        run: pip install -r folhetos/lidl/requirements.txt

      - name: Correr o scraper + parser e guardar histórico
        run: python folhetos/lidl/main_lidl.py

      - name: Guardar o resultado no repositório (commit)
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add folhetos/dados/
          git diff --staged --quiet || git commit -m "Atualiza histórico de folhetos (Lidl)"
          git push
