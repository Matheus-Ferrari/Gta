"""Fila simples: prepara fontes e exporta vídeos um de cada vez, sem travar o painel.

Cancelar: uma tarefa na fila sai da fila na hora; uma rodando para na próxima etapa (a próxima vez que ela informa o
progresso), porque downloads e renders em andamento não têm como ser interrompidos no meio com segurança.
"""
from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from typing import Callable

GUARDAR = 80  # tarefas terminadas que continuam visíveis no painel de Atividade


class Cancelada(Exception):
    pass


class Tarefa:
    def __init__(self, tipo: str, titulo: str, funcao: Callable, chave: str | None, meta: dict | None = None) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.tipo, self.titulo, self.funcao, self.chave = tipo, titulo, funcao, chave
        self.meta = meta or {}  # de quem é e de onde veio (streamer, plataforma, origem): a página Produção agrupa por isso
        self.estado = "fila"
        self.progresso = 0.0
        self.mensagem = "Na fila"
        self.resultado = None
        self.criada = time.time()
        self.comecou = self.terminou = 0.0
        self.cancelar = False

    def avancar(self, progresso: float | None = None, mensagem: str | None = None) -> None:
        if self.cancelar:
            raise Cancelada("Cancelada por você.")
        if progresso is not None:
            self.progresso = max(0.0, min(1.0, progresso))
        if mensagem is not None:
            self.mensagem = mensagem

    def publico(self) -> dict:
        return {"id": self.id, "tipo": self.tipo, "titulo": self.titulo, "estado": self.estado,
                "progresso": round(self.progresso, 3), "mensagem": self.mensagem, "resultado": self.resultado,
                "criada": self.criada, "comecou": self.comecou, "terminou": self.terminou, "cancelando": self.cancelar, "meta": self.meta}


class Fila:
    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.itens: dict[str, Tarefa] = {}
        self.pendentes: queue.Queue[Tarefa] = queue.Queue()
        threading.Thread(target=self._rodar, daemon=True).start()

    def adicionar(self, tipo: str, titulo: str, funcao: Callable, chave: str | None = None, meta: dict | None = None) -> Tarefa:
        with self.trava:
            if chave:
                for t in self.itens.values():
                    if t.chave == chave and t.estado in ("fila", "rodando"):
                        return t
            tarefa = Tarefa(tipo, titulo, funcao, chave, meta)
            self.itens[tarefa.id] = tarefa
            for antiga in sorted(self.itens.values(), key=lambda t: t.criada)[:-GUARDAR]:
                if antiga.estado not in ("fila", "rodando"):
                    del self.itens[antiga.id]
        self.pendentes.put(tarefa)
        return tarefa

    def obter(self, tarefa_id: str) -> Tarefa | None:
        return self.itens.get(tarefa_id)

    def listar(self) -> list[dict]:
        with self.trava:
            itens = sorted(self.itens.values(), key=lambda t: t.criada, reverse=True)
        return [t.publico() for t in itens[:GUARDAR]]

    def cancelar(self, tarefa_id: str) -> dict:
        t = self.itens.get(str(tarefa_id))
        if not t:
            raise ValueError("Tarefa não encontrada.")
        if t.estado == "fila":
            t.estado, t.mensagem, t.terminou = "cancelada", "Cancelada antes de começar", time.time()
        elif t.estado == "rodando":
            t.cancelar, t.mensagem = True, "Cancelando: para na próxima etapa"
        return t.publico()

    def limpar(self) -> dict:
        """Tira da lista o que já terminou (pronto, erro ou cancelado). Os cortes criados continuam em Meus Cortes."""
        with self.trava:
            for t in [t for t in self.itens.values() if t.estado not in ("fila", "rodando")]:
                del self.itens[t.id]
        return {"ok": True}

    def _rodar(self) -> None:
        while True:
            tarefa = self.pendentes.get()
            if tarefa.estado == "cancelada":
                continue
            tarefa.estado, tarefa.mensagem, tarefa.comecou = "rodando", "Processando", time.time()
            try:
                tarefa.resultado = tarefa.funcao(tarefa)
                tarefa.estado, tarefa.progresso, tarefa.mensagem = "ok", 1.0, "Concluído"
            except Cancelada as erro:
                tarefa.estado, tarefa.mensagem = "cancelada", str(erro)
            except (Exception, SystemExit) as erro:  # fontes.py avisa falhas de link com SystemExit
                traceback.print_exc()
                tarefa.estado, tarefa.mensagem = "erro", str(erro) or "Falha inesperada"
            tarefa.terminou = time.time()


fila = Fila()
