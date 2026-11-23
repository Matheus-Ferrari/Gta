"""Segmentos, efeitos de câmera/cor e áudio multitrilha. As contas espelham cortes/web/efeitos.js para a prévia bater com o export."""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from .config import DADOS

TIPOS = ("zoom_cam", "zoom", "tremor", "cam_cheia", "freeze", "flash", "pb", "vinheta")
TRANSICOES = ("corte", "fade", "flash")
SONS = DADOS / "sons"
TAXA_ENV = 1000  # envelopes de volume: 1 kHz basta, o ffmpeg reamostra


def _num(v, padrao: float, minimo: float, maximo: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return padrao
    return padrao if math.isnan(v) else max(minimo, min(maximo, v))


def _id(v, n: int) -> str:
    return re.sub(r"[^\w-]", "", str(v or ""))[:24] or f"x{n}"


# ---------------------------------------------------------------- normalização

def norm_segmentos(p: dict, dur_fonte: float = 86400) -> list[dict]:
    """Projetos antigos têm só inicio/fim: viram um segmento."""
    segs = []
    for s in (p.get("segmentos") or [])[:40]:
        ini = _num(s.get("ini"), 0, 0, dur_fonte)
        fim = _num(s.get("fim"), ini + 1, ini + 0.2, max(dur_fonte, ini + 0.2))
        segs.append({"id": _id(s.get("id"), len(segs)), "ini": round(ini, 3), "fim": round(fim, 3), "vel": _num(s.get("vel"), 1, 0.25, 2),
                     "trans": s.get("trans") if s.get("trans") in TRANSICOES else "corte", "transDur": _num(s.get("transDur"), 0.3, 0.06, 2),
                     "rotulo": str(s.get("rotulo") or "")[:40]})
    if not segs:
        ini = _num(p.get("inicio"), 0, 0, 86400)
        segs = [{"id": "s0", "ini": ini, "fim": _num(p.get("fim"), ini + 1, 0, 86400), "vel": 1, "trans": "corte", "transDur": 0.3, "rotulo": ""}]
    return segs


def norm_efeitos(lista, L: int, A: int) -> list[dict]:
    saida = []
    for e in (lista if isinstance(lista, list) else [])[:80]:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS:
            continue
        ini = _num(e.get("ini"), 0, 0, 86400)
        fim = _num(e.get("fim"), ini + 1, ini + 0.04, 86400)
        teto = {"zoom_cam": 4, "zoom": 4}.get(e["tipo"], 1)
        piso = 1 if teto == 4 else 0
        saida.append({"id": _id(e.get("id"), len(saida)), "tipo": e["tipo"], "ini": round(ini, 3), "fim": round(fim, 3),
                      "forca": _num(e.get("forca"), 1.6 if teto == 4 else 1, piso, teto),
                      "entrada": _num(e.get("entrada"), 0, 0, 30), "saida": _num(e.get("saida"), 0, 0, 30),
                      "cx": _num(e.get("cx"), L / 2, 0, L), "cy": _num(e.get("cy"), A / 2, 0, A),
                      "grupo": _id(e.get("grupo"), 0) if e.get("grupo") else "", "ativo": bool(e.get("ativo", True))})
    return saida


def _chaves(lista) -> list[dict]:
    ks = [{"t": _num(k.get("t"), 0, 0, 86400), "v": _num(k.get("v"), 1, 0, 3)} for k in (lista if isinstance(lista, list) else [])[:200] if isinstance(k, dict)]
    return sorted(ks, key=lambda k: k["t"])


def arquivo_som(rel: str) -> Path | None:
    """Só arquivos dentro da biblioteca local de sons."""
    alvo = (SONS / str(rel)).resolve()
    return alvo if SONS.resolve() in alvo.parents and alvo.is_file() else None


def norm_audio(a, volume_antigo: float = 1.0) -> dict:
    a = a if isinstance(a, dict) else {}

    def trilha(nome: str, vol: float = 1.0) -> dict:
        t = a.get(nome) if isinstance(a.get(nome), dict) else {}
        return {"volume": _num(t.get("volume"), vol, 0, 3), "mudo": bool(t.get("mudo")), "fadeIn": _num(t.get("fadeIn"), 0, 0, 30),
                "fadeOut": _num(t.get("fadeOut"), 0, 0, 30), "chaves": _chaves(t.get("chaves"))}
    clipes = []
    for c in (a.get("clipes") if isinstance(a.get("clipes"), list) else [])[:60]:
        if not isinstance(c, dict) or not arquivo_som(c.get("arquivo", "")):
            continue
        clipes.append({"id": _id(c.get("id"), len(clipes)), "trilha": "sfx" if c.get("trilha") == "sfx" else "musica",
                       "arquivo": str(c["arquivo"]).replace("\\", "/")[:200], "nome": str(c.get("nome") or "")[:60],
                       "ini": _num(c.get("ini"), 0, 0, 86400), "dur": _num(c.get("dur"), 1, 0.05, 3600), "desde": _num(c.get("desde"), 0, 0, 36000),
                       "volume": _num(c.get("volume"), 1, 0, 3), "fadeIn": _num(c.get("fadeIn"), 0, 0, 30), "fadeOut": _num(c.get("fadeOut"), 0, 0, 30),
                       "grupo": _id(c.get("grupo"), 0) if c.get("grupo") else ""})
    d = a.get("ducking") if isinstance(a.get("ducking"), dict) else {}
    return {"original": trilha("original", volume_antigo), "musica": trilha("musica"), "sfx": trilha("sfx"), "clipes": clipes,
            "ducking": {"ativo": bool(d.get("ativo", True)), "nivel": _num(d.get("nivel"), 0.3, 0, 1),
                        "ataque": _num(d.get("ataque"), 0.2, 0.02, 2), "soltura": _num(d.get("soltura"), 0.5, 0.02, 3)}}


def norm_cor(c) -> dict:
    c = c if isinstance(c, dict) else {}
    return {"contraste": _num(c.get("contraste"), 1, 0.5, 1.8), "saturacao": _num(c.get("saturacao"), 1, 0, 2), "barras": _num(c.get("barras"), 0, 0, 0.25)}


# ---------------------------------------------------------------- tempo: fonte <-> saída

def mapa(segs: list[dict]) -> tuple[list[float], float]:
    """Início de cada segmento no vídeo final e a duração total."""
    inicios, t = [], 0.0
    for s in segs:
        inicios.append(t)
        t += (s["fim"] - s["ini"]) / s["vel"]
    return inicios, t


def intervalos_na_saida(segs: list[dict], a: float, b: float) -> list[tuple[float, float]]:
    """Um intervalo no tempo da fonte pode cair em vários segmentos (ou em nenhum)."""
    inicios, _ = mapa(segs)
    saida = []
    for s, t0 in zip(segs, inicios):
        x, y = max(a, s["ini"]), min(b, s["fim"])
        if y > x:
            saida.append((t0 + (x - s["ini"]) / s["vel"], t0 + (y - s["ini"]) / s["vel"]))
    return saida


def transicoes(segs: list[dict]) -> list[dict]:
    """Fade pelo preto e flash branco entre segmentos viram sobreposições de cor na emenda."""
    inicios, _ = mapa(segs)
    saida = []
    for s, t0 in zip(segs[1:], inicios[1:]):
        if s["trans"] == "corte":
            continue
        d = s["transDur"]
        if s["trans"] == "fade":
            saida.append({"cor": "black", "ini": t0 - d / 2, "fim": t0 + d / 2, "forca": 1, "entrada": d / 2, "saida": d / 2})
        else:
            saida.append({"cor": "white", "ini": t0 - 0.03, "fim": t0 + d, "forca": 0.9, "entrada": 0.03, "saida": d})
    return saida


# ---------------------------------------------------------------- expressões do ffmpeg

def _k(e: dict, t: str = "t") -> str:
    """Envelope 0..1 do efeito: sobe em `entrada`, desce em `saida`."""
    en, sa = max(e["entrada"], 0.001), max(e["saida"], 0.001)
    return f"clip(min(({t}-{e['ini']:.3f})/{en:.3f},({e['fim']:.3f}-{t})/{sa:.3f}),0,1)"


def _janela(lista: list[dict]) -> str:
    return "+".join(f"between(t,{e['ini']:.3f},{e['fim']:.3f})" for e in lista)


def geometria(efs: list[dict], L: int, A: int, fps: int) -> str | None:
    """Zoom e tremor aplicados no quadro composto, com precisão de subpixel (filtro perspective)."""
    zooms = [e for e in efs if e["tipo"] in ("zoom", "zoom_cam")]
    tremores = [e for e in efs if e["tipo"] == "tremor"]
    if not zooms and not tremores:
        return None
    t = f"(in/{fps})"
    z = "(1" + "".join(f"+{e['forca'] - 1:.4f}*{_k(e, t)}" for e in zooms) + "".join(f"+0.06*{e['forca']:.3f}*{_k(e, t)}" for e in tremores) + ")"
    amp = 0.025 * min(L, A)

    def eixo(tam: int, chave: str, freq: float, fase: float) -> tuple[str, str]:
        c = f"({tam / 2:.1f}" + "".join(f"+{e[chave] - tam / 2:.2f}*{_k(e, t)}" for e in zooms) + ")"
        meio = f"({tam / 2:.1f}/{z})"
        centro = f"clip({c},{meio},{tam}-{meio})"
        d = "".join(f"+{amp * e['forca']:.3f}*{_k(e, t)}*sin({2 * math.pi * freq:.4f}*{t}+{fase})" for e in tremores)
        return f"{centro}-{meio}{d}", f"{centro}+{meio}{d}"
    xa, xb = eixo(L, "cx", 11, 0)
    ya, yb = eixo(A, "cy", 13, 1)
    return (f"perspective=x0='{xa}':y0='{ya}':x1='{xb}':y1='{ya}':x2='{xa}':y2='{yb}':x3='{xb}':y3='{yb}':"
            f"eval=frame:enable='{_janela(zooms + tremores)}'")


def saturacao(efs: list[dict]) -> str | None:
    pbs = [e for e in efs if e["tipo"] == "pb"]
    if not pbs:
        return None
    s = "clip(1" + "".join(f"-{e['forca']:.3f}*{_k(e)}" for e in pbs) + ",0,1)"
    return f"hue=s='{s}':enable='{_janela(pbs)}'"


def alfa(e: dict) -> str:
    """Opacidade de uma sobreposição (flash, vinheta, transição). A sobreposição só existe durante o efeito."""
    d = e["fim"] - e["ini"]
    partes = [f"colorchannelmixer=aa={e['forca']:.3f}"]
    if e["entrada"] > 0.001:
        partes.append(f"fade=t=in:st=0:d={min(e['entrada'], d):.3f}:alpha=1")
    if e["saida"] > 0.001:
        partes.append(f"fade=t=out:st={max(0, d - e['saida']):.3f}:d={min(e['saida'], d):.3f}:alpha=1")
    return ",".join(partes) + f",setpts=PTS+{max(e['ini'], 0):.3f}/TB"


def vinheta_png(L: int, A: int, pasta: Path) -> Path:
    """A mesma imagem é usada na prévia e no export."""
    destino = pasta / f"_vinheta_{L}x{A}.png"
    if not destino.exists():
        import cv2
        y, x = np.mgrid[0:A, 0:L].astype(np.float32)
        r = np.hypot((x - L / 2) / (L / 2), (y - A / 2) / (A / 2)) / math.sqrt(2)
        a = np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6
        img = np.zeros((A, L, 4), dtype=np.uint8)
        img[..., 3] = np.round(a * 255).astype(np.uint8)
        pasta.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(destino), img)
    return destino


