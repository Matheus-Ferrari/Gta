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
