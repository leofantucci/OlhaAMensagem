import configparser
import os
import random
import shutil
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

LIMITE_LEGENDA = 1000

SELETOR_CAIXA_MENSAGEM = [
    (By.XPATH, "//footer//div[@contenteditable='true']"),
    (By.XPATH, "//div[@role='textbox' and @contenteditable='true']"),
]

SELETOR_NUMERO_SEM_WHATSAPP = [
    (By.XPATH, "//div[@role='dialog']//*[contains(text(), 'inválido')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(text(), 'inválida')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(text(), 'invalid')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(text(), 'não está no WhatsApp')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(text(), 'not on WhatsApp')]"),
]

SELETOR_BOTAO_OK = [
    (
        By.XPATH,
        "//div[@role='dialog']//button[normalize-space()='OK' or normalize-space()='Ok']",
    ),
    (
        By.XPATH,
        "//div[@role='dialog']//*[@role='button'][normalize-space()='OK' or normalize-space()='Ok']",
    ),
    (By.XPATH, "//div[@role='dialog']//button"),
    (By.XPATH, "//div[@role='dialog']//*[@role='button']"),
]


# ---------------------------------------------------------------------------
# Perfil do Firefox
# ---------------------------------------------------------------------------

def bases_firefox():
    home = Path.home()
    xdg_config = os.environ.get("XDG_CONFIG_HOME")

    candidatos = []

    if xdg_config:
        candidatos.append(Path(xdg_config) / "mozilla" / "firefox")

    candidatos.extend(
        [
            home / ".config" / "mozilla" / "firefox",
            home / ".mozilla" / "firefox",
            home / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
            home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",
        ]
    )

    bases = []
    vistos = set()

    for base in candidatos:
        chave = str(base)

        if chave not in vistos and base.is_dir():
            vistos.add(chave)
            bases.append(base)

    return bases


def ler_profiles_ini(base):
    caminho_ini = base / "profiles.ini"

    if not caminho_ini.is_file():
        return None, []

    parser = configparser.ConfigParser(interpolation=None)

    try:
        parser.read(caminho_ini, encoding="utf-8")
    except configparser.Error:
        return None, []

    padrao_instalacao = None

    for secao in parser.sections():
        if secao.startswith("Install"):
            padrao_instalacao = parser.get(secao, "Default", fallback=None)

            if padrao_instalacao:
                break

    perfis = []

    for secao in parser.sections():
        if not secao.startswith("Profile"):
            continue

        caminho = parser.get(secao, "Path", fallback="").strip()

        if not caminho:
            continue

        relativo = parser.get(secao, "IsRelative", fallback="1").strip() != "0"
        perfil = base / caminho if relativo else Path(caminho)
        padrao = parser.get(secao, "Default", fallback="0").strip() in (
            "1",
            "true",
            "True",
        )
        perfis.append((perfil, padrao))

    return padrao_instalacao, perfis


def encontrar_perfil_firefox():
    for base in bases_firefox():
        padrao_instalacao, perfis = ler_profiles_ini(base)

        if padrao_instalacao:
            nome = Path(padrao_instalacao).name

            for perfil, _ in perfis:
                if perfil.name == nome and perfil.is_dir():
                    return perfil

        for perfil, padrao in perfis:
            if padrao and perfil.is_dir():
                return perfil

        for perfil, _ in perfis:
            if "default-release" in perfil.name and perfil.is_dir():
                return perfil

        for perfil, _ in perfis:
            if perfil.is_dir():
                return perfil

    return None


def pasta_dados():
    xdg_data = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
    return base / "olha-a-mensagem"


def perfil_automacao():
    return pasta_dados() / "firefox_profile"


def marcador_perfil():
    return perfil_automacao() / ".olha-mensagem-pronto"


def copiar_dados_firefox(origem, destino):
    destino.mkdir(parents=True, exist_ok=True)

    for nome in [
        "cookies.sqlite",
        "cookies.sqlite-wal",
        "cert9.db",
        "key4.db",
        "pkcs11.txt",
        "permissions.sqlite",
        "prefs.js",
        "handlers.json",
    ]:
        arquivo = origem / nome

        if arquivo.is_file():
            shutil.copy2(arquivo, destino / nome)

    origem_whatsapp = (
        origem / "storage" / "default" / "https+++web.whatsapp.com"
    )

    if origem_whatsapp.is_dir():
        shutil.copytree(
            origem_whatsapp,
            destino / "storage" / "default" / origem_whatsapp.name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "lock",
                ".parentlock",
                "parent.lock",
            ),
        )

    for base in (origem / "storage" / "default").glob(
        "https+++*whatsapp.net*"
    ):
        shutil.copytree(
            base,
            destino / "storage" / "default" / base.name,
            dirs_exist_ok=True,
        )


