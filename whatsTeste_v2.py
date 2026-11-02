import configparser
import os
import random
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LIMITE_LEGENDA = 1000

SELETOR_CAIXA_MENSAGEM = [
    (By.XPATH, "//footer//div[@contenteditable='true']"),
    (By.XPATH, "//div[@role='textbox' and @contenteditable='true']"),
]

SELETOR_NUMERO_SEM_WHATSAPP = [
    (By.XPATH, "//div[@role='dialog']//*[contains(translate(., 'ÁÉÍÓÚÃÕÇ', 'AEIOUAOC'), 'invalido')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(translate(., 'ÁÉÍÓÚÃÕÇ', 'AEIOUAOC'), 'invalida')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'invalid')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'não está no whatsapp')]"),
    (By.XPATH, "//div[@role='dialog']//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'not on whatsapp')]"),
]

SELETOR_BOTAO_OK = [
    (By.XPATH, "//div[@role='dialog']//button[normalize-space()='OK' or normalize-space()='Ok']"),
    (By.XPATH, "//div[@role='dialog']//*[@role='button'][normalize-space()='OK' or normalize-space()='Ok']"),
    (By.XPATH, "//div[@role='dialog']//button"),
    (By.XPATH, "//div[@role='dialog']//*[@role='button']"),
]


def bases_firefox():
    home = Path.home()
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    candidatos = []

    if xdg_config:
        candidatos.append(Path(xdg_config) / "mozilla" / "firefox")

    candidatos.extend([
        home / ".config" / "mozilla" / "firefox",
        home / ".mozilla" / "firefox",
        home / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",
    ])

    bases, vistos = [], set()
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
    except (configparser.Error, OSError):
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
        padrao = parser.get(secao, "Default", fallback="0").strip().lower() in ("1", "true")
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
    for nome in (
        "cookies.sqlite", "cookies.sqlite-wal", "cert9.db", "key4.db",
        "pkcs11.txt", "permissions.sqlite", "prefs.js", "handlers.json",
    ):
        arquivo = origem / nome
        if arquivo.is_file():
            shutil.copy2(arquivo, destino / nome)

    origem_storage = origem / "storage" / "default"
    if origem_storage.is_dir():
        destino_storage = destino / "storage" / "default"
        destino_storage.mkdir(parents=True, exist_ok=True)
        for padrao in ("https+++web.whatsapp.com*", "https+++whatsapp.net*"):
            for pasta in origem_storage.glob(padrao):
                if pasta.is_dir():
                    shutil.copytree(
                        pasta,
                        destino_storage / pasta.name,
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("lock", ".parentlock", "parent.lock"),
                    )


def preparar_perfil_automacao():
    perfil = perfil_automacao()
    marcador = marcador_perfil()
    if marcador.is_file():
        perfil.mkdir(parents=True, exist_ok=True)
        return perfil

    origem = encontrar_perfil_firefox()
    if origem is None:
        print("Perfil padrão do Firefox não encontrado. Será necessário ler o QR code.")
    else:
        print("Preparando o perfil de automação do Firefox (primeira execução)...")
        try:
            copiar_dados_firefox(origem, perfil)
            print("Dados do perfil copiados. Talvez seja necessário autenticar pelo QR code.")
        except (OSError, shutil.Error) as erro:
            print(f"Não foi possível copiar todos os dados do Firefox: {erro}")
            print("Será necessário autenticar pelo QR code.")

    marcador.parent.mkdir(parents=True, exist_ok=True)
    marcador.write_text("ok", encoding="utf-8")
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


def gerar_tempo():
    return random.uniform(1.0, 2.5)


def gerar_tempo_envio():
    return random.uniform(3.5, 4.0)


def gerar_tempo_digitacao():
<<<<<<< HEAD
    return random.uniform(0.028, 0.09)
=======
    return random.uniform(0.025, 0.075)
>>>>>>> 4eba4f7 (fita)


