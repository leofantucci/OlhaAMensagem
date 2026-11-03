#!/usr/bin/env bash
set -e
cd "$(dirname "$(realpath "$0")")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Erro: Python 3 não foi encontrado."
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Arquivo .env criado. Edite-o e informe sua RESEND_API_KEY antes de usar o envio por e-mail."
fi

exec python main.py