def preparar_perfil_automacao():
    perfil = perfil_automacao()

    if marcador_perfil().is_file():
        return perfil

    origem = encontrar_perfil_firefox()

    if origem is None:
        print(
            "Perfil padrão do Firefox não encontrado. "
            "Será necessário escanear o QR code uma vez."
        )
    else:
        print(
            "Preparando o perfil de automação do Firefox "
            "(somente na primeira execução)..."
        )

        try:
            copiar_dados_firefox(origem, perfil)
            print("Perfil de automação preparado com os dados do Firefox.")
        except Exception as erro:
            print(
                f"Não foi possível copiar todos os dados do Firefox: {erro}"
            )
            print("Será necessário escanear o QR code uma vez.")

    marcador_perfil().parent.mkdir(parents=True, exist_ok=True)
    marcador_perfil().write_text("ok", encoding="utf-8")

    return perfil


def criar_driver():
    perfil = preparar_perfil_automacao()

    print(f"Usando o perfil de automação do Firefox: {perfil}")

    options = Options()
    options.add_argument("-profile")
    options.add_argument(str(perfil))

    driver = webdriver.Firefox(options=options)
    driver.maximize_window()
    return driver


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def gerar_tempo():
    return random.uniform(1.0, 2.5)


def gerar_tempo_envio():
    return random.uniform(3.5, 4.0)


def gerar_tempo_digitacao():
    return random.uniform(0.028, 0.09)


def normalizar_texto(texto):
    texto = (texto or "").replace("\u00a0", " ")
    return "\n".join(" ".join(linha.split()) for linha in texto.splitlines())


def texto_da_caixa(elemento):
    valores = [
        elemento.get_attribute("innerText"),
        elemento.get_attribute("textContent"),
        elemento.text,
    ]
    for valor in valores:
        if valor and valor.strip():
            return valor
    return ""


# ---------------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------------

def garantir_sessao(driver):
    driver.get("https://web.whatsapp.com")

    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#pane-side"))
        )
        return
    except TimeoutException:
        pass

    print("Se aparecer o QR code, escaneie com o WhatsApp do seu celular.")
    print("O login fica salvo no perfil de automação para as próximas execuções.")

    try:
        WebDriverWait(driver, 180).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#pane-side"))
        )
    except TimeoutException as erro:
        raise RuntimeError("Login no WhatsApp Web não concluído.") from erro


# ---------------------------------------------------------------------------
# Elementos
# ---------------------------------------------------------------------------

def encontrar_elemento(driver, seletores, timeout=15, visivel=True):
    condicoes = []
    for by, seletor in seletores:
        if visivel:
            condicoes.append(EC.visibility_of_element_located((by, seletor)))
        else:
            condicoes.append(EC.presence_of_element_located((by, seletor)))
    return WebDriverWait(driver, timeout).until(EC.any_of(*condicoes))


def clicar(driver, elemento):
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", elemento
        )
        time.sleep(0.3)
        elemento.click()
    except WebDriverException:
        try:
            driver.execute_script(
                "const alvo = arguments[0].closest('button, [role=\"button\"]') "
                "|| arguments[0]; alvo.click();",
                elemento,
            )
        except Exception:
            driver.execute_script("arguments[0].click();", elemento)


def obter_caixa_mensagem(driver):
    seletores = [
        (By.XPATH, "//footer//div[@contenteditable='true' and @role='textbox']"),
        (By.XPATH, "//footer//*[@contenteditable='true']"),
        (By.XPATH, "//div[@contenteditable='true' and @role='textbox']"),
    ]

    ultimo_erro = None
    for by, seletor in seletores:
        try:
            elementos = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((by, seletor))
            )
            visiveis = [
                elemento for elemento in elementos
                if elemento.is_displayed() and elemento.is_enabled()
            ]
            if visiveis:
                return visiveis[-1]
        except TimeoutException as erro:
            ultimo_erro = erro

    raise TimeoutException(
        "Não encontrei a caixa de mensagem da conversa."
    ) from ultimo_erro


