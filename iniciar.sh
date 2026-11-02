<<<<<<< HEAD
cd ~/Área\ de\ trabalho/Projetos/OlhaAMensagem/
source .venv/bin/activate

=======
#!/usr/bin/env bash
set -e
cd "$(dirname "$(readlink -f "$0")")"

if [[ ! -d ".venv" ]]; then
    echo "Ambiente virtual .venv não encontrado."
    echo "Crie-o com: python -m venv .venv"
    echo "Depois instale as dependências: .venv/bin/pip install -r requirements.txt"
    read -r -p "Pressione ENTER para sair..."
    exit 1
fi

source .venv/bin/activate
>>>>>>> 4eba4f7 (fita)
python main.py
