"""Transcreve só os trechos candidatos, na GPU, guardando o resultado para não refazer."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import TAXA_AUDIO, preparar_gpu


def _carregar(modelo: str):
    preparar_gpu()
    from faster_whisper import WhisperModel

    silencio = np.zeros(TAXA_AUDIO, dtype=np.float32)
    for tipo in ("int8_float16", "float16", "float32"):  # placas antigas não aceitam todos os tipos
        try:
            whisper = WhisperModel(modelo, device="cuda", compute_type=tipo)
            list(whisper.transcribe(silencio, language="pt")[0])
            print(f"  Whisper na GPU ({tipo})")
            return whisper
        except Exception as erro:
            motivo = erro
    print(f"  GPU indisponível ({motivo}). Usando CPU, vai demorar mais.")
    return WhisperModel(modelo, device="cpu", compute_type="int8")


def transcrever(cands: list[dict], audio: np.ndarray, modelo: str, cache: Path) -> None:
    salvo = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    whisper = None
    for n, c in enumerate(cands, 1):
        chave = f"{modelo}:{c['inicio']}-{c['fim']}"
        if chave not in salvo:
            whisper = whisper or _carregar(modelo)
            print(f"  transcrevendo {n}/{len(cands)}", flush=True)
            trecho = np.asarray(audio[c["inicio"] * TAXA_AUDIO: c["fim"] * TAXA_AUDIO], dtype=np.float32) / 32768
            segmentos, _ = whisper.transcribe(
                trecho, language="pt", word_timestamps=True, vad_filter=True,
                beam_size=3, condition_on_previous_text=False,
            )
            salvo[chave] = [
                {"p": p.word.strip(), "i": round(c["inicio"] + p.start, 2), "f": round(c["inicio"] + p.end, 2)}
                for s in segmentos for p in (s.words or []) if p.word.strip()
            ]
            cache.write_text(json.dumps(salvo, ensure_ascii=False), encoding="utf-8")
        c["palavras"] = salvo[chave]
