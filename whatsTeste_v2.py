import configparser
import os
import random
import shutil
import tempfile
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
    return random.uniform(0.025, 0.075)


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
    """Tenta clique normal após rolar o elemento; usa clique JS como fallback."""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            elemento,
        )
        WebDriverWait(driver, 5).until(
            lambda _driver: elemento.is_displayed() and elemento.is_enabled()
        )
        elemento.click()
        return
    except WebDriverException:
        # Um aviso ou painel pode cobrir o elemento e interceptar o clique.
        # O fallback evita travar o fluxo, mas não confirma que a ação ocorreu.
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


def normalizar_telefone_br(telefone):
    """Normaliza números brasileiros para o formato internacional do WhatsApp."""
    telefone = "".join(caractere for caractere in str(telefone or "") if caractere.isdigit())
    # Alguns CSVs já incluem o código do país.
    if telefone.startswith("55") and len(telefone) in (12, 13):
        return telefone
    # DDD + número fixo/celular brasileiro, sem código do país.
    if len(telefone) in (10, 11):
        return "55" + telefone
    # Não altera números internacionais ou formatos inesperados.
    return telefone


def abrir_conversa(driver, telefone, timeout=25):
    telefone = normalizar_telefone_br(telefone)
    if len(telefone) < 10:
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
    clicar(driver, caixa)
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
    clicar(driver, caixa)
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


def _elemento_visivel(elemento):
    try:
        return elemento.is_displayed() and elemento.is_enabled()
    except WebDriverException:
        return False


def _caminho_temporario_arquivo(arquivo):
    """Copia a imagem para um caminho simples, sem acentos ou espaços."""
    destino_dir = Path(tempfile.gettempdir()) / "olha-a-mensagem"
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / f"foto_para_envio{arquivo.suffix.lower()}"
        if arquivo.resolve() != destino.resolve():
            shutil.copy2(arquivo, destino)
        return destino
    except OSError:
        return arquivo


def _preparar_captura_input(driver):
    """Intercepta o clique do input de arquivo para o WhatsApp não abrir o seletor nativo.

    Guarda uma referência ao input escolhido pelo próprio WhatsApp e o marca no DOM
    para que o Python consiga encontrá-lo depois sem precisar devolver o elemento
    pelo execute_script (evita falhas de serialização do Marionette).
    """
    driver.execute_script(
        r"""
        document.querySelectorAll('[data-olha-input-arquivo]').forEach(function (e) {
            e.removeAttribute('data-olha-input-arquivo');
        });
        window.__olhaMensagemUltimoInputArquivo = null;

        if (!window.__olhaMensagemClickOriginal) {
            window.__olhaMensagemClickOriginal = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this.type === 'file') {
                    try { this.setAttribute('data-olha-input-arquivo', '1'); } catch (e) {}
                    window.__olhaMensagemUltimoInputArquivo = this;
                    return;
                }
                return window.__olhaMensagemClickOriginal.apply(this, arguments);
            };
        }

        if (HTMLInputElement.prototype.showPicker && !window.__olhaMensagemShowPickerOriginal) {
            window.__olhaMensagemShowPickerOriginal = HTMLInputElement.prototype.showPicker;
            HTMLInputElement.prototype.showPicker = function () {
                if (this.type === 'file') {
                    try { this.setAttribute('data-olha-input-arquivo', '1'); } catch (e) {}
                    window.__olhaMensagemUltimoInputArquivo = this;
                    return;
                }
                return window.__olhaMensagemShowPickerOriginal.apply(this, arguments);
            };
        }
        """
    )


def _restaurar_seletor_arquivo(driver):
    """Devolve o comportamento normal do clique/picker de inputs de arquivo."""
    try:
        driver.execute_script(
            r"""
            if (window.__olhaMensagemClickOriginal) {
                HTMLInputElement.prototype.click = window.__olhaMensagemClickOriginal;
                window.__olhaMensagemClickOriginal = null;
            }
            if (window.__olhaMensagemShowPickerOriginal) {
                HTMLInputElement.prototype.showPicker = window.__olhaMensagemShowPickerOriginal;
                window.__olhaMensagemShowPickerOriginal = null;
            }
            window.__olhaMensagemUltimoInputArquivo = null;
            """
        )
    except WebDriverException:
        pass


