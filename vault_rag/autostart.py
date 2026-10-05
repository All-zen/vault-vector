"""Abrir o app junto com o Windows, escondido na bandeja.

Pela chave Run do registro do usuario (HKCU), e nao por tarefa agendada:
nao pede administrador, aparece em Gerenciador de Tarefas > Inicializar
(onde a pessoa espera achar e desligar), e some junto com o usuario.

O instalar-servicos.ps1 usava tarefa agendada para o servidor headless,
porque ela reinicia o processo se cair. O app de desktop tem o icone da
bandeja como sinal de vida: se ele sumir, a pessoa ve.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "vault-vector"


def suportado() -> bool:
    return sys.platform == "win32"


def comando() -> str:
    """O que o Windows executa no logon.

    Prefere o vault-vector-app.exe que o pip gera ao lado do pythonw: e o
    nome que aparece no Gerenciador de Tarefas. Sem ele (instalacao sem os
    scripts), cai para o pythonw rodando o modulo.
    """
    pasta = Path(sys.executable).parent
    exe = pasta / "vault-vector-app.exe"
    if exe.is_file():
        return f'"{exe}" --escondido'
    pythonw = pasta / "pythonw.exe"
    return f'"{pythonw if pythonw.is_file() else sys.executable}" -m vault_rag.desktop --escondido'


def ligado() -> bool:
    if not suportado():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE) as k:
            valor, _ = winreg.QueryValueEx(k, NOME)
            return bool(valor)
    except OSError:
        return False


def ligar() -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, comando())


def desligar() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOME)
    except FileNotFoundError:
        pass  # ja estava desligado
