
import base64
import csv
import os
import re
import time
import tkinter as tk
from tkinter import filedialog
import sys

import resend
from dotenv import load_dotenv

from whatsTeste_v2 import high, abrir_whats, preparar_perfil_automacao, adicionar_contatos

load_dotenv()

api_key = os.getenv("RESEND_API_KEY")

if not api_key:
    raise RuntimeError("RESEND_API_KEY não encontrada no arquivo .env")

resend.api_key = api_key

PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
CAMINHO_IMAGEM = os.path.join(PASTA_ATUAL, "arte_LAF_Sites.png")

REMETENTE = "LAF Soluções Empresariais <contato@lafsolucoes.xyz>"
RESPONDER_PARA = "sejaluzluminarias3d@gmail.com"
ASSUNTO = "Faça seu site, com sua cara!"

REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CABECALHOS = {
    "nome",
    "name",
    "cliente",
    "client",
    "telefone",
    "phone",
    "whatsapp",
    "email",
    "e-mail",
}

_root = None


def obter_root():
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()
    return _root


def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")

def mensagem_wpp(texto, largura=50, borda="-", alinhamento="center"):
    largura = max(largura, len(texto) + 2)

    linha = "|" + borda * (largura - 2) + "|"

    if alinhamento == "center":
        conteudo = texto.center(largura - 2)
    elif alinhamento == "right":
        conteudo = texto.rjust(largura - 2)
    else:
        conteudo = texto.ljust(largura - 2)

    print(linha)
    print("|" + conteudo + "|")
    print(linha)

def printar_cabecalho():
    print("########################")
    print("OLHA-A-MENSAGEM.app - v0")
    print("########################\n")


def pausar(mensagem="Pressione ENTER para continuar..."):
    input(mensagem)


def filtrar_numero(numero):
    return re.sub(r"\D", "", str(numero))


def e_cabecalho(linha):
    return any(celula.strip().lower() in CABECALHOS for celula in linha[:3])


def detectar_delimitador(caminho):
    with open(caminho, "r", encoding="utf-8-sig", newline="") as arquivo:
        amostra = arquivo.read(4096)

    try:
        return csv.Sniffer().sniff(
            amostra,
            delimiters=",;\t"
        ).delimiter
    except csv.Error:
        return " "


