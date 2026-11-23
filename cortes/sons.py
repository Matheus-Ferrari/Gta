"""Biblioteca local de sons por categoria. Os sons iniciais são sintetizados aqui (originais, sem licença de terceiros)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from .config import ffprobe
from .efeitos import SONS

TAXA = 48000
CATEGORIAS = {"impacto": "Impacto", "suspense": "Suspense", "panico": "Pânico", "comedia": "Comédia", "falha": "Falha engraçada",
              "revelacao": "Revelação", "reacao": "Reação inesperada", "musica": "Músicas (suas)"}
EXTENSOES = {".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac", ".opus"}
SEM_JANELA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * TAXA)) / TAXA


def _ruido(n: int, semente: int) -> np.ndarray:
    return np.random.default_rng(semente).uniform(-1, 1, n)


def _passa_baixa(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


def _env(t: np.ndarray, ataque: float, queda: float) -> np.ndarray:
    return np.clip(t / max(ataque, 1e-4), 0, 1) * np.exp(-np.clip(t - ataque, 0, None) / queda)


def _impacto() -> np.ndarray:
    t = _t(1.6)
    grave = np.sin(2 * np.pi * (38 * t + 60 * (1 - np.exp(-t * 9)) / 9)) * _env(t, 0.004, 0.42)
    return grave * 0.95 + _passa_baixa(_ruido(len(t), 1), 24) * _env(t, 0.002, 0.07) * 0.8


def _batida() -> np.ndarray:
    t = _t(0.7)
    return np.sin(2 * np.pi * (55 * t + 90 * (1 - np.exp(-t * 20)) / 20)) * _env(t, 0.002, 0.16) + _passa_baixa(_ruido(len(t), 2), 8) * _env(t, 0.001, 0.03) * 0.5


def _suspense() -> np.ndarray:
    t = _t(12)
    base = sum(np.sin(2 * np.pi * f * t + i) * (0.5 + 0.5 * np.sin(2 * np.pi * (0.07 + 0.03 * i) * t)) for i, f in enumerate((55, 58.3, 82.4, 110.7)))
    ar = _passa_baixa(_ruido(len(t), 3), 200) * 2.5 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * t))
    return (base / 4 + ar * 0.25) * np.clip(t / 1.5, 0, 1) * np.clip((12 - t) / 1.5, 0, 1)


def _tensao_crescente() -> np.ndarray:
    t = _t(3)
    f = 180 * np.exp(t * 0.75)
    fase = 2 * np.pi * np.cumsum(f) / TAXA
    return (np.sin(fase) * 0.4 + np.sin(fase * 1.01) * 0.4 + _passa_baixa(_ruido(len(t), 4), 30) * 0.5) * (t / 3) ** 2


def _panico() -> np.ndarray:
    t = _t(8)
    pulso = np.sin(2 * np.pi * 62 * t) * np.exp(-((t * 2.6) % 1) * 7)
    agudo = sum(np.sin(2 * np.pi * f * t) for f in (880, 932.3, 987.8)) / 3 * (0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 5.2 * t))) * 0.22
    return (pulso * 0.8 + agudo) * np.clip(t / 0.4, 0, 1) * np.clip((8 - t) / 1.0, 0, 1)


def _boing() -> np.ndarray:
    t = _t(0.7)
    f = 190 + 260 * np.exp(-t * 5) * (1 + 0.25 * np.sin(2 * np.pi * 14 * t))
    return np.sin(2 * np.pi * np.cumsum(f) / TAXA) * _env(t, 0.005, 0.28)


def _pop() -> np.ndarray:
    t = _t(0.22)
    return np.sin(2 * np.pi * np.cumsum(420 + 900 * np.exp(-t * 40)) / TAXA) * _env(t, 0.002, 0.05)


def _trombone() -> np.ndarray:
    partes = []
    for f, d in ((233.1, 0.36), (220, 0.36), (207.7, 0.36), (196, 1.0)):
        t = _t(d)
        vib = 1 + 0.012 * np.sin(2 * np.pi * 6 * t) * (d > 0.5)
        fase = 2 * np.pi * np.cumsum(f * vib * (1 - 0.04 * t / d * (d > 0.5))) / TAXA
        onda = sum(np.sin(fase * h) / h for h in range(1, 7))
        partes.append(onda * np.clip(t / 0.03, 0, 1) * np.clip((d - t) / (0.25 if d > 0.5 else 0.05), 0, 1))
    return np.concatenate(partes) * 0.5


def _buzina_triste() -> np.ndarray:
    t = _t(0.9)
    fase = 2 * np.pi * np.cumsum(150 - 60 * t) / TAXA
    return np.sign(np.sin(fase)) * 0.35 * _env(t, 0.01, 0.5) + np.sin(fase) * 0.4 * _env(t, 0.01, 0.5)


def _revelacao() -> np.ndarray:
    t = _t(2.4)
    sino = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (1.2 + i * 0.5)) / (i + 1) for i, f in enumerate((523.3, 784, 1046.5, 1568, 2093)))
    brilho = _ruido(len(t), 5) - _passa_baixa(_ruido(len(t), 5), 6)
    return sino * 0.6 + brilho * 0.12 * np.exp(-t * 2.5)


def _subida() -> np.ndarray:
    t = _t(1.8)
    x = _ruido(len(t), 6)
    return (x - _passa_baixa(x, 12)) * (t / 1.8) ** 3 * 0.9 + np.sin(2 * np.pi * np.cumsum(300 + 1400 * (t / 1.8) ** 2) / TAXA) * (t / 1.8) ** 2 * 0.3


def _risco() -> np.ndarray:
    t = _t(0.55)
    x = _ruido(len(t), 7)
    arranhao = (x - _passa_baixa(x, 5)) * np.abs(np.sin(2 * np.pi * (30 - 40 * t) * t)) * _env(t, 0.004, 0.2)
    return arranhao + np.sin(2 * np.pi * np.cumsum(700 - 900 * t) / TAXA) * 0.3 * _env(t, 0.004, 0.15)


def _susto() -> np.ndarray:
    t = _t(1.2)
    acorde = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sign(np.sin(2 * np.pi * f * t)) for f in (311.1, 370, 440, 466.2)) / 6
    return acorde * _env(t, 0.003, 0.35) + _passa_baixa(_ruido(len(t), 8), 20) * _env(t, 0.002, 0.08) * 0.6


ORIGINAIS = {
    "impacto/impacto_grave.wav": _impacto, "impacto/batida_seca.wav": _batida,
    "suspense/suspense_grave.wav": _suspense, "suspense/tensao_crescente.wav": _tensao_crescente,
    "panico/panico_pulsante.wav": _panico,
    "comedia/boing.wav": _boing, "comedia/pop.wav": _pop,
    "falha/trombone_triste.wav": _trombone, "falha/buzina_murcha.wav": _buzina_triste,
    "revelacao/brilho.wav": _revelacao, "revelacao/subida.wav": _subida,
    "reacao/risco_de_disco.wav": _risco, "reacao/susto.wav": _susto,
}


def _gravar(destino: Path, x: np.ndarray) -> None:
    x = x / max(float(np.max(np.abs(x))), 1e-9) * 0.84  # pico em -1,5 dBFS: nunca nasce estourado
    n = min(len(x), int(0.004 * TAXA))
    x[-n:] *= np.linspace(1, 0, n)
    pcm = np.repeat(np.round(x * 32767).astype("<i2"), 2)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(pcm.tobytes())


def garantir() -> None:
    for cat in CATEGORIAS:
        (SONS / cat).mkdir(parents=True, exist_ok=True)
    for rel, gerar in ORIGINAIS.items():
        if not (SONS / rel).exists():
            _gravar(SONS / rel, gerar())


def _duracao(arq: Path) -> float:
    if arq.suffix.lower() == ".wav":
        try:
            with wave.open(str(arq), "rb") as w:
                return w.getnframes() / w.getframerate()
        except (wave.Error, OSError, EOFError):
            pass
    r = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arq)],
                       capture_output=True, text=True, creationflags=SEM_JANELA)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


_cache: dict[str, tuple[float, float]] = {}


def listar() -> dict:
    garantir()
    itens = []
    for cat in CATEGORIAS:
        for arq in sorted((SONS / cat).iterdir()):
            if arq.suffix.lower() not in EXTENSOES:
                continue
            rel, mt = f"{cat}/{arq.name}", arq.stat().st_mtime
            if _cache.get(rel, (0, 0))[0] != mt:
                _cache[rel] = (mt, round(_duracao(arq), 3))
            if _cache[rel][1] > 0:
                itens.append({"arquivo": rel, "nome": arq.stem.replace("_", " "), "categoria": cat, "dur": _cache[rel][1],
                              "origem": "Vice Clips (original)" if rel in ORIGINAIS else "Seu arquivo", "url": "/som/" + rel})
    return {"categorias": CATEGORIAS, "sons": itens, "pasta": str(SONS)}


def importar(caminho: str, categoria: str) -> dict:
    """Copia um arquivo de áudio do usuário para a biblioteca. A licença de uso é responsabilidade de quem envia."""
    origem = Path(caminho)
    if categoria not in CATEGORIAS:
        raise ValueError("Categoria inválida.")
    if not origem.is_file() or origem.suffix.lower() not in EXTENSOES:
        raise ValueError("Escolha um arquivo de áudio (WAV, MP3, OGG, M4A, FLAC).")
    nome = re.sub(r"[^\w.-]+", "_", origem.name)[:80]
    destino = SONS / categoria / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origem, destino)
    if _duracao(destino) <= 0:
        destino.unlink(missing_ok=True)
        raise ValueError("Não consegui ler este áudio.")
    return listar()
