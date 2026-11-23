"""Preparação da análise do vídeo ao vivo, em janelas curtas, sobre uma fonte AUTORIZADA.

A fonte é sempre um arquivo deste PC, por exemplo a gravação que o próprio usuário faz no OBS e que cresce
durante a live (use MKV ou MP4 fragmentado no OBS). Nada aqui captura a live de terceiros: a API de listagem da
Twitch não dá acesso ao vídeo ao vivo, e este módulo não tenta contornar isso.

O trabalho pesado roda em outro processo (python -m cortes.ao_vivo), com prioridade abaixo do normal, uma
análise por vez, ffmpeg com 1 thread e só uma janela de 20-30 s na memória. O arquivo é lido em sequência,
sem carregar tudo, e com --seguir o ffmpeg espera o arquivo crescer.

Por janela: picos de voz e de som, mudanças de cena, movimento na região da webcam (se informada) e reações
(pico de voz + movimento na webcam). Os picos viram sugestões de início e fim; o corte só é criado quando o
usuário pede, reaproveitando vods.criar_corte com tipo "arquivo".
"""
from __future__ import annotations

import argparse
import re
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import numpy as np

from .config import DADOS, TAXA_AUDIO, ffmpeg

BASE = Path(__file__).resolve().parent.parent
PASTA = DADOS / "descobrir" / "ao_vivo"
ARQ_ESTADO = PASTA / "analise.json"
ARQ_LOG = PASTA / "analise.log"
EXT = {".mp4", ".mkv", ".mov", ".ts", ".flv", ".webm", ".m4v"}
JANELAS = (20, 25, 30)
LARG, ALT, FPS = 160, 90, 1  # imagem reduzida: 1 quadro cinza de 160x90 por segundo
HISTORICO = 300  # segundos usados como "normal" do áudio e da imagem
VOZ_MIN = 0.5  # fala tem energia na faixa da voz e espectro com harmônicos; ruído e explosão ficam abaixo
ESPERA_CRESCER = 120  # com --seguir: 2 min sem o arquivo crescer = gravação encerrada
ANTES, DEPOIS, JUNTAR, MAX_CORTE = 15, 10, 20, 60
MAX_SUGESTOES = 200
PRIORIDADE = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
WEBCAMS = {  # frações x, y, largura, altura (as mesmas posições do painel)
    "inferior-direito": (0.72, 0.68, 0.26, 0.30),
    "inferior-esquerdo": (0.02, 0.68, 0.26, 0.30),
    "superior-direito": (0.72, 0.02, 0.26, 0.30),
    "superior-esquerdo": (0.02, 0.02, 0.26, 0.30),
}


def _gravar(dados: dict) -> None:
    """Grava o estado sem deixar arquivo pela metade. No Windows o replace falha se alguém estiver lendo: tenta de novo."""
    PASTA.mkdir(parents=True, exist_ok=True)
    temp = ARQ_ESTADO.with_name(f"analise.{os.getpid()}.tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    for _ in range(20):
        try:
            temp.replace(ARQ_ESTADO)
            return
        except PermissionError:
            time.sleep(0.05)
    temp.unlink(missing_ok=True)


def ler_estado() -> dict:
    for _ in range(3):
        try:
            return json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            time.sleep(0.05)
    return {}


# ---------------------------------------------------------------- processo de análise (roda fora do painel)

def _fluxo(arquivo: str, inicio: float, seguir: bool, video: bool, visual: str) -> subprocess.Popen:
    """Um ffmpeg lendo o arquivo em sequência e entregando só áudio (16 kHz mono) ou só imagem (160x90 cinza)."""
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-filter_threads", "1", "-threads", "1"]
    if seguir:
        cmd += ["-follow", "1"]  # no fim do arquivo, espera ele crescer; quem encerra é o vigia (_vigiar)
    if inicio:
        cmd += ["-ss", f"{inicio:.3f}"]
    if video and visual == "leve":
        cmd += ["-skip_frame", "nokey"]  # decodifica só os quadros-chave: bem mais leve
    cmd += ["-i", "file:" + arquivo]
    if video:
        cmd += ["-map", "0:v:0", "-an", "-vf", f"fps={FPS},scale={LARG}:{ALT}:flags=area,format=gray", "-f", "rawvideo", "pipe:1"]
    else:
        cmd += ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(TAXA_AUDIO), "-f", "s16le", "pipe:1"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=PRIORIDADE, bufsize=0)


