"""App de desktop: janela nativa, icone na bandeja e inicio com o Windows.

Um processo so faz tudo: o servidor HTTP (MCP para o Claude, API e
interface) roda numa thread, a janela e um WebView2 apontando para ele, e o
icone da bandeja fica de pe enquanto o processo vive. Fechar a janela so a
esconde - o Claude continua falando com o vault. Sair, so pelo menu da
bandeja.

    vault-vector-app              abre a janela
    vault-vector-app --escondido  so o icone, que e como o Windows abre no logon

Abrir uma segunda vez nao sobe um segundo servidor: a segunda instancia
acha a primeira pela porta, pede para ela mostrar a janela e sai.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

TITULO = "vault-vector"
TEAL, BRANCO, TEAL_CLARO, FUNDO, BORDA = "#2bb3a6", "#eef1ef", "#5fdccd", "#121415", "#262b2d"


def pasta_de_dados() -> Path:
    """Onde o app guarda o que nao e do vault: perfil do WebView, icone."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    pasta = Path(base) / "vault-vector"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def desenhar_icone(tamanho: int = 64):
    """A marca do app desenhada com Pillow, para a bandeja e a janela.

    Desenha em 512 (as coordenadas do SVG da interface) e reduz: desenhar
    direto em 64 deixaria a ponta redonda dos tracos serrilhada.
    """
    from PIL import Image, ImageDraw

    lado = 512
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=116, fill=FUNDO, outline=BORDA, width=6)

    def traco(x1, y1, x2, y2, cor, largura=50):
        d.line((x1, y1, x2, y2), fill=cor, width=largura)
        r = largura / 2
        for x, y in ((x1, y1), (x2, y2)):
            d.ellipse((x - r, y - r, x + r, y + r), fill=cor)

    traco(140, 140, 256, 366, TEAL)
    traco(372, 140, 256, 366, BRANCO)
    d.ellipse((256 - 54, 366 - 54, 256 + 54, 366 + 54), fill=FUNDO)
    d.ellipse((256 - 46, 366 - 46, 256 + 46, 366 + 46), fill=TEAL_CLARO)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


def arquivo_ico() -> Path:
    destino = pasta_de_dados() / "icone.ico"
    if not destino.is_file():
        desenhar_icone(256).save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    return destino


def tamanho_inicial(largura: int = 1320, altura: int = 860) -> tuple[int, int]:
    """Tamanho da janela que cabe na area util do monitor principal.

    O pywebview trabalha em pixel logico. Num notebook com escala de 125%,
    860 logicos viram 1075 fisicos e o rodape da janela ficava embaixo da
    barra de tarefas.
    """
    if sys.platform != "win32":
        return largura, altura
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    area = wintypes.RECT()
    if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):  # SPI_GETWORKAREA
        return largura, altura
    w, h = area.right - area.left, area.bottom - area.top
    if user32.IsProcessDPIAware():
        # Processo ciente de DPI recebe pixel fisico; converte para logico.
        escala = user32.GetDpiForSystem() / 96 if hasattr(user32, "GetDpiForSystem") else 1.0
        w, h = int(w / escala), int(h / escala)
    return min(largura, int(w * 0.92)), min(altura, int(h * 0.92))


# ------------------------------------------------------------- instancia
def quem_esta_na_porta(porta: int) -> str:
    """'livre', 'app' (este app ou o servidor headless dele), 'mudo' ou 'outro'.

    So conexao recusada quer dizer porta livre. Timeout quer dizer que tem
    alguem escutando e travado - tratar como livre fazia a segunda
    instancia tentar abrir a mesma porta e falhar com erro de bind.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=4) as r:
            dados = json.loads(r.read().decode("utf-8"))
        return "app" if dados.get("app") == "vault-vector" else "outro"
    except urllib.error.HTTPError:
        return "outro"
    except urllib.error.URLError as exc:
        recusada = isinstance(exc.reason, ConnectionRefusedError)
        return "livre" if recusada else "mudo"
    except ConnectionRefusedError:
        return "livre"
    except (TimeoutError, OSError, ValueError):
        return "mudo"


def pedir_para_mostrar(porta: int, token: str) -> bool:
    """Pede a instancia que ja roda para mostrar a janela. True se ela tem janela."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{porta}/api/sistema/mostrar", data=b"{}", method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def avisar(mensagem: str) -> None:
    """Caixa de mensagem nativa: sob pythonw nao ha console para escrever."""
    print(mensagem, file=sys.stderr)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, mensagem, TITULO, 0x40)