def _limpar_marcadores_input(driver):
    try:
        driver.execute_script(
            r"""
            document.querySelectorAll('input[type="file"]').forEach(function (e) {
                e.removeAttribute('data-olha-antigo');
                e.removeAttribute('data-olha-input-arquivo');
            });
            """
        )
    except WebDriverException:
        pass


def _marcar_inputs_arquivo(driver):
    """Marca todos os inputs de arquivo existentes antes de abrir a opção de fotos."""
    try:
        driver.execute_script(
            r"""
            document.querySelectorAll('input[type="file"]').forEach(function (e) {
                e.removeAttribute('data-olha-antigo');
                e.setAttribute('data-olha-antigo', '1');
            });
            """
        )
    except WebDriverException:
        pass


def _input_capturado(driver):
    """Retorna o input marcado quando o WhatsApp tentou abrir seu seletor."""
    try:
        elementos = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"][data-olha-input-arquivo="1"]')
    except WebDriverException:
        return None
    return elementos[-1] if elementos else None


def _novo_input_arquivo(driver):
    """Retorna um input de arquivo criado depois de abrir a opção de fotos."""
    try:
        elementos = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]:not([data-olha-antigo])')
    except WebDriverException:
        return None
    return elementos[0] if elementos else None


def _input_com_video(driver):
    """Input de fotos/vídeos: o de figurinha aceita apenas image/*, este aceita vídeo."""
    try:
        elementos = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    except WebDriverException:
        return None
    for elemento in elementos:
        try:
            accept = (elemento.get_attribute("accept") or "").replace(" ", "").lower()
        except WebDriverException:
            continue
        if "video" in accept:
            return elemento
    return None


def _aguardar_input_midia(driver, timeout=8):
    fim = time.time() + timeout
    while time.time() < fim:
        input_midia = _input_capturado(driver)
        if input_midia is None:
            input_midia = _novo_input_arquivo(driver)
        if input_midia is None:
            input_midia = _input_com_video(driver)
        if input_midia is not None:
            return input_midia
        time.sleep(0.25)
    return None


def _marcar_opcao_fotos_videos(driver):
    """Marca o item 'Fotos e vídeos' do menu Anexar usando busca por texto no JS."""
    driver.execute_script(
        r"""
        (function () {
            document.querySelectorAll('[data-olha-fotos-alvo]').forEach(function (e) {
                e.removeAttribute('data-olha-fotos-alvo');
            });

            const normalizar = function (texto) {
                return (texto || '')
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\s+/g, ' ')
                    .trim();
            };

            const itens = Array.from(document.querySelectorAll(
                '[role="button"], [role="menuitem"], button'
            ));
            let melhor = null;
            let melhorTexto = '';

            for (const item of itens) {
                const estilo = window.getComputedStyle(item);
                const caixa = item.getBoundingClientRect();
                if (estilo.display === 'none' || estilo.visibility === 'hidden' ||
                    caixa.width === 0 || caixa.height === 0) {
                    continue;
                }

                const texto = normalizar(item.innerText || item.textContent || '');
                if (!texto || texto.length > 80) continue;
                if (!/(fotos?|photos?)/.test(texto)) continue;
                if (!/videos?/.test(texto)) continue;

                if (melhor === null || texto.length < melhorTexto.length) {
                    melhor = item;
                    melhorTexto = texto;
                }
            }

            if (melhor) {
                melhor.setAttribute('data-olha-fotos-alvo', '1');
                return true;
            }
            return false;
        })();
        """
    )
    return bool(driver.find_elements(By.CSS_SELECTOR, '[data-olha-fotos-alvo="1"]'))


def abrir_opcao_fotos_videos(driver, timeout=10):
    """Abre a opção Fotos e vídeos do menu Anexar.

    O clique é interceptado para não abrir a janela nativa de arquivos. O input
    escolhido pelo WhatsApp fica marcado no DOM e é usado no upload.
    """
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            encontrou = _marcar_opcao_fotos_videos(driver)
        except WebDriverException:
            encontrou = False

        if encontrou:
            elementos = driver.find_elements(By.CSS_SELECTOR, '[data-olha-fotos-alvo="1"]')
            if elementos:
                try:
                    clicar(driver, elementos[0])
                    return True
                except WebDriverException:
                    pass
        time.sleep(0.4)
    return False


