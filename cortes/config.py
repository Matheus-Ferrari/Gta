"""Caminhos e ajustes gerais. Tudo pesado fica no D:, porque o C: tem pouco espaço."""
from __future__ import annotations

import json
import os
import re
import shutil
import site
from pathlib import Path


def _pasta_dados() -> Path:
    """D:/Cortes quando existe o D: (o C: costuma ter pouco espaço); senão, ViceClips na pasta do usuário. CORTES_DADOS escolhe outra."""
    if os.environ.get("CORTES_DADOS"):
        return Path(os.environ["CORTES_DADOS"])
    return Path(r"D:\Cortes") if Path("D:/").exists() else Path.home() / "ViceClips"


DADOS = _pasta_dados()
LIVES = DADOS / "lives"
MODELOS = DADOS / "modelos"
TAXA_AUDIO = 16000


def ler_json(caminho: Path, padrao=None):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(caminho: Path, dados) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temp = caminho.with_name(caminho.name + ".tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    temp.replace(caminho)


def ffmpeg() -> str:
    achados = sorted((DADOS / "tools" / "ffmpeg").glob("*/bin/ffmpeg.exe"))
    if achados:
        return str(achados[-1])
    caminho = shutil.which("ffmpeg")
    if not caminho:
        raise SystemExit("ffmpeg não encontrado. Veja o README.")
    return caminho


def ffprobe() -> str:
    return str(Path(ffmpeg()).with_name("ffprobe.exe"))


def preparar_gpu() -> None:
    """Deixa as DLLs da CUDA visíveis e guarda os modelos do Whisper no D:."""
    os.environ.setdefault("HF_HOME", str(MODELOS))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    for base in site.getsitepackages():
        for sub in ("cublas", "cudnn", "cuda_nvrtc"):
            pasta = Path(base) / "nvidia" / sub / "bin"
            if pasta.exists():
                os.add_dll_directory(str(pasta))
                os.environ["PATH"] = str(pasta) + os.pathsep + os.environ["PATH"]


def twitch_downloader() -> str | None:
    exe = DADOS / "tools" / "TwitchDownloader" / "TwitchDownloaderCLI.exe"
    return str(exe) if exe.exists() else None


def pasta_da_live(nome: str, plataforma: str = "Arquivos") -> Path:
    nome = re.sub(r"[^\w-]+", "_", nome, flags=re.UNICODE).strip("_")[:80] or "live"
    pasta = LIVES / plataforma / nome
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta
