"""Acha os momentos fortes sem gastar token: voz empolgada e explosão de chat."""
from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

from .config import TAXA_AUDIO, ffmpeg

ATRASO_CHAT = 8  # o chat reage alguns segundos depois do lance
CHAT_MINIMO = 5  # mensagens por minuto. Abaixo disso, uma mensagem solta viraria um falso pico
HYPE = re.compile(
    r"k{4,}|(?:ha|rs){3,}|lul|kekw|omegalul|pog|clip|corta|caralho|mano do c[eé]u|meu deus|n[aã]o acredito|gg+\b",
    re.IGNORECASE,
)


def extrair_audio(entrada: str, destino: Path, inicio: float = 0, duracao: float | None = None) -> None:
    if destino.exists():
        return
    temp = destino.with_suffix(".tmp")
    trecho = ["-ss", f"{inicio:.2f}"] if inicio else []
    if duracao:
        trecho += ["-t", f"{duracao:.2f}"]
    subprocess.run(
        [ffmpeg(), "-y", "-loglevel", "error", *trecho, "-i", entrada, "-vn", "-ac", "1",
         "-ar", str(TAXA_AUDIO), "-f", "s16le", "file:" + str(temp)],
        check=True,
    )
    temp.replace(destino)


def abrir_audio(caminho: Path) -> np.ndarray:
    return np.memmap(caminho, dtype=np.int16, mode="r")


def _suave(x: np.ndarray, janela: int) -> np.ndarray:
    return np.convolve(x, np.ones(janela) / janela, mode="same")