def _marcar_botao_enviar_previa(driver):
    """Marca o botão Enviar da prévia de mídia, ignorando o botão do rodapé do chat."""
    driver.execute_script(
        r"""
        (function () {
            document.querySelectorAll('[data-olha-enviar]').forEach(function (e) {
                e.removeAttribute('data-olha-enviar');
            });

            const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
            const comPrevia = dialogs.filter(function (d) {
                return d.querySelector('img[src^="blob:"], video[src^="blob:"], canvas');
            });
            const escopos = comPrevia.length ? comPrevia : (dialogs.length ? dialogs : [document]);

            for (const escopo of escopos) {
                for (const botao of escopo.querySelectorAll('[role="button"], button')) {
                    if (botao.closest('footer')) continue;

                    const rotulo = (botao.getAttribute('aria-label') || '').toLowerCase();
                    const icone = botao.querySelector(
                        '[data-icon="send"], [data-icon="send-filled"], ' +
                        '[data-icon="send-refreshed"], [data-testid="send"]'
                    );
                    const selecionado = rotulo.indexOf('selecionado') !== -1 ||
                        rotulo.indexOf('selected') !== -1;

                    if (!(rotulo.indexOf('enviar') !== -1 || rotulo.indexOf('send') !== -1 ||
                          icone || selecionado)) {
                        continue;
                    }

                    const caixa = botao.getBoundingClientRect();
                    if (caixa.width > 0 && caixa.height > 0) {
                        botao.setAttribute('data-olha-enviar', '1');
                        return true;
                    }
                }
            }
            return false;
        })();
        """
    )
    return bool(driver.find_elements(By.CSS_SELECTOR, '[data-olha-enviar="1"]'))


def _botao_enviar_midia_visivel(driver):
    """Retorna o botão de envio da prévia, ignorando o botão do rodapé do chat."""
    try:
        if _marcar_botao_enviar_previa(driver):
            for elemento in driver.find_elements(By.CSS_SELECTOR, '[data-olha-enviar="1"]'):
                if _elemento_visivel(elemento):
                    return elemento
    except WebDriverException:
        pass

    seletores = [
        (By.CSS_SELECTOR, '[role="button"][aria-label*="selecionado"]'),
        (By.CSS_SELECTOR, '[role="button"][aria-label*="selected"]'),
        (By.CSS_SELECTOR, 'div[role="dialog"] [data-testid="send"]'),
        (By.CSS_SELECTOR, 'div[role="dialog"] [aria-label*="Enviar"]'),
        (By.CSS_SELECTOR, 'div[role="dialog"] [aria-label*="Send"]'),
        (By.CSS_SELECTOR, '[data-testid="send"]'),
        (By.CSS_SELECTOR, '[data-icon="send"]'),
        (By.XPATH, '//*[@role="button" and (contains(@aria-label, "Enviar") or contains(@aria-label, "Send"))]'),
    ]
    for by, seletor in seletores:
        for elemento in driver.find_elements(by, seletor):
            if not _elemento_visivel(elemento):
                continue
            try:
                if elemento.find_elements(By.XPATH, "ancestor::footer"):
                    continue
            except WebDriverException:
                continue
            return elemento
    return None


def _fechar_previa_midia(driver):
    """Fecha uma prévia de mídia que tenha ficado aberta de uma tentativa anterior."""
    try:
        driver.execute_script(
            r"""
            (function () {
                const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'))
                    .filter(function (d) {
                        return d.querySelector('img[src^="blob:"], video[src^="blob:"], canvas');
                    });
                for (const dialog of dialogs) {
                    for (const botao of dialog.querySelectorAll('[role="button"], button')) {
                        const rotulo = (botao.getAttribute('aria-label') || '').toLowerCase();
                        const icone = botao.querySelector('[data-icon="x"], [data-icon="close"]');
                        if (icone || rotulo.indexOf('fechar') !== -1 || rotulo.indexOf('cancelar') !== -1 ||
                            rotulo.indexOf('close') !== -1 || rotulo.indexOf('cancel') !== -1) {
                            botao.setAttribute('data-olha-fechar-previa', '1');
                            return true;
                        }
                    }
                }
                return false;
            })();
            """
        )
        elementos = driver.find_elements(By.CSS_SELECTOR, '[data-olha-fechar-previa="1"]')
        if elementos:
            clicar(driver, elementos[0])
            time.sleep(0.6)
        driver.execute_script(
            "document.querySelectorAll('[data-olha-fechar-previa]')"
            ".forEach(function (e) { e.removeAttribute('data-olha-fechar-previa'); });"
        )
    except WebDriverException:
        pass