# --------------------------------------------------------------- servidor
class Servidor:
    """O uvicorn numa thread, com parada limpa."""

    def __init__(self, porta: int, token: str):
        import uvicorn

        from .server import criar_app

        app = criar_app("127.0.0.1", porta, token)
        config = uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning")
        self._uvicorn = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._uvicorn.run, name="servidor", daemon=True)

    def iniciar(self, espera: float = 20.0) -> bool:
        self._thread.start()
        limite = time.time() + espera
        while time.time() < limite:
            if self._uvicorn.started:
                return True
            if not self._thread.is_alive():
                return False
            time.sleep(0.05)
        return False

    def parar(self) -> None:
        self._uvicorn.should_exit = True
        self._thread.join(timeout=5)


# ----------------------------------------------------------- atalho global
class AtalhoGlobal:
    """Ctrl+Alt+Espaco traz o app de qualquer lugar, com o foco na busca.

    E o que faz o vault-vector servir no meio do trabalho: a pergunta
    aparece, o atalho abre a busca, e a resposta vem sem trocar de janela
    com o mouse.

    RegisterHotKey vale por thread, e quem recebe o WM_HOTKEY e a fila de
    mensagens da thread que registrou. Por isso o registro e o laco de
    GetMessage vivem na mesma thread, separada da GUI.
    """

    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
    VK_SPACE, WM_HOTKEY, WM_QUIT = 0x20, 0x0312, 0x0012
    TEXTO = "Ctrl+Alt+Espaço"

    def __init__(self, acao):
        self.acao = acao
        self.ativo = False
        self._thread_id = None
        self._pronto = threading.Event()

    def iniciar(self) -> bool:
        if sys.platform != "win32":
            return False
        threading.Thread(target=self._laco, name="atalho-global", daemon=True).start()
        self._pronto.wait(2)
        return self.ativo

    def _laco(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        mods = self.MOD_CONTROL | self.MOD_ALT | self.MOD_NOREPEAT
        # Falha quando outro programa ja tem o atalho: o app segue sem ele.
        self.ativo = bool(user32.RegisterHotKey(None, 1, mods, self.VK_SPACE))
        self._pronto.set()
        if not self.ativo:
            print(f"atalho {self.TEXTO} ja esta em uso por outro programa", file=sys.stderr)
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self.WM_HOTKEY:
                try:
                    self.acao()
                except Exception:
                    import traceback

                    traceback.print_exc()
        user32.UnregisterHotKey(None, 1)

    def parar(self) -> None:
        if self.ativo and self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)


# ------------------------------------------------------------------ ponte
class Ponte:
    """O que a interface chama via window.pywebview.api.

    So o que o navegador nao consegue fazer sozinho. O resto passa pela API
    HTTP, igual no navegador e no app.

    Todo atributo aqui precisa comecar com '_', menos os metodos expostos.
    O pywebview percorre os atributos publicos do js_api para expor ao
    JavaScript, recursivamente: com a janela num atributo publico, ele
    descia pelos objetos .NET do WinForms sem fim e travava a GUI.
    """

    def __init__(self, janela=None):
        self._janela = janela

    def escolher_pasta(self):
        import webview

        escolha = self._janela.create_file_dialog(webview.FileDialog.FOLDER)
        return escolha[0] if escolha else None


