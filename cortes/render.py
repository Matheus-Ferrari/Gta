"""Monta o vídeo vertical 1080x1920 com legenda palavra por palavra."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .config import TAXA_AUDIO, ffmpeg

CABECALHO = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Corte,Arial Black,76,&H00FFFFFF,&H000000FF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _tempo(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _grupos(palavras: list[dict]) -> list[list[dict]]:
    grupos, atual = [], []
    for p in palavras:
        quebra = atual and (len(atual) >= 3 or sum(len(x["p"]) for x in atual) + len(p["p"]) > 20
                            or p["i"] - atual[-1]["f"] > 0.4 or atual[-1]["p"][-1] in ".!?…")
        if quebra:
            grupos.append(atual)
            atual = []
        atual.append(p)
    return grupos + [atual] if atual else grupos


def gerar_legenda(palavras: list[dict], inicio: float, destino: Path) -> None:
    linhas = [CABECALHO]
    grupos = _grupos(palavras)
    for g, grupo in enumerate(grupos):
        proximo = grupos[g + 1][0]["i"] if g + 1 < len(grupos) else float("inf")
        for n, p in enumerate(grupo):
            ate = grupo[n + 1]["i"] if n + 1 < len(grupo) else min(p["f"] + 0.15, proximo)
            texto = " ".join(
                (r"{\c&H00E5FF&}" + x["p"].upper() + r"{\c&HFFFFFF&}") if m == n else x["p"].upper()
                for m, x in enumerate(grupo)
            ).replace("\n", " ")
            linhas.append(f"Dialogue: 0,{_tempo(p['i'] - inicio)},{_tempo(ate - inicio)},Corte,,0,0,0,,{texto}\n")
    destino.write_text("".join(linhas), encoding="utf-8")


def _filtro(webcam: tuple[float, float, float, float] | None) -> str:
    if webcam:
        x, y, l, a = webcam
        return (
            f"[0:v]crop=iw*{l}:ih*{a}:iw*{x}:ih*{y},scale=1080:640:force_original_aspect_ratio=increase,crop=1080:640[cam];"
            "[0:v]crop='min(iw,ih*27/32)':'min(ih,iw*32/27)',scale=1080:1280[jogo];"
            "[cam][jogo]vstack=inputs=2,ass=legenda.ass,format=yuv420p[v]"
        )
    return "[0:v]crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,ass=legenda.ass,format=yuv420p[v]"


MARGEM = 25.0


def baixar_trecho(entradas: list[str], inicio: float, duracao: float, destino: Path) -> None:
    """Baixa só o pedaço do corte, com folga, porque vídeo online não para no segundo exato."""
    leitura = []
    for entrada in entradas:
        leitura += ["-ss", f"{max(inicio - MARGEM, 0):.2f}", "-t", f"{duracao + 2 * MARGEM:.2f}", "-i", entrada]
    subprocess.run(
        [ffmpeg(), "-y", "-loglevel", "error", *leitura, "-map", "0:v:0", "-map", f"{len(entradas) - 1}:a:0",
         "-c", "copy", str(destino)],
        check=True,
    )


def localizar(trecho: Path, audio: np.ndarray, inicio: float, duracao: float) -> float | None:
    """Acha, pelo som, em que segundo do trecho baixado o corte começa."""
    bruto = subprocess.run(
        [ffmpeg(), "-loglevel", "error", "-i", str(trecho), "-vn", "-ac", "1", "-ar", str(TAXA_AUDIO),
         "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    palheiro = np.frombuffer(bruto[: len(bruto) // 2 * 2], dtype=np.int16).astype(np.float64)
    a = int(inicio * TAXA_AUDIO)
    agulha = np.asarray(audio[a: a + int(min(duracao, 15) * TAXA_AUDIO)], dtype=np.float64)
    if len(agulha) < TAXA_AUDIO * 3 or len(palheiro) <= len(agulha):
        return None
    n = len(palheiro) + len(agulha)
    corr = np.fft.irfft(np.fft.rfft(palheiro, n) * np.conj(np.fft.rfft(agulha, n)), n)[: len(palheiro) - len(agulha) + 1]
    acumulado = np.concatenate(([0.0], np.cumsum(palheiro ** 2)))
    energia = acumulado[len(agulha):] - acumulado[: -len(agulha)]
    nota = corr / np.sqrt(np.maximum(energia, 1.0) * max(float(np.sum(agulha ** 2)), 1.0))
    k = int(np.argmax(nota))
    return k / TAXA_AUDIO if nota[k] >= 0.25 else None


def renderizar(entradas: list[str], corte: dict, saida: Path, webcam=None, deslocamento: float = 0) -> str:
    """Tenta a GPU primeiro. Se não der, usa a CPU. Devolve o codificador usado.

    `entradas` é um arquivo ou endereço direto, ou dois quando imagem e som vêm separados.
    `deslocamento` é onde o trecho analisado começa dentro do vídeo original.
    """
    legenda = saida.parent / "legenda.ass"
    gerar_legenda(corte["palavras"], corte["inicio"], legenda)
    leitura = []
    for entrada in entradas:
        leitura += ["-ss", f"{corte['inicio'] + deslocamento:.2f}",
                    "-t", f"{corte['fim'] - corte['inicio']:.2f}", "-i", entrada]
    base = [ffmpeg(), "-y", "-loglevel", "error", *leitura,
            "-filter_complex", _filtro(webcam), "-map", "[v]", "-map", f"{len(entradas) - 1}:a:0?",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]
    opcoes = {
        "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0"],
        "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"],
    }
    erro = ""
    try:
        for nome, args in opcoes.items():
            r = subprocess.run(base + args + [saida.name], cwd=saida.parent, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode == 0:
                return nome
            erro = r.stderr
    finally:
        legenda.unlink(missing_ok=True)
    raise RuntimeError(f"ffmpeg falhou: {erro[-600:]}")