def garantir_sessao(driver):
    driver.get("https://web.whatsapp.com/")
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#pane-side"))
        )
        return
    except TimeoutException:
        pass

    print("Se aparecer o QR code, escaneie com o WhatsApp do celular.")
    print("Aguarde o carregamento da lista de conversas.")
    try:
        WebDriverWait(driver, 180).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#pane-side"))
        )
    except TimeoutException as erro:
        raise RuntimeError("Login no WhatsApp Web não concluído dentro do prazo.") from erro


def clicar(driver, elemento):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
        time.sleep(0.2)
        elemento.click()
    except WebDriverException:
        try:
            driver.execute_script(
                "const alvo = arguments[0].closest('button, [role=\"button\"]') || arguments[0]; alvo.click();",
                elemento,
            )
        except WebDriverException:
            driver.execute_script("arguments[0].click();", elemento)


def obter_caixa_mensagem(driver, timeout=20):
    seletores = [
        (By.XPATH, "//footer//div[@contenteditable='true' and @role='textbox']"),
        (By.XPATH, "//footer//*[@contenteditable='true']"),
        (By.XPATH, "//div[@contenteditable='true' and @role='textbox']"),
    ]
    fim = time.time() + timeout
    while time.time() < fim:
        for by, seletor in seletores:
            for elemento in driver.find_elements(by, seletor):
                try:
                    if elemento.is_displayed() and elemento.is_enabled():
                        return elemento
                except WebDriverException:
                    continue
        time.sleep(0.25)
    raise TimeoutException("Não encontrei a caixa de mensagem visível da conversa.")


def caixa_conversa_visivel(driver):
    for by, seletor in SELETOR_CAIXA_MENSAGEM:
        for elemento in driver.find_elements(by, seletor):
            try:
                if elemento.is_displayed() and elemento.is_enabled():
                    return elemento
            except WebDriverException:
                continue
    return None


def numero_sem_whatsapp(driver):
    for by, seletor in SELETOR_NUMERO_SEM_WHATSAPP:
        for elemento in driver.find_elements(by, seletor):
            try:
                if elemento.is_displayed():
                    return elemento
            except WebDriverException:
                continue
    return None


def encontrar_elemento(driver, seletores, timeout=15, visivel=True):
    condicoes = []
    for by, seletor in seletores:
        condicoes.append(
            EC.visibility_of_element_located((by, seletor)) if visivel
            else EC.presence_of_element_located((by, seletor))
        )
    return WebDriverWait(driver, timeout).until(EC.any_of(*condicoes))


def fechar_aviso_numero_invalido(driver):
    try:
        clicar(driver, encontrar_elemento(driver, SELETOR_BOTAO_OK, timeout=4))
    except (TimeoutException, WebDriverException):
        pass


def abrir_conversa(driver, telefone, timeout=25):
    telefone = "".join(caractere for caractere in str(telefone) if caractere.isdigit())
    if not telefone:
        return False

    driver.get(f"https://web.whatsapp.com/send?phone={quote(telefone)}")
    try:
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda d: numero_sem_whatsapp(d) is not None or caixa_conversa_visivel(d) is not None
        )
    except TimeoutException:
        return None

    if numero_sem_whatsapp(driver) is not None:
        fechar_aviso_numero_invalido(driver)
        return False
    return True


def normalizar_texto(texto):
    texto = (texto or "").replace("\u00a0", " ").replace("\r", "")
    return " ".join(texto.split())


def texto_da_caixa(elemento):
    for valor in (elemento.get_attribute("innerText"), elemento.get_attribute("textContent"), elemento.text):
        if valor and valor.strip():
            return valor
    return ""


def limpar_caixa_mensagem(driver):
    caixa = obter_caixa_mensagem(driver)
    caixa.click()
    caixa.send_keys(Keys.CONTROL, "a")
    caixa.send_keys(Keys.BACKSPACE)
    time.sleep(gerar_tempo())