# ---------------------------------------------------------------- envelopes de volume

def _interp(chaves: list[dict], t: np.ndarray) -> np.ndarray:
    if not chaves:
        return np.ones_like(t)
    return np.interp(t, [k["t"] for k in chaves], [k["v"] for k in chaves])


def falas_na_saida(palavras: list[dict], segs: list[dict], folga: float = 0.6) -> list[tuple[float, float]]:
    """Intervalos com fala no vídeo final, a partir dos tempos reais da transcrição."""
    trechos = sorted(x for p in palavras for x in intervalos_na_saida(segs, p["i"], p["f"]))
    juntos: list[list[float]] = []
    for a, b in trechos:
        if juntos and a - juntos[-1][1] <= folga:
            juntos[-1][1] = max(juntos[-1][1], b)
        else:
            juntos.append([a, b])
    return [(a, b) for a, b in juntos]


def envelope(trilha: dict, dur: float, falas: list[tuple[float, float]] | None = None, duck: dict | None = None) -> np.ndarray:
    """Ganho da trilha a cada 1 ms: volume x keyframes x fades x ducking."""
    t = np.arange(int(math.ceil(dur * TAXA_ENV)) + 1, dtype=np.float64) / TAXA_ENV
    g = np.zeros_like(t) if trilha["mudo"] else trilha["volume"] * _interp(trilha["chaves"], t)
    if trilha["fadeIn"] > 0:
        g *= np.clip(t / trilha["fadeIn"], 0, 1)
    if trilha["fadeOut"] > 0:
        g *= np.clip((dur - t) / trilha["fadeOut"], 0, 1)
    if falas and duck and duck["ativo"]:
        k = np.zeros_like(t)
        for a, b in falas:
            k = np.maximum(k, np.clip(np.minimum((t - a) / duck["ataque"] + 1, (b - t) / duck["soltura"] + 1), 0, 1))
        g *= 1 - (1 - duck["nivel"]) * k
    return g


def gravar_envelope(g: np.ndarray, destino: Path) -> None:
    np.repeat(g.astype("<f4"), 2).tofile(destino)


def trivial(g: np.ndarray) -> bool:
    return bool(np.all(np.abs(g - 1) < 0.004))
