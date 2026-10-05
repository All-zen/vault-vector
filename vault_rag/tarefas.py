"""Trabalho demorado em segundo plano, com andamento consultavel.

Indexar, baixar modelo, medir paralelismo, calibrar: tudo leva de segundos
a minutos, e uma requisicao HTTP nao pode ficar pendurada esse tempo todo.
A rota dispara a tarefa e devolve o id na hora; a interface consulta o
andamento ate o estado sair de "rodando".

Uma tarefa por tipo de cada vez. Clicar duas vezes em "indexar" devolve a
tarefa que ja esta rodando, em vez de abrir uma segunda.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tarefa:
    id: str
    tipo: str
    estado: str = "rodando"  # rodando, ok, erro
    feito: float = 0
    total: float | None = None
    mensagem: str = ""
    # Resultados que saem antes do fim - cada nivel do bench, cada ponto da
    # calibracao - para a interface desenhar enquanto a medicao anda.
    parciais: list = field(default_factory=list)
    resultado: Any = None
    erro: str = ""
    inicio: float = field(default_factory=time.time)
    fim: float | None = None

    def andamento(self, feito: float, total: float | None = None, mensagem: str = "") -> None:
        self.feito = feito
        if total is not None:
            self.total = total
        if mensagem:
            self.mensagem = mensagem

    def parcial(self, item: Any) -> None:
        self.parciais.append(item)

    def como_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "estado": self.estado,
            "feito": self.feito,
            "total": self.total,
            "mensagem": self.mensagem,
            "parciais": list(self.parciais),
            "resultado": self.resultado,
            "erro": self.erro,
            "segundos": round((self.fim or time.time()) - self.inicio, 1),
        }


class Tarefas:
    def __init__(self, guardar: int = 20):
        self._trava = threading.Lock()
        self._todas: dict[str, Tarefa] = {}
        self._guardar = guardar

    def iniciar(self, tipo: str, trabalho: Callable[[Tarefa], Any]) -> Tarefa:
        """Roda trabalho(tarefa) numa thread. O retorno vira o resultado."""
        with self._trava:
            rodando = self.rodando(tipo)
            if rodando:
                return rodando
            tarefa = Tarefa(id=uuid.uuid4().hex[:12], tipo=tipo)
            self._todas[tarefa.id] = tarefa
            self._podar()

        def executar():
            try:
                tarefa.resultado = trabalho(tarefa)
                tarefa.estado = "ok"
            except Exception as exc:
                # A thread morre calada se a excecao escapar; o erro tem que
                # chegar a quem esta olhando o andamento. O log vem antes do
                # estado: quem ve "erro" pode ler o log em seguida.
                traceback.print_exc()
                tarefa.erro = str(exc) or type(exc).__name__
                tarefa.estado = "erro"
            finally:
                tarefa.fim = time.time()

        threading.Thread(target=executar, name=f"tarefa-{tipo}", daemon=True).start()
        return tarefa

    def obter(self, id_: str) -> Tarefa | None:
        return self._todas.get(id_)

    def rodando(self, tipo: str) -> Tarefa | None:
        return next(
            (t for t in self._todas.values() if t.tipo == tipo and t.estado == "rodando"),
            None,
        )

    def _podar(self) -> None:
        terminadas = [t for t in self._todas.values() if t.estado != "rodando"]
        for t in sorted(terminadas, key=lambda t: t.inicio)[: max(0, len(self._todas) - self._guardar)]:
            del self._todas[t.id]