# ------------------------------------------------------------------ app
class App:
    def __init__(self, porta: int, escondido: bool):
        self.porta = porta
        self.escondido = escondido
        self.saindo = False
        self.janela = None
        self.icone = None
        self.servidor: Servidor | None = None
        self.atalho = AtalhoGlobal(self.mostrar)

    def mostrar(self) -> None:
        if self.janela is None:
            return
        self.janela.show()
        self.janela.restore()  # se estava minimizada
        # Chamou o app, quer buscar: o foco vai direto para o campo, se a
        # tela aberta for a de busca.
        self.janela.evaluate_js("document.querySelector('#busca')?.focus()")

    def esconder(self) -> None:
        if self.janela is not None:
            self.janela.hide()

    def sair(self) -> None:
        self.saindo = True
        if self.icone is not None:
            self.icone.stop()
        if self.janela is not None:
            self.janela.destroy()

    def _ao_fechar(self):
        # Fechar a janela e esconder: o servidor do Claude continua no ar.
        # So o "Sair" da bandeja encerra o processo.
        if self.saindo:
            return True
        self.esconder()
        return False

    def _menu(self):
        import pystray

        from . import autostart

        def alternar_autostart():
            if autostart.ligado():
                autostart.desligar()
            else:
                autostart.ligar()

        abrir = "Abrir o vault-vector"
        if self.atalho.ativo:
            abrir += f"   {AtalhoGlobal.TEXTO}"
        itens = [
            pystray.MenuItem(abrir, lambda: self.mostrar(), default=True),
            pystray.Menu.SEPARATOR,
        ]
        if autostart.suportado():
            itens.append(
                pystray.MenuItem("Abrir com o Windows", alternar_autostart, checked=lambda item: autostart.ligado())
            )
        itens += [pystray.Menu.SEPARATOR, pystray.MenuItem("Sair", lambda: self.sair())]
        return pystray.Menu(*itens)

    def rodar(self, token: str) -> int:
        import pystray
        import webview

        from . import autostart, web

        situacao = quem_esta_na_porta(self.porta)
        if situacao == "mudo":
            avisar(
                f"Ja tem um vault-vector na porta {self.porta}, mas ele nao respondeu.\n\n"
                "Encerre pelo Gerenciador de Tarefas (vault-vector-app) e abra de novo."
            )
            return 1
        if situacao == "outro":
            avisar(
                f"A porta {self.porta} esta ocupada por outro programa.\n\n"
                "Se for o servico antigo do vault-vector, o app substitui ele:\n"
                "  .\\instalar-servicos.ps1 -Desinstalar\n\n"
                "Ou defina VAULT_RAG_PORT com outra porta."
            )
            return 1

        if situacao == "app":
            # Ja tem um vault-vector nesta porta. Se for o app, ele mostra a
            # janela e esta instancia sai. Se for o servidor headless (o
            # 'servico' antigo), este processo vira so janela + bandeja.
            if pedir_para_mostrar(self.porta, token):
                return 0
        else:
            self.servidor = Servidor(self.porta, token)
            if not self.servidor.iniciar():
                avisar("O servidor nao subiu. Veja o app.log na pasta do vault-vector.")
                return 1

        web.ganchos.desktop = True
        web.ganchos.autostart = autostart
        web.ganchos.mostrar_janela = self.mostrar

        if sys.platform == "win32":
            import ctypes

            # Sem isto, o Windows agrupa a janela com qualquer outro python.exe
            # na barra de tarefas, com o icone do Python.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("vault-vector.app")

        ponte = Ponte()
        largura, altura = tamanho_inicial()
        self.janela = webview.create_window(
            TITULO,
            f"http://127.0.0.1:{self.porta}/",
            js_api=ponte,
            width=largura,
            height=altura,
            min_size=(960, 620),
            hidden=self.escondido,
            background_color=FUNDO,
            text_select=True,
        )
        ponte._janela = self.janela
        self.janela.events.closing += self._ao_fechar

        if self.atalho.iniciar():
            web.ganchos.atalho = AtalhoGlobal.TEXTO
        self.icone = pystray.Icon("vault-vector", desenhar_icone(64), TITULO, self._menu())
        self.icone.run_detached()

        try:
            webview.start(
                gui="edgechromium" if sys.platform == "win32" else None,
                # Sem isto, janela e barra de tarefas mostram o icone do Python.
                icon=str(arquivo_ico()),
                # Sem private_mode o WebView guarda localStorage entre uma
                # abertura e outra - e la que fica o rascunho de edicao.
                private_mode=False,
                storage_path=str(pasta_de_dados() / "webview"),
            )
        finally:
            self.atalho.parar()
            if self.icone is not None:
                self.icone.stop()
            if self.servidor is not None:
                self.servidor.parar()
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vault-vector-app", description="vault-vector como app de desktop")
    parser.add_argument("--escondido", action="store_true", help="abre so o icone da bandeja (logon)")
    parser.add_argument("--porta", type=int, default=int(os.environ.get("VAULT_RAG_PORT", "8765")))
    args = parser.parse_args(argv)

    # Sob pythonw (o .exe sem console) stdout e stderr sao None, e o primeiro
    # print derrubaria o processo sem deixar rastro.
    if sys.stdout is None or sys.stderr is None:
        from .cli import abrir_log_do_servico

        abrir_log_do_servico("app.log")
        print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  app subindo (pid {os.getpid()}) =====")

    from importlib.util import find_spec

    if not (find_spec("pystray") and find_spec("webview")):
        avisar(
            "Faltam as dependencias do app de desktop.\n\n"
            'Instale com:  pip install -e ".[desktop]"'
        )
        return 1

    from .server import token_do_projeto

    return App(args.porta, args.escondido).rodar(token_do_projeto(criar=True))


if __name__ == "__main__":
    sys.exit(main())