def _ler(proc: subprocess.Popen | None, n: int) -> bytes:
    if proc is None:
        return b""
    partes, falta = [], n
    while falta > 0:
        bloco = proc.stdout.read(falta)
        if not bloco:
            break
        partes.append(bloco)
        falta -= len(bloco)
    return b"".join(partes)


def _robusto(valores) -> tuple[float, float]:
    x = np.asarray(valores, dtype=np.float64)
    if not len(x):
        return 0.0, 1.0
    med = float(np.median(x))
    return med, float(np.median(np.abs(x - med))) * 1.4826


def _limiar(valores, piso: float, k: float, absoluto: float) -> float:
    """Mudança de imagem fora do normal. Com pouco histórico (ou vídeo quase parado), vale só o limite absoluto."""
    mudou = [v for v in valores if v > 0.5]  # com quadros-chave, segundos repetidos têm diferença zero
    if len(mudou) < 20:
        return absoluto
    med, esc = _robusto(mudou)
    return max(piso, med + k * max(esc, 2.0))


def _audio_por_segundo(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Volume (dB) e chance de ser voz em cada segundo. Tiro e explosão têm espectro 'chiado' e contam pouco como voz."""
    total = len(audio) // TAXA_AUDIO
    volume, voz = np.zeros(total), np.zeros(total)
    janela = np.hanning(TAXA_AUDIO // 2)
    freqs = np.fft.rfftfreq(len(janela), 2 / TAXA_AUDIO)
    faixa = (freqs >= 200) & (freqs <= 3400)
    for s in range(total):
        q = audio[s * TAXA_AUDIO:(s + 1) * TAXA_AUDIO].astype(np.float32) / 32768
        volume[s] = 20 * np.log10(np.sqrt(np.mean(q ** 2)) + 1e-5)
        pot = np.abs(np.fft.rfft(q[::2][:len(janela)] * janela)) ** 2 + 1e-12
        na_faixa = pot[faixa]
        chiado = np.exp(np.mean(np.log(na_faixa))) / np.mean(na_faixa)
        voz[s] = (na_faixa.sum() / pot.sum()) * (1 - chiado)
    return volume, voz


class Detector:
    """Guarda só o histórico resumido (um número por segundo) para saber o que é normal nesta live."""

    def __init__(self, webcam: tuple | None) -> None:
        self.webcam = webcam
        self.db, self.vis, self.cam = deque(maxlen=HISTORICO), deque(maxlen=HISTORICO), deque(maxlen=HISTORICO)
        self.quadro: np.ndarray | None = None

    def _diferencas(self, quadros: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
        dif, cam = np.zeros(n), np.zeros(n)
        if self.webcam:
            x, y, w, h = self.webcam
            x0, y0 = int(x * LARG), int(y * ALT)
            x1, y1 = max(x0 + 2, int((x + w) * LARG)), max(y0 + 2, int((y + h) * ALT))
        for s in range(min(n, len(quadros))):
            atual = quadros[s].astype(np.int16)
            if self.quadro is not None:
                d = np.abs(atual - self.quadro)
                dif[s] = float(d.mean())
                if self.webcam:
                    cam[s] = float(d[y0:y1, x0:x1].mean())
            self.quadro = atual
        return dif, cam

    def janela(self, t0: float, audio: np.ndarray, quadros: np.ndarray | None) -> tuple[list[dict], list[float]]:
        db, voz = _audio_por_segundo(audio)
        n = len(db)
        dif, cam = self._diferencas(quadros, n) if quadros is not None and len(quadros) else (np.zeros(n), np.zeros(n))
        med_db, esc_db = _robusto(list(self.db) + list(db))
        lim_v = _limiar(list(self.vis) + list(dif), 18.0, 4.0, 30.0)
        lim_c = _limiar(list(self.cam) + list(cam), 12.0, 3.5, 20.0)
        cenas = [s for s in range(n) if dif[s] > 0.5 and dif[s] >= lim_v]
        webcam = [s for s in range(n) if self.webcam and cam[s] > 0.5 and cam[s] >= lim_c]
        momentos = []
        for s in range(n):
            z = (db[s] - med_db) / max(esc_db, 2.0)
            if z < 2.5 or db[s] < -45:
                continue
            if s > 0 and db[s - 1] >= db[s] and (db[s - 1] - med_db) / max(esc_db, 2.0) >= 2.5:
                continue  # o pico é o primeiro segundo alto: não repete o mesmo grito
            falou = voz[s] >= VOZ_MIN
            motivos = [f"{'Voz' if falou else 'Som'} {db[s] - med_db:+.0f} dB acima do normal"]
            nota = 35 * min(z, 6) / 6 + (15 if falou else 0)
            if any(abs(c - s) <= 3 for c in cenas):
                motivos.append("mudança de cena")
                nota += 20
            if falou and any(abs(c - s) <= 2 for c in webcam):
                motivos.append("reação na webcam")
                nota += 30
            tipo = "reacao" if "reação na webcam" in motivos else "voz" if falou else "som"
            momentos.append({"pico": round(t0 + s, 1), "nota": int(min(100, round(nota))), "motivos": motivos, "tipo": tipo})
        self.db.extend(db)
        self.vis.extend(dif)
        self.cam.extend(cam)
        return momentos, [round(t0 + s, 1) for s in cenas]


def _juntar(sugestoes: list[dict], m: dict) -> dict | None:
    """Picos a menos de 20 s viram uma sugestão só. Devolve a sugestão nova, se criou uma."""
    if sugestoes and m["pico"] - sugestoes[-1]["pico_final"] <= JUNTAR:
        s = sugestoes[-1]
        s["fim"] = round(min(s["inicio"] + MAX_CORTE, max(s["fim"], m["pico"] + DEPOIS)), 1)
        s["pico_final"] = m["pico"]
        if m["nota"] > s["nota"]:
            s.update(nota=m["nota"], pico=m["pico"], tipo=m["tipo"])
        s["motivos"] = list(dict.fromkeys(s["motivos"] + m["motivos"]))[:6]
        return None
    s = {"pico": m["pico"], "pico_final": m["pico"], "inicio": round(max(0.0, m["pico"] - ANTES), 1), "fim": round(m["pico"] + DEPOIS, 1),
         "nota": m["nota"], "motivos": m["motivos"], "tipo": m["tipo"], "fala": ""}
    sugestoes.append(s)
    del sugestoes[:-MAX_SUGESTOES]
    return s


class Transcritor:
    """Gancho opcional: transcreve só os trechos sugeridos, neste processo separado (nunca no painel)."""

    def __init__(self, modelo: str) -> None:
        self.modelo, self.whisper = modelo, None

    def __call__(self, audio: np.ndarray) -> str:
        if self.whisper is None:
            from .transcricao import _carregar  # só carrega o Whisper se o usuário pediu
            self.whisper = _carregar(self.modelo)
        segmentos, _ = self.whisper.transcribe(audio.astype(np.float32) / 32768, language="pt", vad_filter=True, beam_size=1,
                                               condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segmentos)[:400]


def _pai_vivo(pid: int) -> bool:
    if not pid or sys.platform != "win32":
        return True
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not h:
        return False
    try:
        return k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT: ainda rodando
    finally:
        k.CloseHandle(h)


def _vigiar(a: argparse.Namespace, procs: list, fim: threading.Event, motivo: dict) -> None:
    """Encerra a leitura quando o painel fecha ou, com --seguir, quando o arquivo passa 2 min sem crescer."""
    tamanho, desde = -1, time.time()
    while not fim.wait(5):
        if not _pai_vivo(a.pai):
            motivo["texto"] = "pai"
        elif a.seguir:
            try:
                atual = os.path.getsize(a.arquivo)
            except OSError:
                atual = tamanho
            if atual != tamanho:
                tamanho, desde = atual, time.time()
            elif time.time() - desde >= ESPERA_CRESCER:
                motivo["texto"] = "parou"
        if motivo.get("texto"):
            for p in procs:
                if p and p.poll() is None:
                    p.kill()  # o pipe fecha e a última janela, mesmo incompleta, é analisada
            return


def analisar(a: argparse.Namespace) -> None:
    estado = ler_estado()
    if estado.get("id") != a.id:
        estado = {"id": a.id}
    estado.update(estado="rodando", arquivo=a.arquivo, janela=a.janela, seguir=a.seguir, webcam=a.webcam, visual=a.visual,
                  transcrever=a.transcrever, inicio_arquivo=a.inicio, processado=a.inicio, janelas=0, sugestoes=[], cenas=[],
                  mensagem="Lendo o arquivo", pid=os.getpid(), comecou=time.time())
    _gravar(estado)
    som = _fluxo(a.arquivo, a.inicio, a.seguir, False, a.visual)
    img = _fluxo(a.arquivo, a.inicio, a.seguir, True, a.visual)
    detector = Detector(WEBCAMS.get(a.webcam))
    transcrever = Transcritor(a.transcrever) if a.transcrever else None
    anterior = np.zeros(0, dtype=np.int16)
    bytes_audio, bytes_img = a.janela * TAXA_AUDIO * 2, a.janela * FPS * LARG * ALT
    t0 = a.inicio
    fim, motivo = threading.Event(), {}
    threading.Thread(target=_vigiar, args=(a, [som, img], fim, motivo), daemon=True).start()
    try:
        while True:
            bruto = _ler(som, bytes_audio)
            if len(bruto) < TAXA_AUDIO * 2:  # menos de 1 s: o arquivo acabou, parou de crescer ou o painel fechou
                final = {"pai": ("parada", "O painel foi fechado."),
                         "parou": ("concluida", f"O arquivo parou de crescer por {ESPERA_CRESCER // 60} min: gravação encerrada.")}
                fase, texto = final.get(motivo.get("texto"), ("concluida", "Arquivo analisado até o fim."))
                estado.update(estado=fase, mensagem=texto)
                break
            audio = np.frombuffer(bruto[:len(bruto) // 2 * 2], dtype=np.int16)
            quadros = None
            if img is not None:
                cru = _ler(img, bytes_img)
                if cru:
                    quadros = np.frombuffer(cru[:len(cru) // (LARG * ALT) * LARG * ALT], dtype=np.uint8).reshape(-1, ALT, LARG)
                else:
                    img = None  # sem vídeo (ou acabou antes): segue só com o áudio
            momentos, cenas = detector.janela(t0, audio, quadros)
            for m in momentos:
                nova = _juntar(estado["sugestoes"], m)
                if nova and transcrever:
                    junto = np.concatenate([anterior, audio])
                    base = t0 - len(anterior) / TAXA_AUDIO
                    trecho = junto[int(max(0, nova["inicio"] - base) * TAXA_AUDIO):int(max(0, nova["fim"] - base) * TAXA_AUDIO)]
                    try:
                        nova["fala"] = transcrever(trecho)
                    except Exception as erro:  # o gancho é opcional: falha nele não para a análise
                        nova["fala"] = f"(transcrição indisponível: {erro})"[:200]
                        transcrever = None
            estado["cenas"] = (estado["cenas"] + cenas)[-100:]
            t0 += len(audio) / TAXA_AUDIO
            anterior = audio
            estado.update(processado=round(t0, 1), janelas=estado["janelas"] + 1,
                          mensagem=f"Janela {estado['janelas'] + 1} analisada ({len(estado['sugestoes'])} sugestões)")
            _gravar(estado)
    except Exception as erro:
        estado.update(estado="erro", mensagem=f"Falha na análise: {erro}")
    finally:
        fim.set()
        for p in (som, img):
            if p and p.poll() is None:
                p.kill()
        estado.update(terminou=time.time(), pid=0)
        _gravar(estado)


# ---------------------------------------------------------------- controle pelo painel

class Analisador:
    """Uma análise por vez, em subprocesso de prioridade baixa. O painel só lê o estado gravado em disco."""

    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.proc: subprocess.Popen | None = None

    def rodando(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def iniciar(self, d: dict) -> dict:
        if not d.get("autorizado"):
            raise ValueError("Confirme que o arquivo é uma gravação sua ou que você tem autorização para usá-lo.")
        caminho = Path(str(d.get("caminho") or "").strip().strip('"'))
        if not caminho.is_file():
            raise ValueError("Arquivo não encontrado. Escolha a gravação do OBS (MKV ou MP4) neste PC.")
        if caminho.suffix.lower() not in EXT:
            raise ValueError("Use um vídeo MKV, MP4, MOV, TS, FLV ou WEBM.")
        janela = int(d.get("janela") or 25)
        if janela not in JANELAS:
            raise ValueError("A janela precisa ter 20, 25 ou 30 segundos.")
        webcam = str(d.get("webcam") or "")
        if webcam and webcam not in WEBCAMS:
            raise ValueError("Posição da webcam inválida.")
        visual = "completo" if d.get("visual") == "completo" else "leve"
        inicio = max(0.0, float(d.get("inicio") or 0))
        with self.trava:
            if self.rodando():
                raise ValueError("Já existe uma análise rodando. Pare a atual antes de começar outra.")
            ident = uuid.uuid4().hex[:10]
            cmd = [sys.executable, "-m", "cortes.ao_vivo", "--arquivo", str(caminho.resolve()), "--janela", str(janela), "--id", ident,
                   "--pai", str(os.getpid()), "--visual", visual, "--inicio", str(inicio)]
            if webcam:
                cmd += ["--webcam", webcam]
            if d.get("seguir"):
                cmd.append("--seguir")
            if d.get("transcrever"):
                cmd += ["--transcrever", "small"]
            _gravar({"id": ident, "estado": "iniciando", "arquivo": str(caminho.resolve()), "janela": janela, "autorizado": True,
                     "seguir": bool(d.get("seguir")), "webcam": webcam, "visual": visual, "sugestoes": [], "cenas": [],
                     "processado": inicio, "janelas": 0, "mensagem": "Abrindo o processo de análise", "comecou": time.time()})
            with ARQ_LOG.open("w", encoding="utf-8") as log:
                self.proc = subprocess.Popen(cmd, cwd=BASE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
                                             creationflags=PRIORIDADE, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return self.estado()

    def estado(self) -> dict:
        e = ler_estado()
        vivo = self.rodando()
        if not vivo and e.get("estado") in ("iniciando", "rodando"):
            if self.proc is not None:  # o processo morreu sem dizer por quê: mostra o fim do log
                try:
                    fim = [l for l in ARQ_LOG.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()][-1:]
                except OSError:
                    fim = []
                e.update(estado="erro", mensagem="A análise parou de repente. " + (fim[0][:200] if fim else ""))
            else:  # painel reiniciado no meio de uma análise antiga
                e.update(estado="parada", mensagem="A análise foi interrompida quando o painel fechou.")
            _gravar(e)
        return {**e, "rodando": vivo, "janelas_validas": list(JANELAS), "webcams": list(WEBCAMS)}

    def parar(self) -> dict:
        with self.trava:
            if self.rodando():
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.proc.wait(10)
                e = ler_estado()
                e.update(estado="parada", mensagem="Análise parada por você.", pid=0, terminou=time.time())
                _gravar(e)
        return self.estado()

    def criar_corte(self, d: dict, fila) -> dict:
        from . import vods  # só no painel: o processo de análise não precisa do editor nem das plataformas

        e = ler_estado()
        if not e.get("autorizado"):
            raise ValueError("Esta análise não tem a confirmação de autorização do arquivo.")
        try:
            s = e["sugestoes"][int(d.get("indice", -1))]
        except (IndexError, KeyError, ValueError):
            raise ValueError("Sugestão não encontrada. Atualize a lista.") from None
        info = vods.abrir_arquivo(e["arquivo"])
        dados = {"tipo": "arquivo", "id": info["id"], "inicio": s["inicio"], "fim": s["fim"],
                 "titulo": str(d.get("titulo") or "").strip()[:200] or s.get("fala", "")[:120], "streamer": str(d.get("streamer") or "")[:60]}
        return fila.adicionar("corte", f"Corte da sugestão em {int(s['pico'] // 60)}:{int(s['pico'] % 60):02d}",
                              lambda t: vods.criar_corte(dados, t)).publico()


analisador = Analisador()


RISO_CHAT = re.compile(r"k{4,}|(?:ha){3,}|(?:rs){3,}|(?:ja){3,}|kekw|lul|omegalul|lmao|😂|🤣", re.I)
REACAO_CHAT = re.compile(r"\b(?:caralho|porra|mds|meu deus|que isso|nossa|absurdo|insano|mito|lend[aá]rio|pog\w*|wtf|omg|cringe)\b|w+o+w+|😱|😮|🔥", re.I)
PEDE_CLIP = re.compile(r"\bclip(?:a|e|ou|ar|em)?\b|\bcorta\b|\bcortem\b", re.I)


def _chave(fonte: str, pico: float) -> str:
    return f"{fonte}:{round(float(pico) * 10)}"  # décimos de segundo: a mesma chave no Python e no navegador


class ChatMomentos:
    """Lê o chat junto com a gravação. Chat acelerando, enchendo de risada, de reação ou pedindo "clipa" vira momento com nota.
    O chat reage alguns segundos depois do lance: o momento é marcado ~6 s antes da reação."""

    REACAO_ATRASO, ANTES, DEPOIS, RECARGA = 6, 20, 8, 30

    def __init__(self) -> None:
        self.msgs: deque = deque()  # (t, riso, reacao, pede_clip)
        self.avaliado = 0.0
        self.ultimo: dict | None = None
        self.momentos: list[dict] = []
        self.total = 0

    def registrar(self, t: float, texto: str) -> dict | None:
        self.total += 1
        self.msgs.append((t, bool(RISO_CHAT.search(texto)), bool(REACAO_CHAT.search(texto)), bool(PEDE_CLIP.search(texto))))
        while self.msgs[0][0] < t - 180:
            self.msgs.popleft()
        if t - self.avaliado < 2:  # avalia no máximo a cada 2 s: chat grande não pesa
            return None
        self.avaliado = t
        lista = list(self.msgs)
        recentes = [m for m in lista if m[0] > t - 10]
        base = [m for m in lista if m[0] <= t - 10]
        if len(recentes) < 8 or not base or t - 10 - base[0][0] < 45:  # precisa de 45 s de chat "normal" para comparar
            return None
        ritmo = len(recentes) / max(len(base) / (t - 10 - base[0][0]) * 10, 1.0)
        riso = sum(m[1] for m in recentes) / len(recentes)
        reacao = sum(m[2] for m in recentes) / len(recentes)
        clipa = sum(m[3] for m in recentes)
        if ritmo < 2.5 and riso < 0.35 and reacao < 0.3 and clipa < 3:
            return None
        nota = int(min(100, 25 * min(ritmo / 4, 1) + 35 * min(riso / 0.6, 1) + 25 * min(clipa / 6, 1) + 15 * min(reacao / 0.5, 1) + 10))
        motivos = [f for f in (ritmo >= 1.5 and f"chat {ritmo:.1f}x mais rápido", riso >= 0.2 and f"{riso:.0%} rindo (kkkk)",
                                clipa >= 2 and f"{clipa} pedindo clip", reacao >= 0.2 and f"{reacao:.0%} reagindo") if f]
        if self.ultimo and t - self.ultimo["t"] < self.RECARGA:  # mesmo lance: fica com a reação mais forte
            if nota > self.ultimo["nota"]:
                self.ultimo.update(nota=nota, motivos=motivos)
            return None
        self.ultimo = {"t": t, "nota": nota, "motivos": motivos, "fonte": "chat"}
        self.momentos.append(self.ultimo)
        del self.momentos[:-60]
        return self.ultimo

    def por_minuto(self, agora: float) -> int:
        return sum(1 for m in list(self.msgs) if m[0] > agora - 60)


class Captura:
    """Grava a live da Twitch ou da Kick (do ponto atual em diante) num arquivo que cresce, e liga a análise em janelas nele.
    Junto, lê o chat (Twitch) e marca os momentos em que ele explode. Com "clipar sozinho", momentos acima da nota viram cortes.
    Só com autorização confirmada; o vídeo fica no PC e os cortes saem direto desse arquivo."""

    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.info: dict = {}
        self.chat: ChatMomentos | None = None
        self.feitos: dict[str, str] = {}  # momento (fonte:pico) -> corte criado ("" enquanto cria)

    def rodando(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self, d: dict) -> dict:
        from .fontes import YTDLP
        if not d.get("autorizado"):
            raise ValueError("Confirme que você tem autorização para gravar e cortar esta live.")
        plataforma = "kick" if str(d.get("plataforma") or "").lower() == "kick" or "kick.com/" in str(d.get("login") or "") else "twitch"
        login = re.sub(r"^https?://(www\.)?(twitch\.tv|kick\.com)/", "", str(d.get("login") or "").strip().lower()).strip("/@ ").split("/")[0]
        if not re.fullmatch(r"[a-z0-9_-]{2,25}" if plataforma == "kick" else r"[a-z0-9_]{3,25}", login):
            raise ValueError(f"Canal da {plataforma.capitalize()} inválido.")
        url = f"https://kick.com/{login}" if plataforma == "kick" else f"https://www.twitch.tv/{login}"
        altura = {"480": 480, "720": 720, "1080": 1080}.get(str(d.get("qualidade") or "720"), 720)
        with self.trava:
            if self.rodando():
                raise ValueError(f"Já estou gravando a live de {self.info.get('login')}. Pare antes de começar outra.")
            if analisador.rodando():
                analisador.parar()
            pasta = DADOS / "ao_vivo"
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo = pasta / f"{login}_{time.strftime('%Y-%m-%d_%H%M')}.ts"
            log = (pasta / "captura.log").open("w", encoding="utf-8")
            self.proc = subprocess.Popen([*YTDLP, "-f", f"best[height<={altura}]/best", "--hls-use-mpegts", "--no-part", "-o", str(arquivo),
                                          url], cwd=BASE, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         creationflags=PRIORIDADE)
            self.info = {"login": login, "plataforma": plataforma, "arquivo": str(arquivo), "comecou": time.time(), "qualidade": f"{altura}p", "erro": "",
                         "inicio_live": str(d.get("inicio_live") or ""), "estado": "conectando", "auto": max(0, min(int(d.get("auto") or 0), 100))}
            self.chat, self.feitos = ChatMomentos(), {}
        if plataforma == "twitch":  # o chat da Twitch já é lido pelo painel (só leitura); a gravação passa a escutar este canal
            from .canais import canais
            canais.ouvintes = {login: self._ouvir}
            threading.Thread(target=canais._ajustar_chats, daemon=True).start()
        threading.Thread(target=self._ligar_analise, args=(arquivo, bool(d.get("transcrever"))), daemon=True).start()
        threading.Thread(target=self._clipar_sozinho, args=(arquivo,), daemon=True).start()
        return self.estado()

    # ---------------------------------------------- momentos do chat e cortes automáticos

    def _ouvir(self, t: float, texto: str) -> None:
        chat = self.chat
        m = chat.registrar(t, texto) if chat else None
        if m:
            threading.Thread(target=self._marcar, args=(m,), daemon=True).start()

    def _marcar(self, m: dict) -> None:
        """Converte o horário da reação no ponto da gravação: o fim do arquivo que cresce é "agora"."""
        from .editor import sondar
        try:
            dur = float(sondar(Path(self.info["arquivo"]))["dur"])
        except Exception:
            return
        pico = dur - (time.time() - (m["t"] - ChatMomentos.REACAO_ATRASO))
        m.update(pico=round(max(0.0, pico), 1), inicio=round(max(0.0, pico - ChatMomentos.ANTES), 1), fim=round(max(1.0, pico + ChatMomentos.DEPOIS), 1))

    def _criar(self, chave: str, s: dict, fila) -> object:
        """Cria o corte de um momento (do chat ou da análise) e lembra qual corte saiu dele."""
        from . import vods
        info = vods.abrir_arquivo(self.info["arquivo"])
        login = self.info["login"]
        dados = {"tipo": "arquivo", "id": info["id"], "inicio": s["inicio"], "fim": s["fim"], "streamer": login,
                 "plataforma": {"kick": "Kick"}.get(self.info.get("plataforma", ""), "Twitch"),
                 "titulo": (s.get("fala") or "")[:120] or f"{login}: {', '.join(s.get('motivos') or [])[:100]}"}
        self.feitos[chave] = ""

        def trabalho(t):
            r = vods.criar_corte(dados, t)
            self.feitos[chave] = r.get("corte", "")
            return r
        return fila.adicionar("corte", f"Corte de {login} ({s.get('nota', '')} pts)", trabalho, f"aovivo:{chave}")

    def cortar_momento(self, d: dict, fila) -> dict:
        chat = self.chat
        try:
            m = chat.momentos[int(d.get("indice", -1))]
        except (AttributeError, IndexError, ValueError):
            raise ValueError("Momento não encontrado. Atualize a lista.") from None
        if "fim" not in m:
            raise ValueError("Esse momento ainda está sendo localizado na gravação. Tente em alguns segundos.")
        return self._criar(_chave("chat", m["pico"]), m, fila).publico()

    def _clipar_sozinho(self, arquivo: Path) -> None:
        """Com "clipar sozinho" ligado, todo momento (chat ou análise) com nota acima do limite vira corte, quando o trecho já foi gravado."""
        from .editor import sondar
        from .tarefas import fila
        while self.rodando() or analisador.rodando() or self.info.get("estado") == "conectando":
            time.sleep(5)
            limite = self.info.get("auto") or 0
            if not limite or not arquivo.is_file():
                continue
            try:
                dur = float(sondar(arquivo)["dur"])
            except Exception:
                continue
            e = ler_estado()
            candidatos = [(_chave("chat", m["pico"]), m) for m in list(self.chat.momentos if self.chat else []) if "fim" in m]
            if e.get("arquivo") == str(arquivo):  # sugestão da análise já fechada (não vai mais crescer)
                candidatos += [(_chave("analise", s["pico"]), s) for s in e.get("sugestoes", []) if e.get("processado", 0) - s["pico_final"] > JUNTAR + 5]
            for chave, s in candidatos:
                if s["nota"] >= limite and chave not in self.feitos and s["fim"] <= dur - 1:
                    try:
                        self._criar(chave, s, fila)
                    except ValueError:
                        self.feitos[chave] = "erro"

    def configurar_auto(self, d: dict) -> dict:
        if not self.info:
            raise ValueError("Nenhuma live sendo gravada.")
        self.info["auto"] = max(0, min(int(d.get("nota") or 0), 100))
        return self.estado()

    def _ligar_analise(self, arquivo: Path, transcrever: bool) -> None:
        """Espera o arquivo ter alguns segundos de live e começa a análise acompanhando o crescimento."""
        for _ in range(180):
            if not self.rodando():
                break
            if arquivo.is_file() and arquivo.stat().st_size > 3_000_000:
                try:
                    analisador.iniciar({"caminho": str(arquivo), "autorizado": True, "janela": 25, "visual": "leve", "seguir": True, "transcrever": transcrever})
                    self.info["estado"] = "gravando"
                except ValueError as e:
                    self.info.update(estado="erro", erro=str(e))
                return
            time.sleep(1)
        try:
            fim = [l for l in (DADOS / "ao_vivo" / "captura.log").read_text(encoding="utf-8", errors="replace").splitlines() if "ERROR" in l][-1:]
        except OSError:
            fim = []
        motivo = fim[0].split("ERROR:", 1)[-1].strip()[:200] if fim else "a live não começou a chegar"
        self.info.update(estado="erro", erro=f"Não consegui gravar a live: {motivo}. Ela pode ter acabado, ser só para inscritos ou ter restrição de região.")
        self.parar(manter_erro=True)

    def parar(self, manter_erro: bool = False) -> dict:
        with self.trava:
            if self.rodando():
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if self.info and not manter_erro:
                self.info.update(estado="parada", terminou=time.time())
        from .canais import canais
        canais.ouvintes = {}
        return self.estado()  # a análise percebe que o arquivo parou de crescer e termina sozinha em 2 min

    def clipar(self, d: dict, fila) -> dict:
        """Clipar agora: corta os últimos N segundos da gravação em andamento e cria o corte.
        É o "Criar clip" de quem não tem API de clipes (Kick) e funciona igual para a Twitch."""
        from . import vods
        if not self.info or not Path(self.info["arquivo"]).is_file():
            raise ValueError("Nenhuma live sendo gravada. Clique em Gravar e clipar na live primeiro.")
        seg = max(10, min(int(d.get("segundos") or 30), 120))
        info = vods.abrir_arquivo(self.info["arquivo"])
        total = float(info.get("duracao") or 0)
        if total < seg + 3:
            raise ValueError(f"A gravação ainda tem só {int(total)} s. Espere mais um pouco e clique de novo.")
        login, plataforma = self.info["login"], {"kick": "Kick"}.get(self.info.get("plataforma", ""), "Twitch")
        fim = total - 1  # o fim estimado do arquivo que ainda cresce; 1 s de folga
        dados = {"tipo": "arquivo", "id": info["id"], "inicio": max(0.0, fim - seg), "fim": fim, "plataforma": plataforma, "streamer": login,
                 "titulo": str(d.get("titulo") or "").strip()[:200] or f"Clip de {login} às {time.strftime('%H:%M')}"}
        return fila.adicionar("corte", f"Clipando os últimos {seg} s de {login}", lambda t: vods.criar_corte(dados, t)).publico()

    def estado(self) -> dict:
        if not self.info:
            return {}
        arq = Path(self.info["arquivo"])
        tam = arq.stat().st_size if arq.is_file() else 0
        if self.info.get("estado") in ("conectando", "gravando") and not self.rodando():
            self.info["estado"] = "encerrada"  # a live acabou ou caiu
        chat = self.chat
        momentos = [{**{k: v for k, v in m.items() if k != "t"}, "quando": m["t"], "indice": i, "corte": self.feitos.get(_chave("chat", m["pico"])) if "pico" in m else None}
                    for i, m in enumerate(list(chat.momentos if chat else []))]
        return {**self.info, "rodando": self.rodando(), "mb": round(tam / 1048576), "minutos": round((time.time() - self.info["comecou"]) / 60, 1),
                "chat": {"lido": self.info.get("plataforma") == "twitch", "msgs_min": chat.por_minuto(time.time()) if chat else 0,
                         "total": chat.total if chat else 0, "momentos": momentos[::-1][:30]},
                "feitos": {k: v for k, v in self.feitos.items() if k.startswith("analise:")}}


captura = Captura()


def main() -> None:
    p = argparse.ArgumentParser(description="Análise em janelas de um arquivo autorizado (gravação própria).")
    p.add_argument("--arquivo", required=True)
    p.add_argument("--janela", type=int, default=25, choices=JANELAS)
    p.add_argument("--id", default=uuid.uuid4().hex[:10])
    p.add_argument("--pai", type=int, default=0)
    p.add_argument("--inicio", type=float, default=0.0)
    p.add_argument("--webcam", default="", choices=["", *WEBCAMS])
    p.add_argument("--visual", default="leve", choices=["leve", "completo"])
    p.add_argument("--seguir", action="store_true", help="espera o arquivo crescer (OBS gravando)")
    p.add_argument("--transcrever", default="", help="modelo do Whisper para os trechos sugeridos (opcional)")
    analisar(p.parse_args())


if __name__ == "__main__":
    main()