def carregar_clientes(caminho):
    delimitador = detectar_delimitador(caminho)
    clientes = []

    with open(caminho, "r", encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.reader(
            arquivo,
            delimiter=delimitador,
            skipinitialspace=True
        )

        for numero_linha, linha in enumerate(leitor, start=1):
            linha = [celula.strip() for celula in linha]

            if not any(linha):
                continue

            if numero_linha == 1 and e_cabecalho(linha):
                continue

            clientes.append(linha)

    return clientes


def escolher_arquivo(titulo, tipos):
    root = obter_root()
    root.attributes("-topmost", True)

    try:
        arquivo = filedialog.askopenfilename(title=titulo, filetypes=tipos)
    finally:
        root.attributes("-topmost", False)

    if arquivo:
        print("Arquivo selecionado:", arquivo, "\n")
        return arquivo

    print("Nenhum arquivo selecionado.\n")
    return None


def escolher_mensagem():
    caminho = escolher_arquivo(
        "Selecione o arquivo da mensagem (.txt)",
        [("Arquivos de texto", "*.txt"), ("Todos os arquivos", "*.*")],
    )

    if caminho is None:
        return None

    with open(caminho, "r", encoding="utf-8") as arquivo:
        texto = arquivo.read().strip()

    if not texto:
        print("O arquivo de mensagem está vazio.")
        pausar()
        return None

    return texto


def escolher_clientes(titulo="Selecione o arquivo .CSV com os clientes"):
    caminho = escolher_arquivo(
        titulo,
        [("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")],
    )

    if caminho is None:
        return None, None

    clientes = carregar_clientes(caminho)

    if not clientes:
        print("Nenhum cliente encontrado no CSV.")
        pausar()
        return None, None

    return caminho, clientes


def menu():
    while True:
        limpar_tela()
        printar_cabecalho()

        print("0 - Enviar por E-mail")
        print("1 - WhatsApp")
        print("9 - Sair\n")

        try:
            escolha_menu = input("Escolha a opção desejada: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperação interrompida.")
            break

        match escolha_menu:
            case "0":
                enviar_email()
            case "1":
                menu_whatsapp()
            case "9":
                limpar_tela()
                print("Até a próxima!")
                break
            case _:
                print("\nInsira uma opção válida!")
                pausar()


def menu_whatsapp():
    # Abre o WhatsApp Web graficamente antes de apresentar as ações.
    # O navegador permanece aberto para o usuário navegar manualmente e também
    # é reutilizado pelas automações, evitando abrir uma segunda janela/perfil.
    driver = abrir_whats()
    if driver is None:
        print("Não foi possível abrir o WhatsApp Web.")
        pausar()
        return

    try:
        while True:
            limpar_tela()
            printar_cabecalho()
            print("WHATSAPP WEB ABERTO\n")
            print("O navegador está aberto. Você pode navegar normalmente nele.")
            print("1 - Adicionar contatos")
            print("2 - Enviar mensagens")
            print("3 - Continuar navegando no WhatsApp")
            print("0 - Fechar WhatsApp e voltar ao menu principal\n")

            escolha = input("O que deseja fazer? [3]: ").strip()
            if escolha == "":
                escolha = "3"

            if escolha == "1":
                add_contato(driver)
            elif escolha == "2":
                enviar_whats(driver)
            elif escolha == "3":
                input("Navegue no WhatsApp Web. Pressione ENTER aqui para voltar às opções...")
            elif escolha == "0":
                break
            else:
                print("Opção inválida.")
                pausar()
    except (EOFError, KeyboardInterrupt):
        print("\nVoltando ao menu principal...")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def enviar_email():
    limpar_tela()
    printar_cabecalho()
    print("ENVIO POR E-MAIL\n")
    print("1° passo: selecionar a mensagem a ser enviada")
    pausar()

    texto = escolher_mensagem()

    if texto is None:
        return

    print("2° passo: selecionar o .CSV com os clientes")
    pausar()

    caminho_csv, clientes = escolher_clientes()

    if caminho_csv is None:
        return

    destinatarios = []
    invalidos = 0

    for cliente in clientes:
        if len(cliente) < 3 or not REGEX_EMAIL.match(cliente[2]):
            invalidos += 1
            continue

        destinatarios.append(cliente[2])

    destinatarios = list(dict.fromkeys(destinatarios))

    if not destinatarios:
        print("Nenhum e-mail válido encontrado no CSV.")
        pausar()
        return

    limpar_tela()
    printar_cabecalho()
    print("CONFIRMANDO O ENVIO...\n")
    print("Mensagem:\n")
    print(texto)
    print(f"\nDestinatários válidos: {len(destinatarios)}")
    for d in destinatarios:
        print(d)
    if invalidos:
        print(f"Linhas ignoradas (sem e-mail válido): {invalidos}")

    print("\nImagem que será anexada:", CAMINHO_IMAGEM)

    if not os.path.isfile(CAMINHO_IMAGEM):
        print("\nERRO: o arquivo arte_LAF_Sites.png não foi encontrado.")
        pausar()
        return

    confirmacao = input("\nDeseja iniciar o envio? (s/n): ").strip().lower()

    if confirmacao != "s":
        print("Operação cancelada.")
        pausar()
        return

    with open(CAMINHO_IMAGEM, "rb") as imagem:
        imagem_base64 = base64.b64encode(imagem.read()).decode("utf-8")

    limpar_tela()
    printar_cabecalho()
    print(f"Enviando {len(destinatarios)} e-mail(s)...\n")

    enviados = 0
    falhas = 0

    for indice, email_destino in enumerate(destinatarios, start=1):
        try:
            resposta = resend.Emails.send(
                {
                    "from": REMETENTE,
                    "reply_to": RESPONDER_PARA,
                    "to": [email_destino],
                    "subject": ASSUNTO,
                    "text": texto,
                    "attachments": [
                        {
                            "filename": "arte_LAF_Sites.png",
                            "content": imagem_base64,
                            "content_type": "image/png",
                        }
                    ],
                }
            )

            enviados += 1
            print(
                f"[{indice}/{len(destinatarios)}] Enviado para "
                f"{email_destino} (ID: {resposta.get('id', 'n/d')})"
            )
        except Exception as erro:
            falhas += 1
            print(
                f"[{indice}/{len(destinatarios)}] Erro ao enviar para "
                f"{email_destino}: {erro}"
            )

        if indice < len(destinatarios):
            time.sleep(1.0)

    print(f"\nResumo: {enviados} enviado(s), {falhas} falha(s).")
    pausar("\nProcesso finalizado. Pressione ENTER para continuar...")


def perguntar_sim_nao(pergunta, padrao):
    """Pergunta S/N; ENTER aceita o padrão informado."""
    padrao = padrao.upper()
    indicacao = "S/n" if padrao == "S" else "s/N"
    resposta = input(f"{pergunta} ({indicacao}): ").strip().lower()
    if not resposta:
        resposta = padrao.lower()
    return resposta in ("s", "sim", "y", "yes")


def enviar_whats(driver=None):
    mandarFoto = False
    mandarBoasVindas = False
    limpar_tela()
    printar_cabecalho()
    print("ENVIO POR WHATSAPP\n")
    print("1° passo: selecionar a mensagem a ser enviada")
    pausar()

    texto = escolher_mensagem()

    if texto is None:
        return

    print("2° passo: selecionar o .CSV com os clientes")
    pausar()

    caminho_csv, clientes = escolher_clientes()

    if caminho_csv is None:
        return

    mandarFoto = perguntar_sim_nao(
        "3° passo: Deseja enviar uma foto?", "N"
    )
    mandarBoasVindas = perguntar_sim_nao(
        "4° passo: Deseja enviar boas-vindas? (Ex.: Olá NOME, tudo bem?)", "S"
    )

    perfil_firefox = "sessão do WhatsApp Web já aberta" if driver is not None else None
    if driver is None:
        try:
            perfil_firefox = preparar_perfil_automacao()
        except Exception as erro:
            print(f"\nNão é possível preparar o Firefox: {erro}")
            pausar()
            return

    lista_clientes = []
    telefones_vistos = set()
    invalidos = 0

    lista_clientes_contatados = []
    lista_clientes_faltantes = []

    for cliente in clientes:
        if len(cliente) < 2:
            invalidos += 1
            continue

        telefone = filtrar_numero(cliente[1])

        if len(telefone) < 8 or telefone in telefones_vistos:
            invalidos += 1
            continue

        telefones_vistos.add(telefone)
        cliente = list(cliente)
        cliente[1] = telefone
        lista_clientes.append(cliente)

    if not lista_clientes:
        print("Nenhum telefone válido encontrado no CSV.")
        pausar()
        return

    limpar_tela()
    printar_cabecalho()
    print("=====CONFIRMANDO O ENVIO...=====\n")
    if(mandarFoto):
        mensagem_wpp("[FOTO]")
        print("\n")
    if(mandarBoasVindas):
        mensagem_wpp("Olá, NOME! Tudo bem?")
        print("\n")

    mensagem_wpp(texto)

    print(f"\nClientes válidos: {len(lista_clientes)}")

    if invalidos:
        print(f"Linhas ignoradas (sem telefone válido ou duplicadas): {invalidos}")

    print("Perfil de automação do Firefox:", perfil_firefox)
    print("\nContatos:")

    for cliente in lista_clientes:
        nome = cliente[0] if cliente[0] else "sem nome"
        print(f"- {nome}: {cliente[1]}")

    confirmar_envio = perguntar_sim_nao(
        "\nDeseja iniciar o envio pelo WhatsApp?", "S"
    )

    if not confirmar_envio:
        print("Operação cancelada.")
        pausar()
        return

    limpar_tela()
    printar_cabecalho()
    print(f"Enviando para {len(lista_clientes)} cliente(s)...\n")

    try:
        high(texto, lista_clientes, mandarFoto, mandarBoasVindas, driver=driver, caminho_foto=CAMINHO_IMAGEM if mandarFoto else None)
    except Exception as erro:
        print(f"Erro durante a automação do WhatsApp: {erro}")

    pausar("\nProcesso finalizado. Pressione ENTER para continuar...")


def add_contato(driver=None):
    limpar_tela()
    printar_cabecalho()
    print("ADICIONAR CONTATOS\n")

    print("1° passo: selecionar o .CSV com os clientes")
    pausar()

    caminho_csv, clientes = escolher_clientes()

    if caminho_csv is None:
        return

    if driver is None:
        try:
            preparar_perfil_automacao()
        except Exception as erro:
            print(f"\nNão é possível preparar o Firefox: {erro}")
            pausar()
            return

    lista_contatos_adicionados = []
    lista_contatos_faltantes = []
    adicionar_contatos(clientes, lista_contatos_adicionados, lista_contatos_faltantes, driver=driver)

    print("=========RESUMO=========")
    print("CONTATOS ADICIONADOS:", len(lista_contatos_adicionados))
    print("\nCONTATOS FALTANTES:")
    print(lista_contatos_faltantes)

    pausar("\nProcesso finalizado. Pressione ENTER para continuar...")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] in {"email", "whatsapp"}:
            if sys.argv[1] == "email":
                enviar_email()
            else:
                menu_whatsapp()
        else:
            if len(sys.argv) > 1:
                os.chdir(sys.argv[1])
            menu()

    except KeyboardInterrupt:
        print("\n\nOperação interrompida.")