def digitar_mensagem(driver, mensagem):
    mensagem = str(mensagem or "").strip()
    if not mensagem:
        raise ValueError("A mensagem está vazia.")
    if len(mensagem) > LIMITE_LEGENDA:
        raise ValueError(f"A mensagem excede o limite configurado de {LIMITE_LEGENDA} caracteres.")

    limpar_caixa_mensagem(driver)
    caixa = obter_caixa_mensagem(driver)
    caixa.click()
    for caractere in mensagem:
        if caractere == "\n":
            caixa.send_keys(Keys.SHIFT, Keys.ENTER)
        else:
            caixa.send_keys(caractere)
        time.sleep(gerar_tempo_digitacao())

    esperado = normalizar_texto(mensagem)
    try:
        WebDriverWait(driver, 10).until(
            lambda d: normalizar_texto(texto_da_caixa(obter_caixa_mensagem(d, timeout=3))) == esperado
        )
    except TimeoutException as erro:
        raise RuntimeError("O texto digitado está incompleto. A mensagem não foi enviada.") from erro

    obter_caixa_mensagem(driver).send_keys(Keys.ENTER)
    time.sleep(gerar_tempo_envio())
    print("Mensagem enviada.")


<<<<<<< HEAD
def high(mensagem, clientes, mandarFoto=False, mandarBoasVindas=False):
=======
def high(mensagem, clientes, mandarFoto=False, mandarBoasVindas=False, driver=None):
>>>>>>> 4eba4f7 (fita)
    """Envia mensagens aos clientes informados em uma lista de [nome, telefone].

    Para mandarFoto=True, a imagem precisa já estar copiada para a área de transferência
    do sistema antes de executar a função. A automação tenta colá-la na conversa.
    """
    lista_clientes_contatados = []
    lista_clientes_fora_wpp = []
    lista_clientes_com_erro = []
<<<<<<< HEAD
    driver = None

    try:
        driver = criar_driver()
        garantir_sessao(driver)
=======
    driver_externo = driver is not None

    try:
        if driver is None:
            driver = criar_driver()
            garantir_sessao(driver)
