"""Config viva do processo.

O CLI le o config uma vez e termina. O servidor e o app de desktop ficam dias
no ar, e a pessoa troca modelo, limiares e ate o vault pela interface: quem
guarda a config precisa conseguir troca-la sem reiniciar nada.

Tambem e aqui que o processo sobrevive a falta de vault. Antes, o import do
server.py chamava load_config() e morria sem vault configurado - aceitavel
num comando de terminal, inaceitavel num app que precisa abrir justamente
para a pessoa escolher o vault.
"""

from __future__ import annotations

import threading

from .config import Config, VaultNaoConfigurado, load_config


class NaoConfigurado(RuntimeError):
    """Pedido que precisa do vault, num processo que ainda nao tem um.

    RuntimeError, e nao o SystemExit do load_config: dentro de uma ferramenta
    MCP ou de uma rota HTTP, SystemExit derrubaria o processo inteiro em vez
    de virar uma resposta de erro.
    """


_trava = threading.Lock()
_atual: Config | None = None
_motivo: str = ""


def recarregar() -> Config | None:
    """Rele o config.toml. Devolve None se o vault ainda nao esta pronto."""
    global _atual, _motivo
    with _trava:
        try:
            _atual = load_config()
            _motivo = ""
        except VaultNaoConfigurado as exc:
            _atual = None
            _motivo = str(exc)
        return _atual


def tentar() -> Config | None:
    """Config atual, ou None. Le do disco so na primeira vez."""
    if _atual is None and not _motivo:
        return recarregar()
    return _atual


def config() -> Config:
    """Config atual, ou NaoConfigurado com o motivo legivel."""
    cfg = tentar()
    if cfg is None:
        raise NaoConfigurado(_motivo or "vault nao configurado")
    return cfg


def motivo() -> str:
    """Por que nao ha config - para a tela de primeiro uso explicar."""
    tentar()
    return _motivo
