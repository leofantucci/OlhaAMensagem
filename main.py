import math
import os
import sys
import csv
import re
import time
import contextlib
import io
import subprocess
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QUrl, QThread, Signal, QSettings
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QStackedWidget, QTextEdit, QFileDialog, QMessageBox,
    QGraphicsOpacityEffect, QCheckBox, QLineEdit, QPlainTextEdit, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea
)
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

BASE = Path(__file__).resolve().parent
AUDIO_PATH = BASE / 'Olha a mensagem.mp3'
HEADSET_PATH = BASE / 'headset_vr_3d.png'


from whatsTeste_v2 import abrir_whats, high, adicionar_contatos

class LogStream(io.TextIOBase):
    def __init__(self, callback): self.callback = callback
    def write(self, text):
        if text and text.strip(): self.callback(text.rstrip())
        return len(text)
    def flush(self): pass

class WhatsWorker(QThread):
    log = Signal(str)
    done = Signal(object, str)
    def __init__(self, action, driver=None, message='', clients=None, photo=False, welcome=False, photo_path=''):
        super().__init__()
        self.action, self.driver, self.message = action, driver, message
        self.clients, self.photo, self.welcome, self.photo_path = clients or [], photo, welcome, photo_path
    def run(self):
        stream = LogStream(self.log.emit)
        result_driver = self.driver
        error = ''
        try:
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                if self.action == 'open':
                    self.log.emit('Abrindo Firefox e carregando WhatsApp Web...')
                    result_driver = abrir_whats()
                    if result_driver is None: raise RuntimeError('Não foi possível abrir o WhatsApp Web.')
                    self.log.emit('WhatsApp Web aberto. Faça login no navegador, se necessário.')
                elif self.action == 'send':
                    if result_driver is None: raise RuntimeError('Abra o WhatsApp Web primeiro.')
                    high(self.message, self.clients, self.photo, self.welcome, driver=result_driver, caminho_foto=self.photo_path)
                elif self.action == 'contacts':
                    if result_driver is None: raise RuntimeError('Abra o WhatsApp Web primeiro.')
                    added, missing = [], []
                    adicionar_contatos(self.clients, added, missing, driver=result_driver)
                    self.log.emit(f'Resumo: {len(added)} contato(s) adicionado(s), {len(missing)} não confirmado(s).')
                elif self.action == 'close':
                    if result_driver is not None: result_driver.quit()
                    result_driver = None
                    self.log.emit('Sessão do navegador encerrada.')
        except Exception as exc:
            error = str(exc)
            self.log.emit(f'ERRO: {error}')
        self.done.emit(result_driver, error)


STYLE = '''
QWidget { background:#080817; color:#e8e8ff; font-family:'Inter','Segoe UI',sans-serif; }
QScrollArea { border:0; background:transparent; }
QCheckBox { spacing:9px; color:#d9d8f5; padding:4px 2px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #6c4c91; border-radius:4px; background:#111126; }
QCheckBox::indicator:checked { background:#ff3fb4; border:1px solid #ff9ade; }
QFrame#sidebar { background:#0b0a1b; border-right:1px solid #53316e; }
QLabel#brand { color:#fff0fc; font-size:21px; font-weight:800; letter-spacing:2px; }
QLabel#subbrand { color:#ff55c8; font-size:10px; letter-spacing:3px; }
QLabel#heading { font-size:27px; font-weight:700; color:#fff0fc; }
QLabel#muted { color:#6e9baa; font-size:12px; }
QFrame#panel { background:#100f24; border:1px solid #49305f; border-radius:14px; }
QPushButton { background:#17152e; color:#f1eaff; border:1px solid #68417f; border-radius:9px; padding:11px 14px; text-align:left; }
QPushButton:hover { background:#292044; border:1px solid #ff4fbe; }
QPushButton#nav { background:transparent; border:1px solid transparent; padding:13px 14px; }
QPushButton#nav:hover, QPushButton#nav[selected="true"] { background:#21152f; border:1px solid #b64caa; }
QPushButton#primary { background:#ff3fb4; color:#18091c; font-weight:800; border:1px solid #ff9ade; }
QPushButton#primary:hover { background:#ff80d0; }
QTextEdit, QPlainTextEdit, QLineEdit { background:#0a0a19; border:1px solid #49305f; border-radius:8px; padding:9px; selection-background-color:#923c92; }
'''