>>>>>>> 4eba4f7 (fita)

        for cliente in clientes:
            if not isinstance(cliente, (list, tuple)) or len(cliente) < 2:
                print(f"Linha ignorada por formato inválido: {cliente!r}")
                lista_clientes_com_erro.append(cliente)
                continue

            nome = str(cliente[0] or "").strip()
            telefone = "".join(ch for ch in str(cliente[1] or "") if ch.isdigit())
            if not telefone:
                print("Linha ignorada: telefone vazio ou inválido.")
                lista_clientes_com_erro.append(cliente)
                continue

            print(f"\nAbrindo conversa com {nome or '(sem nome)'} -> {telefone}")
            try:
                status = abrir_conversa(driver, telefone)
                time.sleep(gerar_tempo())

                if status is False:
                    print(f"O número {telefone} parece inválido ou não está no WhatsApp. Pulando.")
                    lista_clientes_fora_wpp.append(cliente)
                    continue
                if status is None:
                    print(f"Não foi possível confirmar se {telefone} está no WhatsApp. Pulando.")
                    lista_clientes_com_erro.append(cliente)
                    continue

                if mandarFoto:
                    caixa = obter_caixa_mensagem(driver)
                    caixa.click()
                    caixa.send_keys(Keys.CONTROL, "v")
                    time.sleep(1.5)
                    # Não envia Enter aqui: a imagem pode abrir uma prévia que exige legenda/confirmação.
                    # Se a prévia estiver visível, confirma pelo botão de envio correspondente.
                    try:
                        botao_enviar = encontrar_elemento(driver, [
                            # Botão da prévia de mídia: exemplo real do WhatsApp Web:
                            # aria-label="Enviar 1 item selecionado"
                            (By.CSS_SELECTOR, 'div[role="button"][aria-label^="Enviar"][aria-label*="item selecionado"]'),
                            (By.CSS_SELECTOR, 'div[role="button"][aria-label^="Enviar"][aria-label*="itens selecionados"]'),
                            (By.CSS_SELECTOR, 'div[role="button"][aria-label^="Send"][aria-label*="item selected"]'),
                            (By.CSS_SELECTOR, 'div[role="button"][aria-label^="Send"][aria-label*="items selected"]'),
                            # Seletores alternativos para outras versões/idiomas:
                            (By.CSS_SELECTOR, 'button[aria-label="Enviar"]'),
                            (By.CSS_SELECTOR, 'button[aria-label="Send"]'),
                            (By.CSS_SELECTOR, 'div[role="button"][aria-label="Enviar"]'),
                            (By.CSS_SELECTOR, 'div[role="button"][aria-label="Send"]'),
                        ], timeout=8)
                        clicar(driver, botao_enviar)
                        time.sleep(gerar_tempo_envio())
                        print("Imagem enviada, se a prévia foi reconhecida pelo WhatsApp Web.")
                    except TimeoutException:
                        print("Não encontrei o botão de envio da imagem. Verifique a conversa manualmente.")
                        lista_clientes_com_erro.append(cliente)
                        continue

                if nome and mandarBoasVindas:
                    digitar_mensagem(driver, f"Olá, {nome}! Tudo bem?")
                    time.sleep(gerar_tempo())

                digitar_mensagem(driver, mensagem)
                print(f"Mensagens processadas para {telefone}.")
                lista_clientes_contatados.append(cliente)

            except Exception as erro:
                print(f"Erro ao processar {telefone}: {erro}")
                print("Confira a conversa no WhatsApp Web antes de executar novamente para evitar duplicidade.")
                lista_clientes_com_erro.append(cliente)

            time.sleep(gerar_tempo())

    except Exception as erro:
        print(f"Falha na inicialização da automação: {erro}")

    finally:
        print("\n========= RESUMO =========")
        print(f"Clientes contatados ({len(lista_clientes_contatados)}):")
        print(lista_clientes_contatados)
        print(f"\nClientes fora do WhatsApp ({len(lista_clientes_fora_wpp)}):")
        print(lista_clientes_fora_wpp)
        print(f"\nClientes com erro/não confirmados ({len(lista_clientes_com_erro)}):")
        print(lista_clientes_com_erro)
        contatados_ids = {id(cliente) for cliente in lista_clientes_contatados}
        faltantes = [cliente for cliente in clientes if id(cliente) not in contatados_ids]
        print(f"\nClientes não confirmados como contatados ({len(faltantes)}):")
        print(faltantes)

<<<<<<< HEAD
        if driver is not None:
=======
        if driver is not None and not driver_externo:
>>>>>>> 4eba4f7 (fita)
            try:
                input("Aperte ENTER para fechar o navegador...")
            except (EOFError, KeyboardInterrupt):
                pass
            finally:
                try:
                    driver.quit()
                except WebDriverException:
                    pass


def abrir_whats():
<<<<<<< HEAD
    driver = None
=======
    """Abre o WhatsApp Web em uma janela visível e devolve o driver ativo."""
>>>>>>> 4eba4f7 (fita)
    try:
        driver = criar_driver()
        garantir_sessao(driver)
        driver.get("https://web.whatsapp.com/")
<<<<<<< HEAD
        input("WhatsApp Web aberto. Aperte ENTER para fechar o navegador...")
    except (Exception, KeyboardInterrupt) as erro:
        print(f"Erro ao abrir o WhatsApp Web: {erro}")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


def adicionar_contatos(lista, lista_contatos_adicionados, lista_contatos_faltantes):
    driver = None
    try:
        driver = criar_driver()
        garantir_sessao(driver)
=======
        return driver
    except Exception as erro:
        print(f"Erro ao abrir o WhatsApp Web: {erro}")
        try:
            driver.quit()
        except Exception:
            pass
        return None


def adicionar_contatos(lista, lista_contatos_adicionados, lista_contatos_faltantes, driver=None):
    driver_externo = driver is not None
    try:
        if driver is None:
            driver = criar_driver()
            garantir_sessao(driver)