def localizar_botao_enviar_midia(driver, timeout=25):
    fim = time.time() + timeout
    while time.time() < fim:
        botao = _botao_enviar_midia_visivel(driver)
        if botao is not None:
            return botao
        time.sleep(0.4)
    raise TimeoutException(
        "A prévia da foto não abriu ou o botão de envio da mídia não apareceu."
    )


def _anexar_arquivo(driver, arquivo_envio):
    """Seleciona a opção Fotos e vídeos e envia o arquivo ao input de mídia."""
    botao_anexar = encontrar_elemento(driver, [
        (By.CSS_SELECTOR, 'button[aria-label="Anexar"]'),
        (By.CSS_SELECTOR, 'button[aria-label="Attach"]'),
        (By.CSS_SELECTOR, 'span[data-icon="plus-rounded"]'),
        (By.CSS_SELECTOR, 'span[data-icon="plus"]'),
        (By.CSS_SELECTOR, 'span[data-icon="attach-menu-plus"]'),
        (By.XPATH, '//button[contains(@aria-label, "Anexar") or contains(@aria-label, "Attach")]'),
    ], timeout=8)
    clicar(driver, botao_anexar)
    time.sleep(gerar_tempo())

    print("Menu Anexar aberto. Selecionando Fotos e vídeos...")

    _marcar_inputs_arquivo(driver)
    _preparar_captura_input(driver)
    try:
        if not abrir_opcao_fotos_videos(driver):
            raise TimeoutException(
                "Não encontrei a opção Fotos e vídeos no menu Anexar do WhatsApp."
            )
        input_midia = _aguardar_input_midia(driver, timeout=8)
    finally:
        _restaurar_seletor_arquivo(driver)

    if input_midia is None:
        _limpar_marcadores_input(driver)
        raise TimeoutException(
            "Não encontrei o seletor de fotos/vídeos do WhatsApp. "
            "Abra Anexar > Fotos e vídeos manualmente e tente novamente."
        )

    try:
        accept = input_midia.get_attribute("accept") or ""
    except WebDriverException:
        accept = ""
    print(f"Input de fotos encontrado (accept={accept!r}). Anexando a imagem...")

    try:
        driver.execute_script("arguments[0].value = '';", input_midia)
    except WebDriverException:
        pass

    try:
        try:
            input_midia.send_keys(str(arquivo_envio))
        except WebDriverException:
            # O WhatsApp pode recriar o input logo após o clique; busca outra vez.
            input_midia = (
                _input_capturado(driver)
                or _novo_input_arquivo(driver)
                or _input_com_video(driver)
            )
            if input_midia is None:
                raise
            try:
                driver.execute_script("arguments[0].value = '';", input_midia)
            except WebDriverException:
                pass
            input_midia.send_keys(str(arquivo_envio))
    finally:
        _limpar_marcadores_input(driver)

    # Pausa para o WhatsApp concluir o carregamento e abrir a prévia da foto.
    time.sleep(gerar_tempo())