class VisorIntro(QWidget):
    """Full-screen stylized VR visor sequence, painted in real time."""
    def __init__(self, on_finished, parent=None):
        super().__init__(parent)
        self.on_finished = on_finished
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.progress = 0.0
        self.headset_image = QImage(str(HEADSET_PATH)) if HEADSET_PATH.exists() else QImage()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.82)
        if AUDIO_PATH.exists():
            self.player.setSource(QUrl.fromLocalFile(str(AUDIO_PATH)))

    def start(self):
        self.progress = 0.0
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.timer.start(16)
        QTimer.singleShot(280, self.play_audio)

    def play_audio(self):
        # A preferência é persistida pelo QSettings e sobrevive ao fechamento do app.
        settings = QSettings('OlhaAMensagem', 'OlhaAMensagem')
        if settings.value('intro_audio_enabled', True, type=bool) and AUDIO_PATH.exists():
            self.player.setPosition(0)
            self.player.play()

    def advance(self):
        self.progress += 0.012
        self.update()
        if self.progress >= 1.0:
            self.timer.stop()
            self.hide()
            self.on_finished()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        t = min(1.0, self.progress)
        # Background resembles the actual application already open behind the visor.
        p.fillRect(self.rect(), QColor('#030811'))
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, QColor('#071827'))
        grad.setColorAt(0.55, QColor('#04101b'))
        grad.setColorAt(1, QColor('#02050b'))
        p.fillRect(self.rect(), grad)
        # HUD grid and the app silhouette behind the lens.
        p.setPen(QPen(QColor(0, 196, 235, 25), 1))
        for x in range(0, w, 54): p.drawLine(x, 0, x, h)
        for y in range(0, h, 54): p.drawLine(0, y, w, y)
        app = QRectF(w*.20, h*.16, w*.60, h*.68)
        p.setBrush(QColor(5, 17, 29, 230)); p.setPen(QPen(QColor(28, 132, 161, 150), 1.2))
        p.drawRoundedRect(app, 18, 18)
        p.setPen(QColor('#d9f7ff')); p.setFont(QFont('Segoe UI', max(15, int(h*.026)), QFont.Weight.Bold))
        p.drawText(QRectF(app.x()+30, app.y()+28, app.width()-60, 38), Qt.AlignmentFlag.AlignLeft, 'OLHA-A-MENSAGEM')
        p.setPen(QColor('#35dfff')); p.setFont(QFont('Segoe UI', max(8, int(h*.011))))
        p.drawText(QRectF(app.x()+31, app.y()+68, app.width()-60, 22), Qt.AlignmentFlag.AlignLeft, 'INTERFACE DE CONTROLE  /  SISTEMA ONLINE')
        # Cards are intentionally subtle, like the app is visible through the lenses.
        for i, label in enumerate(('EMAIL', 'WHATSAPP', 'LOGS')):
            r = QRectF(app.x()+30+i*(app.width()-75)/3, app.y()+120, (app.width()-95)/3, app.height()*.31)
            p.setBrush(QColor(5, 40, 57, 230)); p.setPen(QPen(QColor(22, 115, 143, 180), 1))
            p.drawRoundedRect(r, 10, 10)
            p.setPen(QColor('#66eaff')); p.setFont(QFont('Segoe UI', max(9, int(h*.014)), QFont.Weight.DemiBold))
            p.drawText(r.adjusted(12, 12, -8, -8), Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft, label)
            p.setPen(QColor(70, 140, 160, 150))
            for j in range(3): p.drawLine(int(r.x()+12), int(r.y()+45+j*17), int(r.right()-14), int(r.y()+45+j*17))
        # Cinematic 3D headset artwork: moves toward the camera and fades as the view enters the lenses.
        if not self.headset_image.isNull() and t < .91:
            approach = min(1.0, t / .76)
            ease = approach * approach * (3.0 - 2.0 * approach)
            image_w = w * (0.42 + 1.58 * ease)
            image_h = image_w * self.headset_image.height() / max(1, self.headset_image.width())
            # Keep the headset centered slightly above the middle, like a first-person visor being put on.
            image_rect = QRectF((w-image_w)/2, h*.46-image_h/2, image_w, image_h)
            image_alpha = 1.0 if t < .57 else max(0.0, 1.0 - (t-.57)/.34)
            p.save()
            p.setOpacity(image_alpha)
            p.drawImage(image_rect, self.headset_image)
            p.restore()
        # The visor moves toward the viewer, then its lens opening expands to fill the screen.
        cx, cy = w*.5, h*.51
        lens_w = w*(.19 + .94*(t**2.1))
        lens_h = h*(.22 + .98*(t**2.1))
        gap = w*.025*(1-t)
        left = QRectF(cx-lens_w-gap/2, cy-lens_h/2, lens_w, lens_h)
        right = QRectF(cx+gap/2, cy-lens_h/2, lens_w, lens_h)
        # dark overlay is cut away around the two lens windows
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 2, 7, int(235*(1-t))))
        p.drawRect(self.rect())
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawRoundedRect(left, lens_h*.22, lens_h*.22)
        p.drawRoundedRect(right, lens_h*.22, lens_h*.22)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # Glossy VR lens rims.
        rim_alpha = int(235*(1-t))
        for r in (left, right):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(14, 26, 36, rim_alpha), max(3, int(h*.018*(1-t)+1))))
            p.drawRoundedRect(r, lens_h*.22, lens_h*.22)
            p.setPen(QPen(QColor(36, 221, 255, int(170*(1-t))), max(1, int(h*.002))))
            p.drawRoundedRect(r.adjusted(5, 5, -5, -5), lens_h*.20, lens_h*.20)
        # Center bridge and outer headset silhouette retract as the camera enters the lens.
        if t < .82:
            a = int(245*(1-t/.82))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(1, 5, 11, a))
            p.drawRoundedRect(QRectF(cx-w*.045, cy-h*.07, w*.09, h*.14), 18, 18)
            p.setPen(QPen(QColor(38, 211, 244, a), 2))
            p.drawLine(QPointF(cx-w*.18, cy-h*.01), QPointF(cx+w*.18, cy-h*.01))
        # Fades to the app at the end of the zoom.
        if t > .84:
            p.fillRect(self.rect(), QColor(2, 8, 14, int(255*(t-.84)/.16)))
        if t < .72:
            p.setPen(QColor(104, 229, 255, int(220*(1-t/.72))))
            p.setFont(QFont('Segoe UI', max(10, int(h*.016)), QFont.Weight.DemiBold))
            p.drawText(QRectF(0, h*.84, w, 35), Qt.AlignmentFlag.AlignCenter, 'INICIALIZANDO INTERFACE NEURAL...')
        p.end()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('OlhaAMensagem', 'OlhaAMensagem')
        self.setWindowTitle('OLHA-A-MENSAGEM.app | JARVIS Interface')
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.build_shell())
        self.intro = VisorIntro(self.finish_intro)
        self.intro_done = False
        QTimer.singleShot(220, self.start_intro)

    def build_shell(self):
        shell = QWidget(); row = QHBoxLayout(shell); row.setContentsMargins(0,0,0,0); row.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(235)
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(18,24,18,20); sl.setSpacing(9)
        brand = QLabel('OLHA-A-MENSAGEM'); brand.setObjectName('brand'); brand.setWordWrap(True)
        sub = QLabel('PERSONAL OUTREACH SYSTEM'); sub.setObjectName('subbrand')
        sl.addWidget(brand); sl.addWidget(sub); sl.addSpacing(28)
        self.nav_buttons=[]
        for idx, name in enumerate(('⌂  Visão geral','✉  E-mail','◉  WhatsApp','≡  Logs')):
            b=QPushButton(name); b.setObjectName('nav'); b.setProperty('selected', idx==0); b.clicked.connect(lambda checked=False, i=idx: self.navigate(i))
            sl.addWidget(b); self.nav_buttons.append(b)
        sl.addStretch(1)
        status=QLabel('● SISTEMA PRONTO\n\nLOCAL • PYTHON\nSESSÃO SEGURA'); status.setObjectName('muted'); sl.addWidget(status)
        content = QWidget(); cl=QVBoxLayout(content); cl.setContentsMargins(28,24,28,24); cl.setSpacing(16)
        top=QHBoxLayout(); title=QLabel('CENTRAL DE OPERAÇÕES'); title.setObjectName('muted'); top.addWidget(title); top.addStretch(1)
        self.clock=QLabel('J.A.R.V.I.S.  /  ONLINE'); self.clock.setStyleSheet('color:#42dfff;font-weight:700;letter-spacing:1px;'); top.addWidget(self.clock); cl.addLayout(top)
        self.stack=QStackedWidget()
        self.log_box=None
        self.stack.addWidget(self.dashboard_page())
        self.stack.addWidget(self.email_page())
        self.stack.addWidget(self.whatsapp_page())
        self.stack.addWidget(self.logs_page())
        cl.addWidget(self.stack,1)
        row.addWidget(sidebar); row.addWidget(content,1)
        return shell

    def panel(self, title, description=''):
        f=QFrame(); f.setObjectName('panel'); l=QVBoxLayout(f); l.setContentsMargins(20,18,20,18); l.setSpacing(9)
        t=QLabel(title); t.setStyleSheet('font-size:16px;font-weight:700;color:#dcfaff;'); l.addWidget(t)
        if description:
            d=QLabel(description); d.setObjectName('muted'); d.setWordWrap(True); l.addWidget(d)
        return f,l

    def dashboard_page(self):
        page=QWidget(); l=QVBoxLayout(page); l.setContentsMargins(0,4,0,0); l.setSpacing(18)
        h=QLabel('Olá. Sistema em espera.'); h.setObjectName('heading'); l.addWidget(h)
        d=QLabel('Escolha um módulo para iniciar uma operação de contato.'); d.setObjectName('muted'); l.addWidget(d)
        cards=QHBoxLayout(); cards.setSpacing(14)
        for title,desc,btn,idx in [('E-MAIL','Envio de campanhas e mensagens','ABRIR MÓDULO',1),('WHATSAPP','Automação com WhatsApp Web','ABRIR MÓDULO',2),('REGISTROS','Acompanhe a atividade da sessão','VER LOGS',3)]:
            f,fl=self.panel(title,desc); fl.addStretch(1); b=QPushButton(btn); b.setObjectName('primary' if idx==1 else ''); b.clicked.connect(lambda checked=False,i=idx:self.navigate(i)); fl.addWidget(b); cards.addWidget(f)
        l.addLayout(cards)
        jarvis_panel, jarvis_layout = self.panel('J.A.R.V.I.S. — BUSCA DE LEADS', 'Inicia o projeto Jarvis usando o iniciar.sh existente e abre a interface no Firefox.')
        jarvis_row = QHBoxLayout()
        self.jarvis_button = QPushButton('INICIAR JARVIS E ABRIR NO FIREFOX')
        self.jarvis_button.setObjectName('primary')
        self.jarvis_button.clicked.connect(self.start_jarvis)
        jarvis_row.addWidget(self.jarvis_button)
        self.jarvis_status = QLabel('Servidor não iniciado por este aplicativo.')
        self.jarvis_status.setObjectName('muted')
        jarvis_row.addWidget(self.jarvis_status, 1)
        jarvis_layout.addLayout(jarvis_row)
        l.addWidget(jarvis_panel)
        settings_panel, settings_layout = self.panel('PREFERÊNCIAS DE INICIALIZAÇÃO', 'As preferências ficam salvas para as próximas sessões.')
        self.intro_audio_check = QCheckBox('Reproduzir áudio na abertura VR')
        self.intro_audio_check.setChecked(self.settings.value('intro_audio_enabled', True, type=bool))
        self.intro_audio_check.setToolTip('Desmarque para manter a animação VR, mas iniciar sem tocar o MP3.')
        self.intro_audio_check.toggled.connect(self.save_intro_audio_setting)
        settings_layout.addWidget(self.intro_audio_check)
        l.addWidget(settings_panel)
        f,fl=self.panel('SEQUÊNCIA DE INICIALIZAÇÃO','Interface carregada. O módulo de WhatsApp é controlado diretamente pela interface.')
        line=QLabel('01  Interface gráfica ativa\n02  Arquivos CSV selecionados pelo usuário\n03  Operações de envio iniciadas sob demanda'); line.setStyleSheet('color:#91b8c7;line-height:1.6;'); fl.addWidget(line); l.addWidget(f); l.addStretch(1)
        return page

    def email_page(self):
        page=QWidget(); l=QVBoxLayout(page); l.setSpacing(16)
        h=QLabel('Módulo de E-mail'); h.setObjectName('heading'); l.addWidget(h)
        f,fl=self.panel('ENVIO DE CAMPANHA','Abra o fluxo de envio existente para escolher a mensagem, o CSV e revisar os destinatários.')
        b=QPushButton('INICIAR FLUXO DE E-MAIL'); b.setObjectName('primary'); b.clicked.connect(lambda:self.launch_backend('email')); fl.addWidget(b); l.addWidget(f)
        f2,fl2=self.panel('OBSERVAÇÃO','A chave RESEND_API_KEY deve estar configurada no arquivo .env. O envio só ocorre quando você confirma as etapas no fluxo.')
        l.addWidget(f2); l.addStretch(1); return page

    def whatsapp_page(self):
        page=QWidget(); outer=QVBoxLayout(page); outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content=QWidget(); l=QVBoxLayout(content); l.setContentsMargins(2,4,8,12); l.setSpacing(14)
        scroll.setWidget(content); outer.addWidget(scroll)
        h=QLabel('Módulo de WhatsApp'); h.setObjectName('heading'); l.addWidget(h)
        f,fl=self.panel('SESSÃO DO WHATSAPP WEB','Abra o navegador uma vez. Depois, selecione os arquivos e controle todas as ações por esta interface.')
        row=QHBoxLayout()
        self.btn_open=QPushButton('ABRIR WHATSAPP WEB'); self.btn_open.setObjectName('primary'); self.btn_open.clicked.connect(lambda:self.run_whats('open'))
        self.btn_close=QPushButton('FECHAR SESSÃO'); self.btn_close.clicked.connect(lambda:self.run_whats('close'))
        row.addWidget(self.btn_open); row.addWidget(self.btn_close); fl.addLayout(row); l.addWidget(f)
        f2,fl2=self.panel('PREPARAR ENVIO','Selecione a mensagem e o CSV. A lista de destinatários fica em uma área própria abaixo; confira os telefones antes de enviar.')
        fl2.setSpacing(12)
        grid=QHBoxLayout()
        self.msg_path=QLineEdit(); self.msg_path.setReadOnly(True); self.msg_path.setPlaceholderText('Nenhum arquivo .txt selecionado')
        bmsg=QPushButton('SELECIONAR MENSAGEM'); bmsg.clicked.connect(self.pick_message)
        grid.addWidget(self.msg_path,1); grid.addWidget(bmsg); fl2.addLayout(grid)
        grid2=QHBoxLayout()
        self.csv_path=QLineEdit(); self.csv_path.setReadOnly(True); self.csv_path.setPlaceholderText('Nenhum arquivo .csv selecionado')
        bc=QPushButton('SELECIONAR CSV'); bc.clicked.connect(self.pick_csv)
        grid2.addWidget(self.csv_path,1); grid2.addWidget(bc); fl2.addLayout(grid2)
        # Prévia visível dos destinatários carregados do CSV
        preview_head=QHBoxLayout()
        self.contacts_count=QLabel('Destinatários: nenhum CSV carregado')
        self.contacts_count.setStyleSheet('color:#65e7ff;font-weight:700;')
        self.btn_refresh_contacts=QPushButton('ATUALIZAR LISTA')
        self.btn_refresh_contacts.clicked.connect(self.refresh_contacts_preview)
        preview_head.addWidget(self.contacts_count); preview_head.addStretch(1); preview_head.addWidget(self.btn_refresh_contacts)
        fl2.addLayout(preview_head)
        self.contacts_table=QTableWidget(0,2)
        self.contacts_table.setHorizontalHeaderLabels(['CLIENTE / NOME','TELEFONE / WHATSAPP'])
        self.contacts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.contacts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.contacts_table.setAlternatingRowColors(True)
        self.contacts_table.verticalHeader().setVisible(False)
        self.contacts_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.contacts_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.contacts_table.setColumnWidth(1, 220)
        self.contacts_table.setMinimumHeight(220); self.contacts_table.setMaximumHeight(340)
        self.contacts_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.contacts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.contacts_table.setWordWrap(False)
        self.contacts_table.setStyleSheet('QTableWidget{background:#0a0a19;color:#f1eaff;gridline-color:#30213f;border:1px solid #624074;border-radius:8px;alternate-background-color:#121127;selection-background-color:#54245b;selection-color:#ffffff;} QTableWidget::item{padding:8px 10px;} QHeaderView::section{background:#21152f;color:#ff83d5;padding:10px 8px;border:0;font-weight:700;}')
        self.contacts_table.verticalHeader().setDefaultSectionSize(36)
        fl2.addWidget(self.contacts_table)
        # Separador e controles em linhas próprias para evitar sobreposição com a tabela.
        grid3=QHBoxLayout()
        grid3.setSpacing(10)
        self.photo_path=QLineEdit(); self.photo_path.setReadOnly(True); self.photo_path.setPlaceholderText('Opcional: nenhuma imagem selecionada')
        bp=QPushButton('ESCOLHER IMAGEM'); bp.clicked.connect(self.pick_photo)
        grid3.addWidget(self.photo_path,1); grid3.addWidget(bp); fl2.addLayout(grid3)
        self.welcome_check=QCheckBox('Enviar saudação personalizada (Olá, NOME! Tudo bem?)'); self.welcome_check.setChecked(True)
        self.photo_check=QCheckBox('Enviar imagem selecionada antes da mensagem')
        fl2.addWidget(self.welcome_check); fl2.addWidget(self.photo_check)
        self.message_preview=QPlainTextEdit(); self.message_preview.setPlaceholderText('O conteúdo do .txt aparece aqui após selecionar o arquivo.'); self.message_preview.setMaximumHeight(95); fl2.addWidget(self.message_preview)
        row2=QHBoxLayout()
        row2.setSpacing(12)
        self.btn_send=QPushButton('REVISAR E ENVIAR MENSAGENS'); self.btn_send.setObjectName('primary'); self.btn_send.clicked.connect(self.confirm_send)
        self.btn_contacts=QPushButton('ADICIONAR CONTATOS DO CSV'); self.btn_contacts.clicked.connect(self.confirm_contacts)
        row2.addWidget(self.btn_send); row2.addWidget(self.btn_contacts); fl2.addLayout(row2); l.addWidget(f2)
        f3,fl3=self.panel('LOG DE OPERAÇÕES','Mensagens de andamento, erros e resultados aparecem nesta área — não é necessário interagir com o terminal.')
        self.whats_log=QTextEdit(); self.whats_log.setReadOnly(True); self.whats_log.setMinimumHeight(125); self.whats_log.setPlaceholderText('Aguardando operação...'); fl3.addWidget(self.whats_log); l.addWidget(f3,1)
        self.whats_driver=None; self.whats_worker=None; self.selected_photo=''
        return page

    def pick_message(self):
        path,_=QFileDialog.getOpenFileName(self,'Selecionar mensagem','.','Arquivos de texto (*.txt);;Todos os arquivos (*)')
        if path:
            try:
                content=Path(path).read_text(encoding='utf-8').strip()
                if not content: raise ValueError('O arquivo está vazio.')
                self.msg_path.setText(path); self.message_preview.setPlainText(content)
                self.log_whats(f'Mensagem carregada: {path}')
            except Exception as exc: QMessageBox.warning(self,'Mensagem inválida',str(exc))

    def pick_csv(self):
        path,_=QFileDialog.getOpenFileName(self,'Selecionar lista de contatos','.','Arquivos CSV (*.csv);;Todos os arquivos (*)')
        if path:
            self.csv_path.setText(path)
            self.log_whats(f'CSV selecionado: {path}')
            self.refresh_contacts_preview()

    def pick_photo(self):
        path,_=QFileDialog.getOpenFileName(self,'Selecionar imagem','.','Imagens (*.png *.jpg *.jpeg *.webp)')
        if path: self.selected_photo=path; self.photo_path.setText(path); self.photo_check.setChecked(True)

    def refresh_contacts_preview(self):
        try:
            clients = self.read_whats_csv()
            self.contacts_table.setRowCount(0)
            for name, phone in clients:
                row = self.contacts_table.rowCount()
                self.contacts_table.insertRow(row)
                self.contacts_table.setItem(row, 0, QTableWidgetItem(name or '(sem nome no CSV)'))
                self.contacts_table.setItem(row, 1, QTableWidgetItem(phone))
            self.contacts_count.setText(f'◉ {len(clients)} CONTATOS VÁLIDOS  •  LISTA PRONTA PARA REVISÃO')
            self.log_whats(f'Prévia CSV carregada: {len(clients)} contato(s) válido(s).')
            for idx, (name, phone) in enumerate(clients, start=1):
                self.log_whats(f'CONTATO {idx:03d} | {name or "(sem nome)"} | {phone}')
        except Exception as exc:
            if hasattr(self, 'contacts_table'): self.contacts_table.setRowCount(0)
            if hasattr(self, 'contacts_count'): self.contacts_count.setText('Destinatários: lista não carregada')
            QMessageBox.warning(self, 'Não foi possível ler os destinatários', str(exc))

    def read_whats_csv(self):
        path=self.csv_path.text().strip()
        if not path or not Path(path).is_file(): raise ValueError('Selecione um arquivo CSV válido.')
        with open(path,'r',encoding='utf-8-sig',newline='') as f:
            sample=f.read(4096); f.seek(0)
            try: delimiter=csv.Sniffer().sniff(sample,delimiters=',;\t').delimiter
            except csv.Error: delimiter=','
            rows=list(csv.reader(f,delimiter=delimiter,skipinitialspace=True))
        clients=[]; seen=set()
        for i,row in enumerate(rows):
            if not row or not any(str(x).strip() for x in row): continue
            if i==0 and any(str(x).strip().lower() in {'nome','name','cliente','telefone','phone','whatsapp'} for x in row[:3]): continue
            if len(row)<2: continue
            name=str(row[0]).strip(); phone=re.sub(r'\D','',str(row[1]))
            if len(phone)>=8 and phone not in seen:
                seen.add(phone); clients.append([name,phone])
        if not clients: raise ValueError('Nenhum telefone válido foi encontrado nas duas primeiras colunas do CSV.')
        return clients

    def log_whats(self, message):
        if hasattr(self,'whats_log') and self.whats_log:
            self.whats_log.append(message)
            self.whats_log.verticalScrollBar().setValue(self.whats_log.verticalScrollBar().maximum())
        if self.log_box: self.log_box.append('[WhatsApp] '+message)

    def run_whats(self, action, clients=None, message='', photo=False, welcome=False, photo_path=''):
        if hasattr(self,'whats_worker') and self.whats_worker and self.whats_worker.isRunning():
            QMessageBox.information(self,'Operação em andamento','Aguarde a operação atual terminar.'); return
        self.whats_worker=WhatsWorker(action,self.whats_driver,message,clients,photo,welcome,photo_path)
        self.whats_worker.log.connect(self.log_whats)
        self.whats_worker.done.connect(self.whats_finished)
        self.set_whats_controls(False)
        self.whats_worker.start()

    def whats_finished(self, driver, error):
        self.whats_driver=driver
        self.set_whats_controls(True)
        if error: QMessageBox.warning(self,'Operação finalizada com erro',error)
        elif self.whats_driver is not None: self.log_whats('Sessão ativa e pronta para novas operações.')

    def set_whats_controls(self, enabled):
        for name in ('btn_open','btn_close','btn_send','btn_contacts'):
            if hasattr(self,name): getattr(self,name).setEnabled(enabled)

    def confirm_send(self):
        try:
            message=self.message_preview.toPlainText().strip()
            if not message: raise ValueError('Selecione um arquivo .txt com a mensagem.')
            clients=self.read_whats_csv()
            if self.whats_driver is None: raise ValueError('Clique em ABRIR WHATSAPP WEB e autentique a sessão antes de enviar.')
            photo=self.photo_check.isChecked()
            if photo and (not self.selected_photo or not Path(self.selected_photo).is_file()): raise ValueError('Selecione uma imagem válida ou desmarque a opção de imagem.')
            confirm_text = (f'A mensagem será enviada para {len(clients)} contatos.\n'
                            f'Confira a tabela de destinatários no aplicativo antes de confirmar.\n'
                            f'Saudação: {"sim" if self.welcome_check.isChecked() else "não"}\n'
                            f'Imagem: {"sim" if photo else "não"}\n\nDeseja continuar?')
            answer=QMessageBox.question(self,'Confirmar envio',confirm_text,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes: return
            self.log_whats(f'INÍCIO DO ENVIO — {len(clients)} destinatário(s).')
            for idx, (name, phone) in enumerate(clients, start=1):
                self.log_whats(f'FILA {idx:03d} | Cliente: {name or "(sem nome)"} | Telefone: {phone}')
            if photo:
                image=QImage(self.selected_photo)
                if image.isNull(): raise ValueError('Não foi possível abrir a imagem selecionada.')
                self.log_whats('A imagem será anexada como foto pelo seletor de mídia do WhatsApp Web.')
            self.run_whats('send',clients,message,photo,self.welcome_check.isChecked(),
                           self.selected_photo if photo else '')
        except Exception as exc: QMessageBox.warning(self,'Não foi possível iniciar o envio',str(exc))

    def confirm_contacts(self):
        try:
            clients=self.read_whats_csv()
            if self.whats_driver is None: raise ValueError('Abra o WhatsApp Web antes de adicionar contatos.')
            answer=QMessageBox.question(self,'Confirmar contatos',f'Tentar adicionar {len(clients)} contatos do CSV?\nConfira a lista exibida no aplicativo antes de continuar.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self.log_whats(f'INÍCIO DO CADASTRO DE CONTATOS — {len(clients)} registro(s).')
                for idx, (name, phone) in enumerate(clients, start=1):
                    self.log_whats(f'CADASTRO {idx:03d} | Cliente: {name or "(sem nome)"} | Telefone: {phone}')
                self.run_whats('contacts',clients)
        except Exception as exc: QMessageBox.warning(self,'Não foi possível iniciar',str(exc))

    def logs_page(self):
        page=QWidget(); l=QVBoxLayout(page); h=QLabel('Registros do sistema'); h.setObjectName('heading'); l.addWidget(h)
        f,fl=self.panel('EVENTOS DESTA SESSÃO','Eventos da sessão, incluindo nome e telefone dos destinatários carregados do CSV.')
        self.log_box=QTextEdit(); self.log_box.setReadOnly(True); self.log_box.setPlainText(f'Interface iniciada.\nProjeto: {BASE}\nÁudio de abertura: {"encontrado" if AUDIO_PATH.exists() else "não encontrado"}.')
        fl.addWidget(self.log_box); l.addWidget(f,1); return page

    def start_jarvis(self):
        # O caminho padrão corresponde a ~/Área de trabalho/Projetos/Jarvis.
        jarvis_dir = Path.home() / 'Área de trabalho' / 'Projetos' / 'Jarvis'
        starter = jarvis_dir / 'iniciar.sh'
        if not starter.is_file():
            QMessageBox.warning(self, 'Jarvis não encontrado', f'Não encontrei o iniciar.sh em:\n{starter}\n\nConfira se o projeto está nessa pasta.')
            self.append_log('ERRO: iniciar.sh do Jarvis não encontrado: ' + str(starter))
            return
        # Reutiliza o processo enquanto ele estiver ativo; não cria instâncias duplicadas.
        if getattr(self, 'jarvis_process', None) is not None and self.jarvis_process.poll() is None:
            self.jarvis_status.setText('Servidor já iniciado; abrindo Firefox...')
            webbrowser.get('firefox').open('http://localhost:5173')
            self.append_log('Jarvis já estava em execução; Firefox aberto em http://localhost:5173.')
            return
        try:
            log_path = BASE / 'jarvis.log'
            log_file = open(log_path, 'a', encoding='utf-8')
            # O script pode perguntar se deve continuar sem backend/.env. Envia Enter
            # automaticamente para que o fluxo não fique preso aguardando o terminal.
            self.jarvis_process = subprocess.Popen(
                ['bash', '-lc', "printf '\n' | ./iniciar.sh"],
                cwd=str(jarvis_dir), stdout=log_file, stderr=subprocess.STDOUT,
                start_new_session=True
            )
            self.jarvis_log_file = log_file
            self.jarvis_status.setText('Inicializando backend e frontend...')
            self.jarvis_button.setEnabled(False)
            self.append_log('Jarvis iniciado via iniciar.sh. Log: ' + str(log_path))
            QTimer.singleShot(5000, self.open_jarvis_firefox)
            QTimer.singleShot(7000, self.restore_jarvis_button)
        except Exception as exc:
            self.jarvis_status.setText('Falha ao iniciar Jarvis.')
            QMessageBox.critical(self, 'Erro ao iniciar Jarvis', str(exc))
            self.append_log('ERRO ao iniciar Jarvis: ' + str(exc))

    def open_jarvis_firefox(self):
        try:
            webbrowser.get('firefox').open('http://localhost:5173')
            self.jarvis_status.setText('Firefox aberto em http://localhost:5173')
            self.append_log('Firefox aberto em http://localhost:5173. Consulte jarvis.log se não carregar.')
        except Exception as exc:
            self.jarvis_status.setText('Jarvis iniciou; não foi possível abrir Firefox automaticamente.')
            self.append_log('Aviso ao abrir Firefox: ' + str(exc))

    def restore_jarvis_button(self):
        if hasattr(self, 'jarvis_button'):
            self.jarvis_button.setEnabled(True)

    def append_log(self, message):
        if getattr(self, 'log_box', None) is not None:
            self.log_box.append(message)

    def save_intro_audio_setting(self, enabled):
        self.settings.setValue('intro_audio_enabled', bool(enabled))
        self.settings.sync()
        if hasattr(self, 'log_box') and self.log_box:
            self.log_box.append('Áudio de abertura: ' + ('ativado' if enabled else 'desativado') + ' (preferência salva).')

    def navigate(self, idx):
        self.stack.setCurrentIndex(idx)
        for i,b in enumerate(self.nav_buttons): b.setProperty('selected', i==idx); b.style().unpolish(b); b.style().polish(b)
        if self.log_box: self.log_box.append(f'Módulo selecionado: {idx}')

    def launch_backend(self, mode):
        if mode == 'whatsapp':
            self.navigate(2)
            self.run_whats('open')
            return
        QMessageBox.information(self, 'Módulo de e-mail', 'O fluxo de e-mail ainda utiliza o backend de console. Esta atualização remove o console do fluxo de WhatsApp.')

    def start_intro(self):
        self.showFullScreen()
        self.intro.setGeometry(self.geometry())
        self.intro.start()

    def finish_intro(self):
        self.showFullScreen()
        self.raise_(); self.activateWindow()
        self.intro_done = True

    def closeEvent(self, event):
        try:
            if getattr(self, 'whats_driver', None) is not None:
                self.whats_driver.quit()
        except Exception:
            pass
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.intro.isVisible():
            self.intro.timer.stop(); self.intro.player.stop(); self.intro.hide(); self.finish_intro(); return
        super().keyPressEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('Olha-a-Mensagem')
    app.setStyle('Fusion')
    window = MainWindow()
    sys.exit(app.exec())