def _realce(x: np.ndarray, piso: float, bloco: int = 120) -> np.ndarray:
    """Quanto cada segundo se destaca do clima dos minutos ao redor (0 a 1)."""
    n = len(x)
    if n < bloco * 2:
        base = np.full(n, np.median(x))
    else:
        centros = np.arange(bloco // 2, n, bloco)
        medianas = [np.median(x[max(0, c - bloco): c + bloco]) for c in centros]
        base = np.interp(np.arange(n), centros, medianas)
    desvio = x - base
    escala = max(float(np.median(np.abs(desvio - np.median(desvio)))) * 1.4826, piso)
    return np.clip(desvio / escala, 0, 6) / 6


def sinal_audio(audio: np.ndarray) -> np.ndarray:
    """Volume ponderado pela chance de ser voz. Tiro e explosão têm espectro 'chiado' e pesam menos."""
    total = len(audio) // TAXA_AUDIO
    volume, voz = np.zeros(total), np.zeros(total)
    janela = np.hanning(TAXA_AUDIO // 2)
    freqs = np.fft.rfftfreq(len(janela), 2 / TAXA_AUDIO)
    faixa = (freqs >= 200) & (freqs <= 3400)
    for s in range(total):
        q = np.asarray(audio[s * TAXA_AUDIO: (s + 1) * TAXA_AUDIO], dtype=np.float32) / 32768
        volume[s] = 20 * np.log10(np.sqrt(np.mean(q ** 2)) + 1e-5)
        pot = np.abs(np.fft.rfft(q[::2][: len(janela)] * janela)) ** 2 + 1e-12
        na_faixa = pot[faixa]
        chiado = np.exp(np.mean(np.log(na_faixa))) / np.mean(na_faixa)
        voz[s] = (na_faixa.sum() / pot.sum()) * (1 - chiado)
    return _realce(volume, piso=1.5) * np.clip(voz * 1.4, 0, 1)


def ler_chat(caminho: Path) -> list[tuple[float, str]]:
    """Aceita JSON do TwitchDownloader ou CSV simples: segundos,mensagem."""
    if caminho.suffix.lower() == ".json":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return [(float(c["content_offset_seconds"]), c.get("message", {}).get("body", ""))
                for c in dados.get("comments", [])]
    with caminho.open(encoding="utf-8", newline="") as f:
        return [(float(l[0]), l[1] if len(l) > 1 else "") for l in csv.reader(f) if l and l[0].replace(".", "").isdigit()]


def normalizar_msg(texto: str) -> str:
    """Junta variações da mesma reação: KEKW e kekw, kkkkkk e kkk."""
    t = re.sub(r"(.)\1{2,}", r"\1\1", texto.lower().strip())
    return re.sub(r"\s+", " ", t)[:40]


def sinal_chat(mensagens: list[tuple[float, str]], total: int) -> np.ndarray:
    volume, hype, repetida = np.zeros(total), np.zeros(total), np.zeros(total)
    blocos: dict[int, Counter] = {}
    for t, texto in mensagens:
        s = int(t) - ATRASO_CHAT
        if 0 <= s < total:
            volume[s] += 1
            hype[s] += bool(HYPE.search(texto))
            blocos.setdefault(s // 8, Counter())[normalizar_msg(texto)] += 1
    for b, contagem in blocos.items():
        repetida[b * 8: (b + 1) * 8] = max(contagem.values()) - 1
    return (0.45 * _realce(_suave(volume, 10), piso=0.5) + 0.3 * _realce(_suave(hype, 10), piso=0.2)
            + 0.25 * _realce(_suave(repetida, 10), piso=0.3))


def medir_chat(mensagens: list[tuple[float, str]], pico: int, janela: int = 25) -> dict:
    """Compara o chat logo depois do lance com o ritmo normal dos minutos anteriores."""
    agora = [texto for t, texto in mensagens if pico <= t - ATRASO_CHAT < pico + janela]
    antes = Counter(int((pico - (t - ATRASO_CHAT)) // janela) for t, _ in mensagens if pico - 150 <= t - ATRASO_CHAT < pico)
    normal = max(float(np.median([antes.get(i, 0) for i in range(6)])), 1.0)
    repetida, vezes = "", 0
    if agora:
        repetida, vezes = Counter(normalizar_msg(t) for t in agora).most_common(1)[0]
    return {"mensagens": len(agora), "crescimento": len(agora) / normal, "repetida": repetida, "vezes": vezes,
            "parcela": vezes / max(len(agora), 1), "hype": sum(bool(HYPE.search(t)) for t in agora) / max(len(agora), 1)}


def _centroide(x: np.ndarray) -> float:
    if len(x) < 2048:
        return 1.0
    x = x[:8192]
    e = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / TAXA_AUDIO)
    faixa = (f >= 150) & (f <= 4000)
    return float((e[faixa] * f[faixa]).sum() / (e[faixa].sum() + 1e-9))


def medir_audio(audio: np.ndarray, pico: int) -> dict:
    """Mede o pico contra a voz normal da pessoa: altura, surpresa, ritmo de risada e voz aguda."""
    total = len(audio) // TAXA_AUDIO
    ini, fim = max(0, pico - 120), min(total, pico + 12)
    q = np.asarray(audio[ini * TAXA_AUDIO: fim * TAXA_AUDIO], dtype=np.float32) / 32768
    passo = TAXA_AUDIO // 4
    n = len(q) // passo
    if n < 16:
        return {"acima": 0.0, "subita": 0.0, "ritmo": 0.0, "agudo": 1.0}
    db = 20 * np.log10(np.sqrt(np.mean(q[: n * passo].reshape(n, passo) ** 2, axis=1)) + 1e-5)
    centro = (pico - ini) * 4
    falando = db[: max(4, centro - 20)]
    falando = falando[falando > -55]  # ignora silêncio digital ao medir o normal
    if len(falando) < 40:  # pico logo no começo do áudio: usa o trecho inteiro como referência
        falando = db[db > -55]
    if not len(falando):
        return {"acima": 0.0, "subita": 0.0, "ritmo": 0.0, "agudo": 1.0}
    normal = float(np.median(falando[falando >= np.percentile(falando, 30)]))
    forte = float(np.percentile(db[max(0, centro - 12): centro + 12], 90))
    anterior = db[max(0, centro - 48): max(1, centro - 16)]
    anterior = anterior[anterior > -55]
    trecho = q[max(0, (pico - ini - 4) * TAXA_AUDIO): (pico - ini + 4) * TAXA_AUDIO]

    salto = TAXA_AUDIO // 50
    m = len(trecho) // salto
    ritmo = 0.0
    if m >= 100:
        env = np.sqrt(np.mean(trecho[: m * salto].reshape(m, salto) ** 2, axis=1))
        pot = np.abs(np.fft.rfft((env - env.mean()) * np.hanning(m))) ** 2
        f = np.fft.rfftfreq(m, 1 / 50)
        ritmo = float(pot[(f >= 3.5) & (f <= 8)].max() / (pot[(f > 0.5) & (f <= 20)].mean() + 1e-9))
    referencia = q[: max(0, (pico - ini - 8) * TAXA_AUDIO)][-TAXA_AUDIO * 20:]
    return {"acima": forte - normal, "subita": forte - float(np.median(anterior)) if len(anterior) else 0.0, "ritmo": ritmo,
            "agudo": _centroide(trecho) / max(_centroide(referencia), 1.0)}


def combinar(audio: np.ndarray, chat: np.ndarray | None) -> np.ndarray:
    base = audio if chat is None else 0.35 * audio + 0.65 * chat
    return _suave(base, 8)


def candidatos(score: np.ndarray, qtd: int, antes: int = 35, depois: int = 30, distancia: int = 75) -> list[dict]:
    """Pega os maiores picos, sem deixar dois cortes caírem no mesmo momento."""
    restante = score.copy()
    achados = []
    while len(achados) < qtd:
        pico = int(np.argmax(restante))
        if restante[pico] <= 0.02:
            break
        achados.append({
            "pico": pico,
            "inicio": max(0, pico - antes),
            "fim": min(len(score), pico + depois),
            "sinal": round(float(score[pico]), 4),
        })
        restante[max(0, pico - distancia): pico + distancia] = 0
    return achados
