"""Lê lives gravadas pelo link, usando o yt-dlp. Só o áudio é baixado inteiro."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .config import twitch_downloader

YTDLP = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--ignore-config", "--no-playlist"]
FORMATO_AUDIO = "bestaudio/worst"
FORMATO_VIDEO = "best[height<=1440]/bestvideo[height<=1440]+bestaudio/best"  # a maior qualidade original até 1440p


def eh_link(texto: str) -> bool:
    return texto.lower().startswith(("http://", "https://"))


def _rodar(*args: str) -> str:
    r = subprocess.run([*YTDLP, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        linhas = [l for l in r.stderr.splitlines() if l.strip()]
        if "subscriber-only" in r.stderr:
            raise SystemExit("Essa gravação é exclusiva para inscritos do canal. Use uma gravação pública.")
        raise SystemExit(f"Não consegui ler esse link: {linhas[-1] if linhas else 'erro desconhecido'}")
    return r.stdout


def info(url: str) -> dict:
    return json.loads(_rodar("-J", "--skip-download", url))


def enderecos(url: str, formato: str) -> list[str]:
    """Endereços diretos do vídeo. Podem ser dois quando imagem e som vêm separados."""
    return [l.strip() for l in _rodar("-g", "-f", formato, url).splitlines() if l.strip()]


def plataforma(dados: dict) -> str:
    chave = dados.get("extractor_key", "").lower()
    for prefixo, nome in (("twitch", "Twitch"), ("kick", "Kick"), ("youtube", "YouTube")):
        if chave.startswith(prefixo):
            return nome
    return "Outros"


def baixar_chat_twitch(video_id: str, destino: Path, inicio: float, duracao: float) -> bool:
    """Baixa o chat do trecho analisado. Sem chat o corte ainda sai, só com a voz."""
    if destino.exists():
        return True
    exe = twitch_downloader()
    if not exe:
        return False
    temp = destino.with_name("chat_baixando.json")
    r = subprocess.run(
        [exe, "chatdownload", "--id", video_id, "-o", str(temp), "-b", f"{int(inicio)}s",
         "-e", f"{int(inicio + duracao) + 1}s", "--collision", "Overwrite", "--banner", "false", "--log-level", "Error"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not temp.exists():
        temp.unlink(missing_ok=True)
        return False
    temp.replace(destino)
    return True