def caixa_conversa_visivel(driver):
    for by, seletor in SELETOR_CAIXA_MENSAGEM:
        for elemento in driver.find_elements(by, seletor):
            if elemento.is_displayed() and elemento.is_enabled():
                return elemento
    return None


def numero_sem_whatsapp(driver):
    for by, seletor in SELETOR_NUMERO_SEM_WHATSAPP:
        for elemento in driver.find_elements(by, seletor):
            if elemento.is_displayed():
                return elemento
    return None


def fechar_aviso_numero_invalido(driver):
    try:
        elemento = encontrar_elemento(driver, SELETOR_BOTAO_OK, timeout=5)
        clicar(driver, elemento)
    except Exception:
        pass


def abrir_conversa(driver, telefone, timeout=25):
    driver.get("https://web.whatsapp.com/send?phone=" + telefone)

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda d: numero_sem_whatsapp(d) is not None
            or caixa_conversa_visivel(d) is not None
        )
    except TimeoutException:
        return None

    if numero_sem_whatsapp(driver) is not None:
        fechar_aviso_numero_invalido(driver)
        return False

    return True


def limpar_caixa_mensagem(driver):
    caixa = obter_caixa_mensagem(driver)
    caixa.click()
    caixa.send_keys(Keys.CONTROL, "a")
    caixa.send_keys(Keys.BACKSPACE)
    time.sleep(gerar_tempo())


# ---------------------------------------------------------------------------
# Botão de enviar
# ---------------------------------------------------------------------------

def clicar_botao_enviar(driver):
    """
    Clica no botão de enviar da conversa aberta.
    Espera o botão ficar clicável (ele só habilita depois que o texto
    é 'commitado' no editor).
    """
    seletores = [
        (By.CSS_SELECTOR, 'button[data-tab="11"]'),
        (By.CSS_SELECTOR, 'button[aria-label="Enviar"]'),
        (By.CSS_SELECTOR, 'button[aria-label="Enviar mensagem"]'),
        (By.CSS_SELECTOR, 'button[aria-label="Send"]'),
        (
            By.XPATH,
            "//button[.//svg/title[contains(text(), 'send-filled') or contains(text(), 'send')]]",
        ),
    ]

    for by, seletor in seletores:
        try:
            botao = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((by, seletor))
            )
        except TimeoutException:
            continue

        try:
            if botao.is_displayed() and botao.is_enabled():
                try:
                    botao.click()
                    print("Botão de enviar clicado (Selenium).")
                    return True
                except Exception:
                    driver.execute_script("arguments[0].click();", botao)
                    print("Botão de enviar clicado (JS).")
                    return True
        except Exception:
            continue

    # fallback JS puro
    try:
        clicou = driver.execute_script(
            """
            const btn = document.querySelector('button[data-tab="11"]')
                     || document.querySelector('button[aria-label="Enviar"]')
                     || document.querySelector('button[aria-label="Send"]')
                     || document.querySelector('button[aria-label="Enviar mensagem"]');
            if (btn) { btn.click(); return true; }
            return false;
            """
        )
        if clicou:
            print("Botão de enviar clicado (JS fallback).")
            return True
    except Exception as e:
        print(f"Falha no clique JS: {e}")

    print("Não encontrei botão de enviar clicável.")
    return False


def esperar_botao_enviar_preview(driver, timeout=30):
    """
    Espera o botão de enviar da pré-visualização de imagem/mídia.
    Aceita tanto 'Enviar N item(ns) selecionado(s)' quanto 'Enviar'.
    """
    seletores = [
        (By.CSS_SELECTOR, 'button[aria-label^="Enviar"]'),
        (By.CSS_SELECTOR, 'button[aria-label^="Send"]'),
        (By.CSS_SELECTOR, 'div[role="button"][aria-label^="Enviar"]'),
        (By.CSS_SELECTOR, 'div[role="button"][aria-label^="Send"]'),
        (By.XPATH, "//button[.//svg/title[contains(text(), 'send-filled')]]"),
    ]

    def _botao_visivel(d):
        for by, seletor in seletores:
            for el in d.find_elements(by, seletor):
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        return False

    return WebDriverWait(driver, timeout, poll_frequency=0.5).until(_botao_visivel)


# ---------------------------------------------------------------------------
# Envio de mensagem
# ---------------------------------------------------------------------------

def digitar_mensagem(driver, mensagem):
    limpar_caixa_mensagem(driver)

    mensagem = str(mensagem).strip()

    if not mensagem:
        raise ValueError("A mensagem está vazia.")

    caixa = obter_caixa_mensagem(driver)
    caixa.click()

    for letra in mensagem:
        if letra == "\n":
            caixa.send_keys(Keys.SHIFT, Keys.ENTER)
        else:
            caixa.send_keys(letra)
        time.sleep(gerar_tempo_digitacao())


# ---------------------------------------------------------------------------
# Fluxo principal de envio em massa
# ---------------------------------------------------------------------------

def high(mensagem, clientes, mandarFoto, mandarBoasVindas):
    driver = None
    lista_clientes_contatados = []
    lista_clientes_fora_wpp = []

    try:
        driver = criar_driver()
        garantir_sessao(driver)

        for cliente in clientes:
            if len(cliente) < 2:
                continue

            nome = str(cliente[0]).strip()
            telefone = "".join(ch for ch in str(cliente[1]) if ch.isdigit())

            if not telefone:
                print("Linha ignorada: telefone vazio ou inválido.")
                continue

            print(f"\nAbrindo conversa com {nome} -> {telefone}")

            try:
                status = abrir_conversa(driver, telefone)
                time.sleep(gerar_tempo())

                if status is False:
                    print(
                        f"O número {telefone} não está no WhatsApp. Pulando..."
                    )
                    lista_clientes_fora_wpp.append(cliente)
                    time.sleep(gerar_tempo())
                    continue

                if status is None:
                    print(
                        f"Não foi possível confirmar se {telefone} está no "
                        "WhatsApp. Pulando..."
                    )
                    lista_clientes_fora_wpp.append(cliente)
                    time.sleep(gerar_tempo())
                    continue

                time.sleep(gerar_tempo())

                try:
                    caixa = obter_caixa_mensagem(driver)
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", caixa
                    )
                    time.sleep(gerar_tempo())
                    try:
                        caixa.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", caixa)
                    time.sleep(gerar_tempo())
                except Exception:
                    pass

                limpar_caixa_mensagem(driver)

                if mandarFoto:
                    time.sleep(gerar_tempo())
                    try:
                        caixa = obter_caixa_mensagem(driver)
                        caixa.send_keys(Keys.CONTROL, "v")
                    except Exception as erro:
                        print(f"Falha ao colar imagem: {erro}")

                    try:
                        botao_enviar_preview = esperar_botao_enviar_preview(
                            driver, timeout=30
                        )
                        clicar(driver, botao_enviar_preview)
                        print("Imagem enviada.")
                    except TimeoutException:
                        print(
                            "Não encontrei o botão de enviar a imagem. Pulando foto."
                        )
                    time.sleep(gerar_tempo())

                if nome and mandarBoasVindas:
                    primeira_msg = f"Olá, {nome}! Tudo bem?"
                    digitar_mensagem(driver, primeira_msg)
                    time.sleep(gerar_tempo())
                    caixa.send_keys(Keys.ENTER)
                    print("Saudações enviadas.")
                    

                digitar_mensagem(driver, mensagem)
                time.sleep(gerar_tempo())
                caixa.send_keys(Keys.ENTER)
                print("Mensagem enviada.")


                print(f"Mensagens enviadas para {telefone}.")
                lista_clientes_contatados.append(cliente)

            except Exception as erro:
                print(f"Erro ao processar {telefone}: {erro}")
                print(
                    "Confira a conversa no WhatsApp Web antes de executar novamente."
                )

            time.sleep(gerar_tempo())

    finally:
        print("=========RESUMO=========")
        print("CLIENTES CONTATADOS: ")
        print(lista_clientes_contatados)
        print("\nCLIENTES FORA DO WHATSAPP: ")
        print(lista_clientes_fora_wpp)

        faltantes = [
            cliente for cliente in clientes
            if cliente not in lista_clientes_contatados
        ]

        print("\nCLIENTES A CONTATAR (clientes - contatados): ")
        print(faltantes)

        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

        try:
            input("Aperte ENTER p/ fechar...")
        except EOFError:
            pass

    return {
        "contatados": lista_clientes_contatados,
        "fora_wpp": lista_clientes_fora_wpp,
    }