>>>>>>> 4eba4f7 (fita)

        for cliente in lista:
            if not isinstance(cliente, (list, tuple)) or len(cliente) < 2:
                lista_contatos_faltantes.append(cliente)
                continue

            nome = str(cliente[0] or "").strip()
            telefone = "".join(ch for ch in str(cliente[1] or "") if ch.isdigit())
            if not nome or not telefone:
                print("Cliente ignorado: nome ou telefone inválido.")
                lista_contatos_faltantes.append(cliente)
                continue

            print(f"\nAdicionando contato: {nome} -> {telefone}")
            try:
                novo_chat = encontrar_elemento(driver, [
                    (By.CSS_SELECTOR, 'button[aria-label="Nova conversa"]'),
                    (By.CSS_SELECTOR, 'button[aria-label="New chat"]'),
                    (By.XPATH, "//*[contains(@data-icon, 'new-chat')]/ancestor::*[@role='button' or self::button][1]"),
                ])
                clicar(driver, novo_chat)
                time.sleep(gerar_tempo())

                novo_contato = encontrar_elemento(driver, [
                    (By.XPATH, "//*[normalize-space()='Novo contato']"),
                    (By.XPATH, "//*[normalize-space()='New contact']"),
                ])
                clicar(driver, novo_contato)
                time.sleep(gerar_tempo())

                nome_contato = encontrar_elemento(driver, [
                    (By.CSS_SELECTOR, 'div[data-testid="contact-first-name-input"]'),
                    (By.XPATH, "//div[@contenteditable='true' and (@aria-label='Nome' or @aria-label='First name')]"),
                ])
                telefone_contato = encontrar_elemento(driver, [
                    (By.CSS_SELECTOR, 'input[data-testid="phone-number-input"]'),
                    (By.CSS_SELECTOR, 'input[aria-label="Número de telefone"]'),
                    (By.CSS_SELECTOR, 'input[aria-label="Phone number"]'),
                ])

                nome_contato.click()
                nome_contato.send_keys(Keys.CONTROL, "a")
                nome_contato.send_keys(nome)
                time.sleep(0.3)
                nome_preenchido = (nome_contato.get_attribute("textContent") or "").strip()
                if nome_preenchido != nome:
                    raise RuntimeError("O nome não foi preenchido corretamente.")

                # Mantém o DDI se o campo aceitar número internacional. Se a interface separar
                # país/DDI e número, confira a seleção de país antes de salvar.
                telefone_contato.click()
                telefone_contato.send_keys(Keys.CONTROL, "a")
                telefone_contato.send_keys(telefone)
                time.sleep(gerar_tempo())

                salvar = encontrar_elemento(driver, [
                    (By.CSS_SELECTOR, 'div[data-testid="save-contact-btn"]'),
                    (By.CSS_SELECTOR, '[aria-label="Salvar contato"]'),
                    (By.CSS_SELECTOR, '[data-testid="save-contact-btn"]'),
                    (By.XPATH, "//*[@role='button' and (@aria-label='Salvar contato' or @aria-label='Save contact')]"),
                    (By.XPATH, "//button[normalize-space()='Salvar' or normalize-space()='Save']"),
                ])
                clicar(driver, salvar)
                time.sleep(gerar_tempo())
                lista_contatos_adicionados.append(cliente)
                print(f"Contato {nome} salvo (confirme na interface se necessário).")

            except Exception as erro:
                print(f"Erro ao adicionar {nome}: {erro}")
                lista_contatos_faltantes.append(cliente)
            time.sleep(gerar_tempo())

    except Exception as erro:
        print(f"Falha ao iniciar o cadastro de contatos: {erro}")
    finally:
<<<<<<< HEAD
        if driver is not None:
=======
        if driver is not None and not driver_externo:
>>>>>>> 4eba4f7 (fita)
            try:
                input("Aperte ENTER para fechar o navegador...")
            except (EOFError, KeyboardInterrupt):
                pass
            finally:
                try:
                    driver.quit()
                except WebDriverException:
                    pass

    print("\n========== RESUMO ==========")
    print(f"Contatos adicionados/processados: {len(lista_contatos_adicionados)}")
    print(f"Contatos faltantes: {len(lista_contatos_faltantes)}")
    print("============================")