def enviar_foto_como_midia(driver, caminho_foto, tentativas=2):
    """Anexa uma imagem pelo seletor de Fotos e vídeos do WhatsApp Web."""
    arquivo = Path(caminho_foto).expanduser().resolve()
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo de imagem não encontrado: {arquivo}")
    if arquivo.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Formato de imagem não suportado. Use PNG, JPG, JPEG ou WEBP.")

    # Caminho sem acentos/espaços evita falhas de upload em alguns drivers.
    arquivo_envio = _caminho_temporario_arquivo(arquivo)

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            if tentativa > 1:
                print(f"Tentando anexar a foto novamente ({tentativa}/{tentativas})...")
            _fechar_previa_midia(driver)
            _anexar_arquivo(driver, arquivo_envio)

            botao_enviar = localizar_botao_enviar_midia(driver)
            clicar(driver, botao_enviar)
            time.sleep(gerar_tempo_envio())

            # Confirma que a prévia fechou, indicando que a foto saiu como mídia.
            fim = time.time() + 20
            while time.time() < fim and _botao_enviar_midia_visivel(driver) is not None:
                time.sleep(0.4)
            if _botao_enviar_midia_visivel(driver) is not None:
                raise RuntimeError(
                    "O envio da foto não foi confirmado. Confira a conversa no WhatsApp Web."
                )
            print(f"Foto enviada como mídia: {arquivo.name}")
            return
        except Exception as erro:
            ultimo_erro = erro
            print(f"Falha ao anexar/enviar a foto (tentativa {tentativa}/{tentativas}): {erro}")
            _restaurar_seletor_arquivo(driver)
            _limpar_marcadores_input(driver)
            _fechar_previa_midia(driver)
            time.sleep(gerar_tempo())

    raise RuntimeError(
        f"Não foi possível anexar/enviar a foto {arquivo.name}: {ultimo_erro}"
    ) from ultimo_erro


def high(mensagem, clientes, mandarFoto=False, mandarBoasVindas=False, driver=None, caminho_foto=None):
    """Envia mensagens aos clientes informados em uma lista de [nome, telefone].

    Para mandarFoto=True, informe caminho_foto. A imagem é anexada pelo seletor
    de fotos/vídeos do WhatsApp Web, para ser enviada como foto e não como figurinha.
    """
    lista_clientes_contatados = []
    lista_clientes_fora_wpp = []
    lista_clientes_com_erro = []
    driver_externo = driver is not None

    try:
        if driver is None:
            driver = criar_driver()
            garantir_sessao(driver)

        for cliente in clientes:
            if not isinstance(cliente, (list, tuple)) or len(cliente) < 2:
                print(f"Linha ignorada por formato inválido: {cliente!r}")
                lista_clientes_com_erro.append(cliente)
                continue

            nome = str(cliente[0] or "").strip()
            telefone = normalizar_telefone_br(cliente[1])
            if len(telefone) < 10:
                print("Linha ignorada: telefone vazio ou inválido.")
                lista_clientes_com_erro.append(cliente)
                continue

            print(f"\nAbrindo conversa com {nome or '(sem nome)'} -> {telefone}")
            try:
                # abrir_conversa() aguarda até a caixa de conversa aparecer.
                status = abrir_conversa(driver, telefone)

                if status is False:
                    print(f"O número {telefone} parece inválido ou não está no WhatsApp. Pulando.")
                    lista_clientes_fora_wpp.append(cliente)
                    continue
                if status is None:
                    print(f"Não foi possível confirmar se {telefone} está no WhatsApp. Pulando.")
                    lista_clientes_com_erro.append(cliente)
                    continue

                # Pausa para a conversa terminar de carregar antes de anexar a foto.
                time.sleep(gerar_tempo())

                if mandarFoto:
                    if not caminho_foto:
                        raise ValueError(
                            "A opção de imagem está ativada, mas nenhum caminho de imagem foi informado."
                        )
                    enviar_foto_como_midia(driver, caminho_foto)
                    # Pausa entre a foto e a mensagem de texto para manter a ordem.
                    time.sleep(gerar_tempo())

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
        if driver is not None:
            _restaurar_seletor_arquivo(driver)
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

        if driver is not None and not driver_externo:
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
    """Abre o WhatsApp Web em uma janela visível e devolve o driver ativo."""
    driver = None
    try:
        driver = criar_driver()
        garantir_sessao(driver)
        driver.get("https://web.whatsapp.com/")
        return driver
    except Exception as erro:
        print(f"Erro ao abrir o WhatsApp Web: {erro}")
        if driver is not None:
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

        for cliente in lista:
            if not isinstance(cliente, (list, tuple)) or len(cliente) < 2:
                lista_contatos_faltantes.append(cliente)
                continue

            nome = str(cliente[0] or "").strip()
            telefone = normalizar_telefone_br(cliente[1])
            if not nome or len(telefone) < 10:
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
        if driver is not None and not driver_externo:
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
