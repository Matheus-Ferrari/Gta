"""Fila simples: prepara fontes e exporta vídeos um de cada vez, sem travar o painel."""
from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from typing import Callable


class Tarefa:
    def __init__(self, tipo: str, titulo: str, funcao: Callable, chave: str | None) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.tipo, self.titulo, self.funcao, self.chave = tipo, titulo, funcao, chave
        self.estado = "fila"
        self.progresso = 0.0
        self.mensagem = "Na fila"
        self.resultado = None
        self.criada = time.time()

    def avancar(self, progresso: float | None = None, mensagem: str | None = None) -> None:
        if progresso is not None:
            self.progresso = max(0.0, min(1.0, progresso))
        if mensagem is not None:
            self.mensagem = mensagem

    def publico(self) -> dict:
        return {"id": self.id, "tipo": self.tipo, "titulo": self.titulo, "estado": self.estado,
                "progresso": round(self.progresso, 3), "mensagem": self.mensagem, "resultado": self.resultado,
                "criada": self.criada}


class Fila:
    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.itens: dict[str, Tarefa] = {}
        self.pendentes: queue.Queue[Tarefa] = queue.Queue()
        threading.Thread(target=self._rodar, daemon=True).start()

    def adicionar(self, tipo: str, titulo: str, funcao: Callable, chave: str | None = None) -> Tarefa:
        with self.trava:
            if chave:
                for t in self.itens.values():
                    if t.chave == chave and t.estado in ("fila", "rodando"):
                        return t
            tarefa = Tarefa(tipo, titulo, funcao, chave)
            self.itens[tarefa.id] = tarefa
            for antiga in sorted(self.itens.values(), key=lambda t: t.criada)[:-40]:
                if antiga.estado not in ("fila", "rodando"):
                    del self.itens[antiga.id]
        self.pendentes.put(tarefa)
        return tarefa

    def obter(self, tarefa_id: str) -> Tarefa | None:
        return self.itens.get(tarefa_id)

    def listar(self) -> list[dict]:
        with self.trava:
            itens = sorted(self.itens.values(), key=lambda t: t.criada, reverse=True)
        return [t.publico() for t in itens[:25]]

    def _rodar(self) -> None:
        while True:
            tarefa = self.pendentes.get()
            tarefa.estado, tarefa.mensagem = "rodando", "Processando"
            try:
                tarefa.resultado = tarefa.funcao(tarefa)
                tarefa.estado, tarefa.progresso, tarefa.mensagem = "ok", 1.0, "Concluído"
            except (Exception, SystemExit) as erro:  # fontes.py avisa falhas de link com SystemExit
                traceback.print_exc()
                tarefa.estado, tarefa.mensagem = "erro", str(erro) or "Falha inesperada"


fila = Fila()