def abrir_whats():
    driver = criar_driver()

    try:
        garantir_sessao(driver)
        print("\nAbrindo Whatsapp")
        try:
            driver.get("https://web.whatsapp.com/")
            input("Aperte ENTER para fechar!")
            print("Apertou!")
        except Exception as erro:
            print(f"Erro: {erro}")
        time.sleep(gerar_tempo())

    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Adicionar contatos
# ---------------------------------------------------------------------------

def adicionar_contatos(lista, lista_contatos_adicionados, lista_contatos_faltantes):
    driver = None

    try:
        driver = criar_driver()
        garantir_sessao(driver)

        for cliente in lista:
            if len(cliente) < 2:
                lista_contatos_faltantes.append(cliente)
                continue

            nome = str(cliente[0]).strip()
            telefone = "".join(ch for ch in str(cliente[1]) if ch.isdigit())

            if not nome or not telefone:
                print("Cliente ignorado: nome ou telefone inválido.")
                lista_contatos_faltantes.append(cliente)
                continue

            print(f"\nAdicionando contato: {nome} -> {telefone}")

            try:
                novo_chat = encontrar_elemento(
                    driver,
                    [
                        (By.CSS_SELECTOR, 'button[aria-label="Nova conversa"]'),
                        (By.CSS_SELECTOR, 'button[aria-label="New chat"]'),
                        (By.XPATH, "//*[contains(@data-icon, 'new-chat')]"),
                    ],
                )

                clicar(driver, novo_chat)
                time.sleep(gerar_tempo())

                novo_contato = encontrar_elemento(
                    driver,
                    [
                        (By.XPATH, "//*[normalize-space()='Novo contato']"),
                        (By.XPATH, "//*[normalize-space()='New contact']"),
                    ],
                )

                clicar(driver, novo_contato)
                time.sleep(gerar_tempo())

                nome_contato = encontrar_elemento(
                    driver,
                    [
                        (By.CSS_SELECTOR, 'div[data-testid="contact-first-name-input"]'),
                        (By.XPATH, "//div[@contenteditable='true' and @aria-label='Nome']"),
                        (By.XPATH, "//div[@contenteditable='true' and @aria-label='First name']"),
                    ],
                )

                telefone_contato = encontrar_elemento(
                    driver,
                    [
                        (By.CSS_SELECTOR, 'input[data-testid="phone-number-input"]'),
                        (By.CSS_SELECTOR, 'input[aria-label="Número de telefone"]'),
                        (By.CSS_SELECTOR, 'input[aria-label="Phone number"]'),
                    ],
                )

                nome_contato.click()
                nome_contato.send_keys("\ue009", "a")
                nome_contato.send_keys(nome)

                time.sleep(1)

                nome_preenchido = nome_contato.get_attribute("textContent").strip()

                if nome_preenchido != nome:
                    nome_contato.click()
                    nome_contato.send_keys("\ue009", "a")
                    nome_contato.send_keys(nome)
                    time.sleep(1)

                if nome_contato.get_attribute("textContent").strip() != nome:
                    raise RuntimeError("O nome não foi preenchido corretamente.")

                if telefone.startswith("55"):
                    telefone = telefone[2:]

                telefone_contato.click()
                telefone_contato.send_keys(telefone)

                time.sleep(gerar_tempo())

                salvar = encontrar_elemento(
                    driver,
                    [
                        (By.CSS_SELECTOR, 'div[data-testid="save-contact-btn"]'),
                        (By.CSS_SELECTOR, '[aria-label="Salvar contato"]'),
                        (By.CSS_SELECTOR, '[data-testid="save-contact-btn"]'),
                        (
                            By.XPATH,
                            "//*[@role='button' and (@aria-label='Salvar contato' or @aria-label='Save contact')]",
                        ),
                    ],
                )

                clicar(driver, salvar)
                time.sleep(gerar_tempo())

                lista_contatos_adicionados.append(cliente)
                print(f"Contato {nome} adicionado.")

            except Exception as erro:
                print(f"Erro ao adicionar {nome}: {erro}")
                lista_contatos_faltantes.append(cliente)

            time.sleep(gerar_tempo())

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

        try:
            input("Aperte ENTER p/ fechar...")
        except EOFError:
            pass

    print("\n========== RESUMO ==========")
    print(f"Contatos adicionados: {len(lista_contatos_adicionados)}")
    print(f"Contatos faltantes: {len(lista_contatos_faltantes)}")
    print("============================")