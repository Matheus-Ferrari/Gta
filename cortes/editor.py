"""Editor de composição: baixa a fonte original do corte, guarda o projeto e exporta o vídeo 9:16."""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import efeitos, fontes, render
from .config import DADOS, LIVES, TAXA_AUDIO, ffmpeg, ffprobe, gravar_json, ler_json

LARGURA, ALTURA = 1080, 1920
FORMATOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def dims(p: dict) -> tuple[int, int]:
    return FORMATOS.get(p.get("formato"), FORMATOS["9:16"])
FONTES = {"Arial Black", "Impact", "Segoe UI Black", "Arial", "Verdana", "Trebuchet MS", "Georgia", "Tahoma"}
ARQ_STREAMERS = DADOS / "streamers.json"
ARQ_ESTILOS = DADOS / "estilos.json"
ARQ_TEMPLATES = DADOS / "templates.json"
ARQ_MARCA = DADOS / "marca.json"
GRAFICOS = DADOS / "graficos"
REGIOES = ("webcam", "gameplay", "chat")
ANIMS = ("nenhuma", "fade", "pop", "subir")
QUALIDADES = {"alta": 12_000_000, "media": 8_000_000, "leve": 4_500_000}
AUDIO_BPS = 192_000
SEM_JANELA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ---------------------------------------------------------------- localização do corte

def achar_corte(corte_id: str) -> SimpleNamespace:
    partes = str(corte_id).replace("\\", "/").split("/")
    if len(partes) != 3 or any(p in ("", ".", "..") for p in partes):
        raise ValueError("Corte inválido.")
    raiz = LIVES.resolve()
    pasta = (raiz / partes[0] / partes[1]).resolve()
    if raiz not in pasta.parents or not pasta.is_dir():
        raise ValueError("Corte não encontrado.")
    lista = ler_json(pasta / "cortes" / "cortes.json", [])
    corte = next((c for c in lista if c.get("arquivo") == partes[2]), None)
    if not corte:
        raise ValueError("Corte não encontrado.")
    return SimpleNamespace(id="/".join(partes), plataforma=partes[0], live=partes[1], pasta=pasta, corte=corte,
                           info=ler_json(pasta / "live.json", {}), stem=Path(partes[2]).stem)


def _desloc(c: dict) -> float:
    """Onde a análise começou dentro do vídeo. Cortes antigos só guardam o horário em texto."""
    if "desloc" in c:
        return float(c["desloc"])
    m = re.fullmatch(r"(\d+)h(\d+)m(\d+)s", c.get("momento_na_live", ""))
    if not m:
        return 0.0
    momento = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
    return max(0.0, float(math.ceil(momento - c["inicio"] - 1e-6)))


def origem_da_live(a: SimpleNamespace) -> str | None:
    origem = str(a.info.get("origem") or "").strip()
    if origem and (fontes.eh_link(origem) or Path(origem).is_file()):
        return origem
    m = re.match(r"TwitchVod_v(\d+)", a.live)
    if m:
        return f"https://www.twitch.tv/videos/{m[1]}"
    for pasta in (DADOS / "teste",):
        local = pasta / f"{a.live}.mp4"
        if local.is_file():
            return str(local)
    return None


def sondar(arquivo: Path) -> dict:
    r = subprocess.run(
        [ffprobe(), "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,start_time",
         "-show_entries", "format=duration", "-of", "json", str(arquivo)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA, check=True)
    dados = json.loads(r.stdout)
    v = next((s for s in dados["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in dados["streams"] if s["codec_type"] == "audio"), {})
    num, _, den = v.get("r_frame_rate", "30/1").partition("/")
    return {"w": v.get("width", 0), "h": v.get("height", 0), "fps": round(float(num) / float(den or 1), 3),
            "dur": float(dados["format"].get("duration", 0)), "video": v.get("codec_name"), "audio": a.get("codec_name"),
            "atraso_audio": float(a.get("start_time") or 0) - float(v.get("start_time") or 0)}


# ---------------------------------------------------------------- fonte original

def _arq_fonte(a: SimpleNamespace) -> tuple[Path, Path]:
    destino = a.pasta / "fontes" / f"{a.stem}.mp4"
    return destino, destino.with_suffix(".json")


def fonte_pronta(a: SimpleNamespace) -> dict | None:
    destino, meta = _arq_fonte(a)
    dados = ler_json(meta)
    if dados and (LIVES / dados["arquivo"]).is_file():
        return dados
    return None


def _usar_corte_pronto(a: SimpleNamespace, motivo: str) -> dict:
    arquivo = a.pasta / "cortes" / a.corte["arquivo"]
    s = sondar(arquivo)
    meta = {"arquivo": arquivo.resolve().relative_to(LIVES.resolve()).as_posix(), "t0": a.corte["inicio"], "dur": s["dur"],
            "w": s["w"], "h": s["h"], "fps": s["fps"], "original": False,
            "aviso": f"{motivo} O editor está usando o corte já renderizado, que tem legenda gravada e pouca margem."}
    gravar_json(_arq_fonte(a)[1], meta)
    return meta


def preparar_fonte(corte_id: str, tarefa=None) -> dict:
    a = achar_corte(corte_id)
    pronta = fonte_pronta(a)
    if pronta and pronta.get("original"):
        return pronta
    avancar = tarefa.avancar if tarefa else (lambda *_: None)
    origem = origem_da_live(a)
    if not origem:
        return _usar_corte_pronto(a, "A fonte original deste corte não foi encontrada.")

    c = a.corte
    destino, arq_meta = _arq_fonte(a)
    destino.parent.mkdir(exist_ok=True)
    temp, duracao = destino.with_name(f"_{a.stem}.mkv"), c["fim"] - c["inicio"]
    momento = c["inicio"] + _desloc(c)
    try:
        avancar(0.1, "Baixando o trecho original")
        if fontes.eh_link(origem):
            entradas = fontes.enderecos(origem, fontes.FORMATO_VIDEO)
            if not a.info.get("streamer"):
                dados = fontes.info(origem)
                a.info["streamer"] = dados.get("uploader") or dados.get("uploader_id") or dados.get("channel") or ""
                gravar_json(a.pasta / "live.json", a.info)
        else:
            entradas = [origem]
        render.baixar_trecho(entradas, momento, duracao, temp)
        avancar(0.7, "Preparando para o editor")
        s = sondar(temp)
        compativel = s["video"] == "h264" and s["audio"] in ("aac", None)
        codec = ["-c", "copy"] if compativel else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(temp), "-map", "0:v:0", "-map", "0:a:0?", *codec,
                        "-movflags", "+faststart", str(destino)], check=True, capture_output=True, creationflags=SEM_JANELA)
    except (subprocess.CalledProcessError, SystemExit, OSError, KeyError) as erro:
        destino.unlink(missing_ok=True)
        return _usar_corte_pronto(a, f"Não consegui baixar a fonte original ({str(erro)[:120]}).")
    finally:
        temp.unlink(missing_ok=True)

    avancar(0.85, "Conferindo o sincronismo")
    achado = None
    if (a.pasta / "audio.pcm").exists():
        audio = np.memmap(a.pasta / "audio.pcm", dtype=np.int16, mode="r")
        achado = render.localizar(destino, audio, c["inicio"], duracao)
    aviso = "" if achado is not None else "Não consegui conferir o sincronismo pelo áudio. Confira o início do corte na timeline."
    s = sondar(destino)
    if achado is None:
        achado = min(render.MARGEM, momento)
    else:  # localizar conta amostras de áudio, e o áudio pode começar depois da imagem
        achado += s["atraso_audio"]
    meta = {"arquivo": destino.resolve().relative_to(LIVES.resolve()).as_posix(), "t0": round(c["inicio"] - achado, 3),
            "dur": s["dur"], "w": s["w"], "h": s["h"], "fps": s["fps"], "original": True, "aviso": aviso}
    gravar_json(arq_meta, meta)
    return meta


# ---------------------------------------------------------------- palavras e áudio

def palavras_da_fonte(a: SimpleNamespace, meta: dict) -> list[dict]:
    """Reúne a transcrição que cobre a fonte, no tempo da fonte (0 = início do arquivo)."""
    salvo = ler_json(a.pasta / "transcricoes.json", {}) or {}
    ini, fim = meta["t0"], meta["t0"] + meta["dur"]
    trechos = []
    for chave, lista in salvo.items():
        m = re.search(r":(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$", chave)
        if m:
            trechos.append((min(fim, float(m[2])) - max(ini, float(m[1])), float(m[1]), float(m[2]), lista))
    if not trechos:
        return []
    trechos.sort(key=lambda t: t[0], reverse=True)
    _, base_a, base_b, escolhidas = trechos[0]
    todas = list(escolhidas)
    for _, _, _, lista in trechos[1:]:
        todas += [p for p in lista if p["f"] <= base_a or p["i"] >= base_b]
    vistos, saida = set(), []
    for p in sorted(todas, key=lambda x: x["i"]):
        chave = (round(p["i"], 1), p["p"])
        if chave not in vistos and p["f"] > ini and p["i"] < fim:
            vistos.add(chave)
            saida.append({"p": p["p"], "i": round(p["i"] - ini, 2), "f": round(p["f"] - ini, 2)})
    return saida


def onda(corte_id: str, pontos: int = 900) -> list[float]:
    a = achar_corte(corte_id)
    meta = fonte_pronta(a)
    if not meta:
        return []
    bruto = subprocess.run([ffmpeg(), "-loglevel", "error", "-i", str(LIVES / meta["arquivo"]), "-vn", "-ac", "1", "-ar", "4000",
                            "-f", "s16le", "-"], capture_output=True, creationflags=SEM_JANELA).stdout
    x = np.abs(np.frombuffer(bruto[: len(bruto) // 2 * 2], dtype=np.int16).astype(np.float32))
    if not len(x):
        return []
    blocos = np.array_split(x, min(pontos, len(x)))
    picos = np.array([float(b.max()) for b in blocos])
    return [round(float(v), 3) for v in picos / max(float(picos.max()), 1.0)]


def transcrever_fonte(corte_id: str, modelo: str, tarefa=None) -> dict:
    """Roda em outro processo para o Whisper devolver a memória da placa ao terminar."""
    if tarefa:
        tarefa.avancar(0.1, "Transcrevendo o trecho")
    r = subprocess.run([sys.executable, "-m", "cortes.editor", "transcrever", corte_id, modelo],
                       cwd=Path(__file__).parent.parent, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=SEM_JANELA)
    if r.returncode != 0:
        raise RuntimeError("Não consegui transcrever: " + (r.stderr.strip().splitlines() or ["erro desconhecido"])[-1])
    a = achar_corte(corte_id)
    return {"palavras": palavras_da_fonte(a, fonte_pronta(a))}


def _transcrever_agora(corte_id: str, modelo: str) -> None:
    from . import transcricao
    a = achar_corte(corte_id)
    meta = fonte_pronta(a)
    if not meta:
        raise SystemExit("A fonte deste corte ainda não foi preparada.")
    pcm = a.pasta / "audio.pcm"
    if pcm.exists() and not a.corte.get("manual"):
        audio = np.memmap(pcm, dtype=np.int16, mode="r")
        limite = len(audio) // TAXA_AUDIO
        cand = {"inicio": max(0, int(math.floor(meta["t0"]))), "fim": min(limite, int(math.ceil(meta["t0"] + meta["dur"])))}
        transcricao.transcrever([cand], audio, modelo, a.pasta / "transcricoes.json")
        return
    # Corte manual ou arquivo sem análise: usa o áudio da própria fonte e guarda no tempo da live.
    bruto = subprocess.run([ffmpeg(), "-loglevel", "error", "-i", str(LIVES / meta["arquivo"]), "-vn", "-ac", "1", "-ar", str(TAXA_AUDIO),
                            "-f", "s16le", "-"], capture_output=True, creationflags=SEM_JANELA).stdout
    audio = np.frombuffer(bruto[: len(bruto) // 2 * 2], dtype=np.int16)
    if len(audio) < TAXA_AUDIO:
        raise SystemExit("A fonte não tem áudio para transcrever.")
    cand = {"inicio": 0, "fim": len(audio) // TAXA_AUDIO}
    temp = a.pasta / "fontes" / f"_{a.stem}_transc.json"
    temp.unlink(missing_ok=True)
    transcricao.transcrever([cand], audio, modelo, temp)
    temp.unlink(missing_ok=True)
    t0 = float(meta["t0"])
    salvo = ler_json(a.pasta / "transcricoes.json", {}) or {}
    salvo[f"{modelo}:{t0:.2f}-{t0 + cand['fim']:.2f}"] = [
        {"p": p["p"], "i": round(p["i"] + t0, 2), "f": round(p["f"] + t0, 2)} for p in cand["palavras"]]
    gravar_json(a.pasta / "transcricoes.json", salvo)


# ---------------------------------------------------------------- webcam

def detectar_webcam(corte_id: str) -> dict:
    """Procura um rosto que fica no mesmo lugar durante o vídeo. Rosto de jogo muda de posição."""
    try:
        import cv2
    except ImportError:
        return {"encontrada": False, "mensagem": "Detecção automática indisponível. Marque a webcam manualmente."}
    a = achar_corte(corte_id)
    meta = fonte_pronta(a)
    if not meta:
        raise ValueError("Prepare a fonte antes de detectar a webcam.")
    largura, altura = 960, 2 * round(960 * meta["h"] / meta["w"] / 2)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    achados: list[tuple[int, float, float, float, float]] = []
    amostras = 14
    for n in range(amostras):
        t = meta["dur"] * (n + 0.5) / amostras
        bruto = subprocess.run([ffmpeg(), "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(LIVES / meta["arquivo"]), "-frames:v", "1",
                                "-vf", f"scale={largura}:{altura}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                               capture_output=True, creationflags=SEM_JANELA).stdout
        if len(bruto) != largura * altura:
            continue
        quadro = np.frombuffer(bruto, dtype=np.uint8).reshape(altura, largura)
        for x, y, l, h in detector.detectMultiScale(quadro, 1.1, 6, minSize=(34, 34)):
            achados.append((n, (x + l / 2) / largura, (y + h / 2) / altura, l / largura, h / altura))
    melhor, apoio = None, 0
    for f in achados:
        perto = {g[0] for g in achados if abs(g[1] - f[1]) < 0.06 and abs(g[2] - f[2]) < 0.08}
        if len(perto) > apoio:
            melhor, apoio = f, len(perto)
    confianca = apoio / amostras
    if not melhor or confianca < 0.35:
        return {"encontrada": False, "confianca": round(confianca, 2),
                "mensagem": "Não encontrei webcam neste vídeo. Se ela existir, marque a região manualmente."}
    grupo = [g for g in achados if abs(g[1] - melhor[1]) < 0.06 and abs(g[2] - melhor[2]) < 0.08]
    cx, cy, fl, fh = (float(np.median([g[i] for g in grupo])) for i in (1, 2, 3, 4))
    l, h = min(1.0, fl * 3.4), min(1.0, fh * 3.0)
    x, y = max(0.0, min(1 - l, cx - l / 2)), max(0.0, min(1 - h, cy + fh * 0.2 - h / 2))
    return {"encontrada": True, "confianca": round(confianca, 2),
            "regiao": {k: round(v, 4) for k, v in zip("xywh", (x, y, l, h))},
            "mensagem": "Webcam sugerida. Ajuste o retângulo para encaixar na câmera."}


def regioes_streamer(streamer: str) -> dict | None:
    return (ler_json(ARQ_STREAMERS, {}) or {}).get(streamer.strip().lower()) if streamer.strip() else None


def salvar_regioes(streamer: str, regioes: dict) -> None:
    if not streamer.strip():
        return
    todos = ler_json(ARQ_STREAMERS, {}) or {}
    chave = streamer.strip().lower()
    todos[chave] = {**todos.get(chave, {}), **{r: _regiao(regioes.get(r)) for r in REGIOES}}
    gravar_json(ARQ_STREAMERS, todos)


def salvar_layout_streamer(streamer: str, projeto: dict) -> dict:
    """Guarda a composição atual para os próximos cortes do mesmo streamer."""
    if not streamer.strip():
        raise ValueError("Escreva o nome do streamer no topo do editor.")
    p = normalizar(projeto)
    layout = _layout(p)
    todos = ler_json(ARQ_STREAMERS, {}) or {}
    todos[streamer.strip().lower()] = {**p["regioes"], "layout": layout}
    gravar_json(ARQ_STREAMERS, todos)
    return layout


def estilos() -> list[dict]:
    return ler_json(ARQ_ESTILOS, []) or []


def salvar_estilo(nome: str, estilo: dict | None) -> list[dict]:
    nome = str(nome).strip()[:40]
    if not nome:
        raise ValueError("Dê um nome ao estilo.")
    lista = [e for e in estilos() if e.get("nome") != nome]
    if estilo:
        lista.append({"nome": nome, "estilo": _legenda({**estilo, "blocos": []}) | {"blocos": []}})
    gravar_json(ARQ_ESTILOS, lista)
    return lista


def _layout(p: dict) -> dict:
    return {"preset": p["preset"], "formato": p["formato"], "camadas": p["camadas"], "fundo": p["fundo"], "divisao": p["divisao"], "cor": p["cor"],
            "opcoes": p["opcoes"], "legenda": {k: v for k, v in p["legenda"].items() if k != "blocos"}}


def templates() -> list[dict]:
    return ler_json(ARQ_TEMPLATES, []) or []


def salvar_template(nome: str, projeto: dict | None) -> list[dict]:
    """Template personalizado: a composição atual com um nome. Sem projeto, apaga."""
    nome = str(nome).strip()[:40]
    if not nome:
        raise ValueError("Dê um nome ao template.")
    lista = [t for t in templates() if t.get("nome") != nome]
    if projeto:
        lista.append({"nome": nome, "layout": _layout(normalizar(projeto))})
    gravar_json(ARQ_TEMPLATES, lista)
    return lista


TAMANHOS_MARCA = {"logo": (60, 300, 110), "nome": (20, 110, 40), "arroba": (14, 80, 32)}  # px no cabeçalho editorial: mínimo, máximo, padrão


def _tamanhos(t) -> dict:
    t = t if isinstance(t, dict) else {}
    saida = {}
    for k, (menor, maior, padrao) in TAMANHOS_MARCA.items():
        try:
            saida[k] = max(menor, min(maior, int(t.get(k) or padrao)))
        except (TypeError, ValueError):
            saida[k] = padrao
    return saida


def marca() -> dict:
    m = ler_json(ARQ_MARCA, {}) or {}
    return {"nome": str(m.get("nome") or "")[:40], "arroba": str(m.get("arroba") or "")[:40], "logo": str(m.get("logo") or "")[:64],
            "tamanhos": _tamanhos(m.get("tamanhos"))}


def salvar_marca(d: dict) -> dict:
    logo = re.sub(r"[^\w.-]", "", str(d.get("logo") or ""))[:64]
    gravar_json(ARQ_MARCA, {"nome": str(d.get("nome") or "").strip()[:40], "arroba": str(d.get("arroba") or "").strip()[:40],
                            "logo": logo if logo and (GRAFICOS / logo).is_file() else "", "tamanhos": _tamanhos(d.get("tamanhos"))})
    return marca()


# ---------------------------------------------------------------- projeto

def _arq_projeto(a: SimpleNamespace) -> Path:
    return a.pasta / "projetos" / f"{a.stem}.json"


def abrir(corte_id: str) -> dict:
    a = achar_corte(corte_id)
    meta = fonte_pronta(a)
    if not meta:
        return {"preparar": True}
    streamer = a.info.get("streamer") or ""
    c = a.corte
    return {
        "corte": a.id, "titulo_live": a.info.get("titulo", a.live), "plataforma": a.plataforma, "streamer": streamer,
        "nota": c.get("nota"), "motivo": c.get("motivo", ""), "texto": c.get("texto", ""),
        "pasta": f"{a.plataforma}/{a.live}/cortes",
        "fonte": {**meta, "url": "/video/" + meta["arquivo"]},
        "inicio": round(max(0, c["inicio"] - meta["t0"]), 2), "fim": round(min(meta["dur"], c["fim"] - meta["t0"]), 2),
        "palavras": palavras_da_fonte(a, meta), "regioes": regioes_streamer(streamer),
        "projeto": ler_json(_arq_projeto(a)), "estilos": estilos(), "templates": templates(), "marca": marca(), "exportados": exportados(a),
        "vinheta": {f: "/grafico/" + efeitos.vinheta_png(*FORMATOS[f], GRAFICOS).name for f in FORMATOS},
        "manual": bool(c.get("manual")), "formato": c.get("formato") if c.get("formato") in FORMATOS else "9:16", **chat_da_fonte(a, meta),
    }


def chat_da_fonte(a: SimpleNamespace, meta: dict) -> dict:
    """Mensagens reais do chat no tempo da fonte. Sem arquivo de chat, a lista fica vazia (nada é inventado)."""
    proprio = a.pasta / "fontes" / f"{a.stem}.chat.json"
    if proprio.is_file():
        return {"chat": ler_json(proprio, []) or [], "chat_origem": "Chat da gravação na Twitch"}
    arquivo = a.pasta / "chat.json"
    if arquivo.is_file():
        base = float(meta["t0"]) + _desloc(a.corte)
        dados = ler_json(arquivo, {}) or {}
        msgs = []
        for c in dados.get("comments", []):
            t = float(c.get("content_offset_seconds", 0)) - base
            msg = c.get("message") or {}
            texto = str(msg.get("body") or "").strip()
            if -90 <= t <= meta["dur"] and texto:
                cor = msg.get("user_color") or ""
                msgs.append({"t": round(t, 2), "n": str((c.get("commenter") or {}).get("display_name") or "")[:25], "m": texto[:220],
                             "c": cor.upper() if re.fullmatch(r"#[0-9a-fA-F]{6}", cor) else ""})
        if msgs:
            return {"chat": sorted(msgs, key=lambda x: x["t"]), "chat_origem": "Chat da gravação na Twitch"}
    return {"chat": [], "chat_origem": ""}


def salvar_projeto(corte_id: str, projeto: dict, streamer: str = "") -> None:
    a = achar_corte(corte_id)
    limpo = normalizar(projeto)
    gravar_json(_arq_projeto(a), limpo)
    if streamer.strip() and streamer != a.info.get("streamer"):
        a.info["streamer"] = streamer.strip()[:60]
        gravar_json(a.pasta / "live.json", a.info)
    salvar_regioes(streamer or a.info.get("streamer", ""), limpo["regioes"])


def exportados(a: SimpleNamespace) -> list[dict]:
    pasta = a.pasta / "cortes" / "editados"
    lista = [e for e in ler_json(pasta / "editados.json", []) or [] if (pasta / e["arquivo"]).exists()]
    return [e for e in lista if e.get("origem") == a.corte["arquivo"]]


def _num(v, padrao: float, minimo: float, maximo: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return padrao
    return padrao if math.isnan(v) else max(minimo, min(maximo, v))


def _cor(v, padrao: str) -> str:
    return v if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) else padrao


def _fonte(v) -> str:
    return v if v in FONTES else "Arial Black"


def _regiao(r) -> dict | None:
    if not isinstance(r, dict):
        return None
    x, y = _num(r.get("x"), 0, 0, 0.98), _num(r.get("y"), 0, 0, 0.98)
    return {"x": x, "y": y, "w": _num(r.get("w"), 1, 0.02, 1 - x), "h": _num(r.get("h"), 1, 0.02, 1 - y)}


def _legenda(l: dict, L: int = LARGURA, A: int = ALTURA) -> dict:
    blocos = []
    for bloco in l.get("blocos") or []:
        palavras = [{"p": str(p.get("p", ""))[:40], "i": _num(p.get("i"), 0, 0, 86400), "f": _num(p.get("f"), 0, 0, 86400),
                     "d": bool(p.get("d")), "q": bool(p.get("q"))} for p in bloco if str(p.get("p", "")).strip()]
        if palavras:
            blocos.append(palavras)
    modo = l.get("modo") if l.get("modo") in ("atual", "karaoke", "marcadas", "nenhum") else "atual"
    return {"ativa": bool(l.get("ativa", True)), "fonte": _fonte(l.get("fonte")), "tamanho": _num(l.get("tamanho"), 76, 24, 200),
            "cor": _cor(l.get("cor"), "#FFFFFF"), "destaque": _cor(l.get("destaque"), "#FFE500"),
            "contorno": _cor(l.get("contorno"), "#000000"), "espessura": _num(l.get("espessura"), 7, 0, 24),
            "sombra": _num(l.get("sombra"), 3, 0, 20), "x": _num(l.get("x"), L / 2, 0, L), "y": _num(l.get("y"), A * 0.78, 0, A),
            "maxPalavras": int(_num(l.get("maxPalavras"), 3, 1, 8)), "maiusculas": bool(l.get("maiusculas", True)), "modo": modo,
            "anim": l.get("anim") if l.get("anim") in ANIMS else "nenhuma", "popPalavra": bool(l.get("popPalavra")),
            "chaves": str(l.get("chaves") or "")[:300], "corChave": _cor(l.get("corChave"), "#FF2D95"), "idioma": re.sub(r"[^a-z-]", "", str(l.get("idioma") or ""))[:8],
            "offset": _num(l.get("offset"), 0, -5, 5), "blocos": blocos}


def _caixa(caixa, w: float, h: float, L: int = LARGURA, A: int = ALTURA, minimo: float = 40) -> dict:
    caixa = caixa if isinstance(caixa, dict) else {}
    return {"x": _num(caixa.get("x"), 0, -L, L), "y": _num(caixa.get("y"), 0, -A, A),
            "w": _num(caixa.get("w"), w, minimo, L * 3), "h": _num(caixa.get("h"), h, minimo, A * 3)}


def _opcoes(o) -> dict:
    """Parâmetros do template (inverter, alturas...): só números, booleanos e textos curtos."""
    saida = {}
    for k, v in (o.items() if isinstance(o, dict) else []):
        k = re.sub(r"[^\w]", "", str(k))[:24]
        if isinstance(v, bool) or isinstance(v, (int, float)) and not math.isnan(v):
            saida[k] = v
        elif isinstance(v, str):
            saida[k] = v[:80]
    return dict(list(saida.items())[:30])


def normalizar(p: dict) -> dict:
    formato = p.get("formato") if p.get("formato") in FORMATOS else "9:16"
    L, A = FORMATOS[formato]
    camadas = []
    for c in (p.get("camadas") or [])[:24]:
        base = {"id": re.sub(r"[^\w-]", "", str(c.get("id", "")))[:24] or f"c{len(camadas)}", "nome": str(c.get("nome", ""))[:40],
                "visivel": bool(c.get("visivel", True))}
        if c.get("papel"):
            base["papel"] = re.sub(r"[^\w-]", "", str(c["papel"]))[:16]
        if c.get("tipo") == "video":
            regiao = c.get("regiao") if c.get("regiao") in (*REGIOES, "propria") else "gameplay"
            item = {**base, "tipo": "video", "regiao": regiao, "caixa": _caixa(c.get("caixa"), L, A, L, A),
                    "zoom": _num(c.get("zoom"), 1, 1, 6), "panX": _num(c.get("panX"), 0, -1, 1), "panY": _num(c.get("panY"), 0, -1, 1),
                    "borda": _num(c.get("borda"), 0, 0, 40), "bordaCor": _cor(c.get("bordaCor"), "#FF2D95")}
            if regiao == "propria":
                item["recorte"] = _regiao(c.get("recorte")) or {"x": 0, "y": 0, "w": 1, "h": 1}
            camadas.append(item)
        elif c.get("tipo") == "imagem":
            arquivo = re.sub(r"[^\w.-]", "", str(c.get("arquivo", "")))[:64]
            if arquivo and (GRAFICOS / arquivo).is_file():
                camadas.append({**base, "tipo": "imagem", "arquivo": arquivo, "caixa": _caixa(c.get("caixa"), 400, 400, L, A, 10),
                                "opacidade": _num(c.get("opacidade"), 1, 0, 1), "circular": bool(c.get("circular"))})
        elif c.get("tipo") == "forma":
            camadas.append({**base, "tipo": "forma", "caixa": _caixa(c.get("caixa"), L, 6, L, A, 1), "cor": _cor(c.get("cor"), "#FFFFFF"),
                            "alfa": _num(c.get("alfa"), 1, 0, 1)})
        elif c.get("tipo") == "chat":
            camadas.append({**base, "tipo": "chat", "caixa": _caixa(c.get("caixa"), 380, 900, L, A), "tamanho": _num(c.get("tamanho"), 30, 14, 80),
                            "cor": _cor(c.get("cor"), "#FFFFFF"), "contorno": _cor(c.get("contorno"), "#000000"),
                            "espessura": _num(c.get("espessura"), 3, 0, 12), "fundoCor": _cor(c.get("fundoCor"), "#000000"),
                            "fundoAlfa": _num(c.get("fundoAlfa"), 0.45, 0, 1)})
        elif c.get("tipo") == "texto":
            caixa = c.get("caixa") or {}
            camadas.append({**base, "tipo": "texto", "texto": str(c.get("texto", ""))[:300], "x": _num(c.get("x"), L / 2, -200, L + 200),
                            "y": _num(c.get("y"), A / 2, -200, A + 200), "fonte": _fonte(c.get("fonte")), "tamanho": _num(c.get("tamanho"), 72, 16, 260),
                            "cor": _cor(c.get("cor"), "#FFFFFF"), "contorno": _cor(c.get("contorno"), "#000000"), "espessura": _num(c.get("espessura"), 4, 0, 24),
                            "sombra": _num(c.get("sombra"), 0, 0, 20), "fundoAtivo": bool(c.get("fundoAtivo")), "fundoCor": _cor(c.get("fundoCor"), "#FF2D95"),
                            "fundoAlfa": _num(c.get("fundoAlfa"), 1, 0, 1), "raio": _num(c.get("raio"), 14, 0, 80),
                            "faixa": bool(c.get("faixa")), "altMin": _num(c.get("altMin"), 0, 0, 900), "quebra": str(c.get("quebra") or "")[:600],
                            "bordaFaixa": _num(c.get("bordaFaixa"), 0, 0, 30), "bordaFaixaCor": _cor(c.get("bordaFaixaCor"), "#000000"),
                            "destaque": _cor(c.get("destaque"), "#E10613"), "alinhar": "esquerda" if c.get("alinhar") == "esquerda" else "centro",
                            "largMax": _num(c.get("largMax"), 0, 0, L), "ini": _num(c.get("ini"), 0, 0, 86400), "fim": _num(c.get("fim"), 0, 0, 86400),
                            "anim": c.get("anim") if c.get("anim") in ANIMS else "nenhuma",
                            "caixa": {"w": _num(caixa.get("w"), 600, 10, L * 2), "h": _num(caixa.get("h"), 140, 10, A)}})
    regioes = p.get("regioes") or {}
    segs = efeitos.norm_segmentos(p)
    return {"versao": 3, "formato": formato, "inicio": min(s["ini"] for s in segs), "fim": max(s["fim"] for s in segs), "segmentos": segs,
            "preset": str(p.get("preset", "livre"))[:24],
            "fundo": _cor(p.get("fundo"), "#000000"), "fps": 60 if p.get("fps") == 60 else 30,
            "regioes": {"webcam": _regiao(regioes.get("webcam")), "gameplay": _regiao(regioes.get("gameplay")) or {"x": 0, "y": 0, "w": 1, "h": 1},
                        "chat": _regiao(regioes.get("chat")), "rosto": _regiao(regioes.get("rosto"))},
            "divisao": _num(p.get("divisao"), 0.42, 0.15, 0.85), "volume": _num(p.get("volume"), 1, 0, 3),
            "qualidade": p.get("qualidade") if p.get("qualidade") in QUALIDADES else "alta",
            "efeitos": efeitos.norm_efeitos(p.get("efeitos"), L, A), "audio": efeitos.norm_audio(p.get("audio"), _num(p.get("volume"), 1, 0, 3)),
            "cor": efeitos.norm_cor(p.get("cor")), "opcoes": _opcoes(p.get("opcoes")),
            "camadas": camadas, "legenda": _legenda(p.get("legenda") or {}, L, A)}


# ---------------------------------------------------------------- composição (mesma conta do editor.js)

def _par(v: float) -> int:
    return 2 * int(v / 2 + 0.5)


def recorte_efetivo(regiao: dict, caixa: dict, zoom: float, pan_x: float, pan_y: float, w: int, h: int) -> tuple[int, int, int, int]:
    rx, ry, rl, ra = regiao["x"] * w, regiao["y"] * h, regiao["w"] * w, regiao["h"] * h
    alvo = caixa["w"] / caixa["h"]
    l, a = (ra * alvo, ra) if rl / ra > alvo else (rl, rl / alvo)
    l, a = l / zoom, a / zoom
    cx, cy = rx + rl / 2 + pan_x * (rl - l) / 2, ry + ra / 2 + pan_y * (ra - a) / 2
    fl, fa = max(2, min(_par(l), w - w % 2)), max(2, min(_par(a), h - h % 2))
    return max(0, min(w - fl, _par(cx - l / 2))), max(0, min(h - fa, _par(cy - a / 2))), fl, fa


def recorte_cam(p: dict, bw: float, bh: float, w: int, h: int) -> tuple[int, int, int, int]:
    """Recorte da webcam para uma caixa bw x bh, centralizado no rosto (mesma conta do recorteCam em editor.js)."""
    r, f = p["regioes"]["webcam"], p["regioes"].get("rosto")
    rl, ra, alvo = r["w"] * w, r["h"] * h, bw / bh
    l, a = (ra * alvo, ra) if rl / ra > alvo else (rl, rl / alvo)
    cx, cy = r["x"] * w + rl / 2, r["y"] * h + ra / 2
    fx, fy = ((f["x"] + f["w"] / 2) * w, (f["y"] + f["h"] / 2) * h + 0.08 * a) if f else (cx, cy)
    pan_x = max(-1.0, min(1.0, (fx - cx) / ((rl - l) / 2))) if rl - l > 1 else 0.0
    pan_y = max(-1.0, min(1.0, (fy - cy) / ((ra - a) / 2))) if ra - a > 1 else 0.0
    return recorte_efetivo(r, {"w": bw, "h": bh}, 1, pan_x, pan_y, w, h)


def detectar_rosto(corte_id: str, regiao) -> dict:
    """Acha o rosto dentro da webcam marcada, para o zoom e a webcam ampliada não cortarem a pessoa."""
    try:
        import cv2
    except ImportError:
        return {"rosto": None}
    a = achar_corte(corte_id)
    meta, r = fonte_pronta(a), _regiao(regiao)
    if not meta or not r:
        return {"rosto": None}
    largura, altura = 960, 2 * round(960 * meta["h"] / meta["w"] / 2)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    x0, y0, x1, y1 = (int(v) for v in (r["x"] * largura, r["y"] * altura, (r["x"] + r["w"]) * largura, (r["y"] + r["h"]) * altura))
    achados = []
    for n in range(10):
        t = meta["dur"] * (n + 0.5) / 10
        bruto = subprocess.run([ffmpeg(), "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(LIVES / meta["arquivo"]), "-frames:v", "1",
                                "-vf", f"scale={largura}:{altura}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                               capture_output=True, creationflags=SEM_JANELA).stdout
        if len(bruto) != largura * altura:
            continue
        quadro = np.frombuffer(bruto, dtype=np.uint8).reshape(altura, largura)[y0:y1, x0:x1]
        rostos = detector.detectMultiScale(np.ascontiguousarray(quadro), 1.08, 5, minSize=(24, 24))
        if len(rostos):
            x, y, l, h = max(rostos, key=lambda q: q[2] * q[3])
            achados.append(((x0 + x) / largura, (y0 + y) / altura, l / largura, h / altura))
    if len(achados) < 3:
        return {"rosto": None}
    return {"rosto": {k: round(float(np.median([q[i] for q in achados])), 4) for i, k in enumerate("xywh")}}


def _hex(c: str) -> str:
    return "0x" + c[1:].upper()


def regiao_da_camada(p: dict, c: dict) -> dict | None:
    """Cada camada de vídeo recorta a mesma fonte: por uma região nomeada ou pelo próprio recorte."""
    return c.get("recorte") if c["regiao"] == "propria" else p["regioes"].get(c["regiao"])


def _circulo() -> str:
    return ("geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*clip(min(W,H)/2-hypot(X-W/2+0.5,Y-H/2+0.5)+0.5,0,1)'")


def montar_filtro(p: dict, fonte: dict, duracao: float, legenda: str, imagens: dict[str, int] | None = None, base: float | None = None,
                  vinhetas: dict[str, int] | None = None) -> str:
    """Segmentos -> camadas -> efeitos de câmera -> cor -> legendas -> flashes. Mesma ordem da prévia."""
    imagens, vinhetas = imagens or {}, vinhetas or {}
    segs, efs = p["segmentos"], [e for e in p["efeitos"] if e["ativo"] and e["ini"] < duracao]
    base = min(s["ini"] for s in segs) if base is None else base
    fps = p["fps"]
    LARGURA, ALTURA = dims(p)
    camadas = [c for c in p["camadas"] if c["visivel"] and ((c["tipo"] == "video" and regiao_da_camada(p, c)) or c["tipo"] == "forma" or
                                                            (c["tipo"] == "imagem" and c["id"] in imagens))]
    cheias = [e for e in efs if e["tipo"] == "cam_cheia"] if p["regioes"]["webcam"] else []
    alt_cam = {e["id"]: min(ALTURA, _par(max(0.3, e["forca"]) * ALTURA)) for e in cheias}  # parte da tela que a webcam ocupa
    consumidores = len([c for c in camadas if c["tipo"] == "video"]) + sum(1 if alt_cam[e["id"]] >= ALTURA else 2 for e in cheias)
    partes = [f"color=c={_hex(p['fundo'])}:s={LARGURA}x{ALTURA}:r={fps}:d={duracao:.3f},format=yuv420p[b0]"]
    if consumidores:
        if len(segs) == 1 and segs[0]["vel"] == 1:
            partes.append(f"[0:v]trim=start={segs[0]['ini'] - base:.3f}:end={segs[0]['fim'] - base:.3f},setpts=PTS-STARTPTS,fps={fps}[src]")
        else:
            partes.append(f"[0:v]split={len(segs)}" + "".join(f"[g{i}]" for i in range(len(segs))))
            for i, s in enumerate(segs):
                partes.append(f"[g{i}]trim=start={s['ini'] - base:.3f}:end={s['fim'] - base:.3f},setpts=(PTS-STARTPTS)/{s['vel']:.3f}[h{i}]")
            partes.append("".join(f"[h{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0,fps={fps}[src]")
        partes.append(f"[src]split={consumidores}" + "".join(f"[s{i}]" for i in range(consumidores)))
    atual, k, n = "b0", 0, 0

    def passo(texto: str) -> None:
        nonlocal atual, n
        n += 1
        partes.append(texto.replace("@@", f"[{atual}]") + f"[b{n}]")
        atual = f"b{n}"
    for i, c in enumerate(camadas):
        cx = c["caixa"]
        bl, ba = (_par(cx["w"]), _par(cx["h"])) if c["tipo"] != "forma" else (max(1, int(round(cx["w"]))), max(1, int(round(cx["h"]))))
        px, py = int(round(cx["x"])), int(round(cx["y"]))
        if c["tipo"] == "video":
            x, y, l, a = recorte_efetivo(regiao_da_camada(p, c), cx, c["zoom"], c["panX"], c["panY"], fonte["w"], fonte["h"])
            partes.append(f"[s{k}]crop={l}:{a}:{x}:{y},scale={bl}:{ba}:flags=lanczos,setsar=1[v{i}]")
            k += 1
            borda = ""
            if c["borda"] > 0:
                borda = f",drawbox=x={px}:y={py}:w={bl}:h={ba}:color={_hex(c['bordaCor'])}:t={int(c['borda'])}"
            passo(f"@@[v{i}]overlay={px}:{py}:eof_action=repeat:shortest=0{borda}")
        elif c["tipo"] == "forma":
            passo(f"@@drawbox=x={px}:y={py}:w={bl}:h={ba}:color={_hex(c['cor'])}@{c['alfa']:.3f}:t=fill")
        else:
            circ = "," + _circulo() if c["circular"] else ""
            partes.append(f"[{imagens[c['id']]}:v]scale={bl}:{ba}:flags=lanczos,format=rgba{circ},colorchannelmixer=aa={c['opacidade']:.3f}[v{i}]")
            passo(f"@@[v{i}]overlay={px}:{py}:shortest=0")
    for j, e in enumerate(cheias):  # webcam em tela cheia: recorte da fonte original, sem perder nitidez
        hc = alt_cam[e["id"]]
        liga = f"enable='between(t,{e['ini']:.3f},{e['fim']:.3f})'"
        x, y, l, a = recorte_cam(p, LARGURA, hc, fonte["w"], fonte["h"])
        partes.append(f"[s{k}]crop={l}:{a}:{x}:{y},scale={LARGURA}:{hc}:flags=lanczos,setsar=1[w{j}]")
        k += 1
        passo(f"@@[w{j}]overlay=0:0:eof_action=repeat:shortest=0:{liga}")
        if hc < ALTURA:  # o gameplay continua visível embaixo
            x, y, l, a = recorte_efetivo(p["regioes"]["gameplay"], {"w": LARGURA, "h": ALTURA - hc}, 1, 0, 0, fonte["w"], fonte["h"])
            partes.append(f"[s{k}]crop={l}:{a}:{x}:{y},scale={LARGURA}:{ALTURA - hc}:flags=lanczos,setsar=1[wg{j}]")
            k += 1
            passo(f"@@[wg{j}]overlay=0:{hc}:eof_action=repeat:shortest=0:{liga}")
    geo = efeitos.geometria(efs, LARGURA, ALTURA, fps)
    if geo:
        passo(f"@@{geo}")
    for j, e in enumerate(x for x in efs if x["tipo"] == "freeze"):
        a, b = int(math.ceil(e["ini"] * fps - 1e-6)), int(math.floor(min(e["fim"], duracao) * fps + 1e-6)) - 1
        if b > a:
            partes.append(f"[{atual}]split[fa{j}][fb{j}]")
            n += 1
            partes.append(f"[fa{j}][fb{j}]freezeframes=first={a + 1}:last={b}:replace={a}[b{n}]")
            atual = f"b{n}"
    cor = p["cor"]
    if abs(cor["contraste"] - 1) > 0.005 or abs(cor["saturacao"] - 1) > 0.005:
        passo(f"@@eq=contrast={cor['contraste']:.3f}:saturation={cor['contraste'] * cor['saturacao']:.3f}")
    sat = efeitos.saturacao(efs)
    if sat:
        passo(f"@@{sat}")
    if cor["barras"] > 0.001:
        h = int(round(cor["barras"] * ALTURA))
        passo(f"@@drawbox=x=0:y=0:w={LARGURA}:h={h}:color=black:t=fill,drawbox=x=0:y={ALTURA - h}:w={LARGURA}:h={h}:color=black:t=fill")
    for e in efs:
        if e["tipo"] == "vinheta" and e["id"] in vinhetas:
            partes.append(f"[{vinhetas[e['id']]}:v]format=rgba,{efeitos.alfa(e)}[vi{e['id']}]")
            passo(f"@@[vi{e['id']}]overlay=0:0:eof_action=pass:shortest=0")
    passo(f"@@ass={legenda}")
    brilhos = [{**e, "cor": "white"} for e in efs if e["tipo"] == "flash"] + [t for t in efeitos.transicoes(segs)]
    for j, e in enumerate(brilhos):
        partes.append(f"color=c={e['cor']}:s={LARGURA}x{ALTURA}:r={fps}:d={e['fim'] - e['ini']:.3f},format=rgba,{efeitos.alfa(e)}[fl{j}]")
        passo(f"@@[fl{j}]overlay=0:0:eof_action=pass:shortest=0")
    partes.append(f"[{atual}]format=yuv420p[v]")
    return ";".join(partes)


def montar_audio(p: dict, duracao: float, tem_audio: bool, base: float, clipes: list[tuple[dict, int]], env: dict[str, int]) -> str:
    """Original (por segmento) + música + efeitos sonoros, com envelopes de volume e limitador no final."""
    segs, partes, entradas = p["segmentos"], [], []
    padrao = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    if tem_audio:
        if len(segs) > 1:
            partes.append(f"[0:a]asplit={len(segs)}" + "".join(f"[ag{i}]" for i in range(len(segs))))
        for i, s in enumerate(segs):
            v, tempo = s["vel"], ""
            while v < 0.5:
                tempo, v = tempo + ",atempo=0.5", v / 0.5
            tempo += f",atempo={v:.4f}" if abs(v - 1) > 0.001 else ""
            d = (s["fim"] - s["ini"]) / s["vel"]
            emenda = f",afade=t=in:d=0.008,afade=t=out:st={max(0, d - 0.008):.3f}:d=0.008" if len(segs) > 1 else ""
            partes.append(f"[{'ag' + str(i) if len(segs) > 1 else '0:a'}]atrim=start={s['ini'] - base:.3f}:end={s['fim'] - base:.3f},asetpts=PTS-STARTPTS{tempo}{emenda}[ah{i}]")
        junta = "".join(f"[ah{i}]" for i in range(len(segs))) + (f"concat=n={len(segs)}:v=0:a=1," if len(segs) > 1 else "")
        partes.append(f"{junta}{padrao},apad,atrim=duration={duracao:.3f}[ao]")
    else:
        partes.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duracao:.3f}[ao]")

    def ganho(rotulo: str, nome: str) -> str:
        if nome not in env:
            return rotulo
        partes.append(f"[{env[nome]}:a]{padrao},apad[en{nome}]")
        partes.append(f"[{rotulo}][en{nome}]amultiply,atrim=duration={duracao:.3f}[m{nome}]")
        return f"m{nome}"
    entradas.append(ganho("ao", "original"))
    for trilha in ("musica", "sfx"):
        meus = [(c, i) for c, i in clipes if c["trilha"] == trilha and c["ini"] < duracao]
        for c, i in meus:
            fades = (f",afade=t=in:d={c['fadeIn']:.3f}" if c["fadeIn"] > 0 else "") + \
                    (f",afade=t=out:st={max(0, c['dur'] - c['fadeOut']):.3f}:d={c['fadeOut']:.3f}" if c["fadeOut"] > 0 else "")
            partes.append(f"[{i}:a]atrim=start={c['desde']:.3f}:duration={c['dur']:.3f},asetpts=PTS-STARTPTS,{padrao}{fades},volume={c['volume']:.3f},"
                          f"adelay={int(round(c['ini'] * 1000))}:all=1[c{c['id']}]")
        if meus:
            mix = "".join(f"[c{c['id']}]" for c, _ in meus) + (f"amix=inputs={len(meus)}:normalize=0:dropout_transition=0," if len(meus) > 1 else "")
            partes.append(f"{mix}apad,atrim=duration={duracao:.3f}[t{trilha}]")
            entradas.append(ganho(f"t{trilha}", trilha))
    mix = "".join(f"[{e}]" for e in entradas) + (f"amix=inputs={len(entradas)}:normalize=0:dropout_transition=0:duration=first," if len(entradas) > 1 else "")
    partes.append(f"{mix}alimiter=limit=0.95:attack=3:release=60:level=disabled[a]")
    return ";".join(partes)


# ---------------------------------------------------------------- ASS

def _cor_ass(c: str, alfa: float = 1.0) -> str:
    return f"&H{round((1 - alfa) * 255):02X}{c[5:7]}{c[3:5]}{c[1:3]}".upper()


def _so_cor(c: str) -> str:
    return f"&H{c[5:7]}{c[3:5]}{c[1:3]}&".upper()


def _tempo(t: float) -> str:
    return render._tempo(t)


def _limpar(t: str) -> str:
    return t.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\r", "")


def _estilo(nome: str, fonte: str, tam: float, cor: str, contorno: str, esp: float, sombra: float) -> str:
    return (f"Style: {nome},{fonte},{tam:g},{_cor_ass(cor)},&H000000FF,{_cor_ass(contorno)},&H96000000,0,0,0,0,100,100,0,0,1,"
            f"{esp:g},{sombra:g},5,0,0,0,1\n")


def _retangulo(l: int, a: int, r: int) -> str:
    r = min(r, l // 2, a // 2)
    if r <= 0:
        return f"m 0 0 l {l} 0 l {l} {a} l 0 {a}"
    return (f"m {r} 0 l {l - r} 0 b {l} 0 {l} 0 {l} {r} l {l} {a - r} b {l} {a} {l} {a} {l - r} {a} "
            f"l {r} {a} b 0 {a} 0 {a} 0 {a - r} l 0 {r} b 0 0 0 0 {r} 0")


def _chaves(leg: dict) -> set[str]:
    return {x for x in re.split(r"[\s,;]+", leg["chaves"].lower()) if x}


def _texto_bloco(bloco: list[dict], leg: dict, marcar: int | None, pop: bool = False) -> str:
    pedacos, chaves = [], _chaves(leg)
    for n, w in enumerate(bloco):
        t = _limpar(w["p"].upper() if leg["maiusculas"] else w["p"])
        forte = {"atual": n == marcar, "karaoke": marcar is not None and n <= marcar, "marcadas": bool(w.get("d"))}.get(leg["modo"], False)
        cor = leg["destaque"] if forte else leg["corChave"] if re.sub(r"[^\w]", "", w["p"].lower()) in chaves else None
        if cor:
            t = "{\\c" + _so_cor(cor) + "}" + t + "{\\c" + _so_cor(leg["cor"]) + "}"
        if pop and n == marcar:  # a palavra falada cresce por um instante
            t = "{\\fscx100\\fscy100\\t(0,70,\\fscx118\\fscy118)\\t(70,150,\\fscx100\\fscy100)}" + t + "{\\fscx100\\fscy100}"
        pedacos.append(("\\N" if w.get("q") and n else (" " if n else "")) + t)
    return "".join(pedacos)


def _anim(tipo: str, x: int, y: int, an: int, entrada: bool = True, saida: bool = True) -> str:
    """Entrada e saída do texto. Os mesmos tempos estão em efeitos.js (animTexto)."""
    pos = f"\\an{an}\\pos({x},{y})"
    if tipo == "fade":
        return f"{pos}\\fad({180 if entrada else 0},{180 if saida else 0})"
    if tipo == "subir" and entrada:
        return f"\\an{an}\\move({x},{y + 40},{x},{y},0,220)\\fad(150,{150 if saida else 0})"
    if tipo == "pop" and entrada:
        return f"{pos}\\fad(60,{120 if saida else 0})\\fscx70\\fscy70\\t(0,110,\\fscx112\\fscy112)\\t(110,200,\\fscx100\\fscy100)"
    if tipo in ("subir", "pop") and saida:
        return f"{pos}\\fad(0,{150 if tipo == 'subir' else 120})"
    return pos


def _marcado(linhas: list[str], cor: str, destaque: str) -> str:
    """*palavra* troca a cor; a marcação pode atravessar linhas."""
    forte, saida = False, []
    for linha in linhas:
        pedacos = linha.split("*")
        texto = ("{\\c" + _so_cor(destaque) + "}") if forte else ""
        for i, ped in enumerate(pedacos):
            if i:
                forte = not forte
                texto += "{\\c" + _so_cor(destaque if forte else cor) + "}"
            texto += _limpar(ped)
        saida.append(texto)
    return "\\N".join(saida)


def _forma(x: int, y: int, l: int, a: int, cor: str, alfa: float, raio: int, camada: int, fim: str, estilo: str, ini: str = "0:00:00.00", extra: str = "") -> str:
    tag = f"{{\\an7\\pos({x},{y})\\bord0\\shad0\\1c{_so_cor(cor)}\\1a&H{round((1 - alfa) * 255):02X}&{extra}\\p1}}"
    return f"Dialogue: {camada},{ini},{fim},{estilo},,0,0,0,,{tag}{_retangulo(l, a, raio)}{{\\p0}}\n"


def chat_visivel(msgs: list[dict], t: float, altura: float, lh: float, espaco: float) -> list[dict]:
    """Mensagens que cabem na coluna no instante t, da mais nova para a mais antiga (mesma conta do editor.js)."""
    vis, usado = [], 0.0
    for m in reversed([m for m in msgs if m["t"] <= t]):
        alt = len(m["l"]) * lh + (espaco if vis else 0)
        if usado + alt > altura:
            break
        vis.append(m)
        usado += alt
    return vis


def _eventos_chat(n: int, c: dict, msgs: list[dict], inicio: float, duracao: float, fim: str, t0: float = 0.0, vel: float = 1.0, fundo: bool = True) -> tuple[str, list[str]]:
    tam = c["tamanho"]
    pad, lh, espaco = (int(math.floor(tam * k + 0.5)) for k in (0.4, 1.18, 0.3))  # igual ao Math.round do editor.js
    cx = c["caixa"]
    x0, y0, l, a = int(round(cx["x"])), int(round(cx["y"])), int(round(cx["w"])), int(round(cx["h"]))
    eventos = [_forma(x0, y0, l, a, c["fundoCor"], c["fundoAlfa"], 14, 50, fim, f"C{n}")] if c["fundoAlfa"] > 0 and fundo else []
    msgs = sorted((m for m in msgs if m.get("l")), key=lambda m: m["t"])
    pontos = sorted({inicio, *(m["t"] for m in msgs if inicio < m["t"] < inicio + duracao)})
    for k, t in enumerate(pontos):
        ate = pontos[k + 1] if k + 1 < len(pontos) else inicio + duracao
        base = y0 + a - pad
        for m in chat_visivel(msgs, t, a - 2 * pad, lh, espaco):
            base -= len(m["l"]) * lh
            for j, linha in enumerate(m["l"]):
                corpo = _limpar(linha)
                if j == 0 and m.get("k"):
                    corpo = "{\\c" + _so_cor(m["c"]) + "}" + _limpar(linha[: m["k"]]) + "{\\c" + _so_cor(c["cor"]) + "}" + _limpar(linha[m["k"]:])
                eventos.append(f"Dialogue: 51,{_tempo(t0 + (t - inicio) / vel)},{_tempo(t0 + (ate - inicio) / vel)},C{n},,0,0,0,,"
                               f"{{\\an7\\pos({x0 + pad},{int(base + j * lh)})}}{corpo}\n")
            base -= espaco
    return _estilo(f"C{n}", "Arial", tam, c["cor"], c["contorno"], c["espessura"], 0), eventos


def gerar_ass(p: dict, duracao: float, chat: list[dict] | None = None) -> str:
    estilos_ass, eventos = [_estilo("L", p["legenda"]["fonte"], p["legenda"]["tamanho"], p["legenda"]["cor"], p["legenda"]["contorno"],
                                    p["legenda"]["espessura"], p["legenda"]["sombra"])], []
    fim = _tempo(duracao)
    segs = p["segmentos"]
    inicios, _ = efeitos.mapa(segs)
    textos = [c for c in p["camadas"] if c["tipo"] == "texto" and c["visivel"] and c["texto"].strip()]
    for n, c in enumerate(textos):
        estilos_ass.append(_estilo(f"T{n}", c["fonte"], c["tamanho"], c["cor"], c["contorno"], c["espessura"], c["sombra"]))
        x, y = int(round(c["x"])), int(round(c["y"]))
        l, a = int(round(c["caixa"]["w"])), int(round(c["caixa"]["h"]))
        cronometrado = c["fim"] > c["ini"]  # título editorial: aparece só no intervalo
        t_a, t_b = (_tempo(c["ini"]), _tempo(min(c["fim"], duracao))) if cronometrado else ("0:00:00.00", fim)
        if cronometrado and c["ini"] >= duracao:
            continue
        anim = c["anim"] if cronometrado else "nenhuma"
        if c["fundoAtivo"]:
            some = "\\fad(150,150)" if anim != "nenhuma" else ""
            eventos.append(_forma(x - l // 2, y - a // 2, l, a, c["fundoCor"], c["fundoAlfa"], int(c["raio"]), n * 2, t_b, f"T{n}", t_a, some))
            if c["bordaFaixa"] > 0:
                t = int(c["bordaFaixa"])
                for yy in (y - a // 2, y - a // 2 + a - t):
                    eventos.append(_forma(x - l // 2, yy, l, t, c["bordaFaixaCor"], 1, 0, n * 2, t_b, f"T{n}", t_a, some))
        corpo = _marcado((c["quebra"] or c["texto"]).split("\n"), c["cor"], c["destaque"])
        tx, an = (x - l // 2 + (40 if c["faixa"] else 36), 4) if c["alinhar"] == "esquerda" else (x, 5)
        eventos.append(f"Dialogue: {n * 2 + 1},{t_a},{t_b},T{n},,0,0,0,,{{{_anim(anim, tx, y, an)}}}{corpo}\n")
    for n, c in enumerate(c for c in p["camadas"] if c["tipo"] == "chat" and c["visivel"]):
        for k, (s, t0) in enumerate(zip(segs, inicios)):
            estilo, evs = _eventos_chat(n, c, chat or [], s["ini"], s["fim"] - s["ini"], fim, t0, s["vel"], k == 0)
            eventos += evs
        estilos_ass.append(estilo)

    leg = p["legenda"]
    if leg["ativa"]:
        lx, ly = int(round(leg["x"])), int(round(leg["y"]))
        blocos = leg["blocos"]
        for g, bloco in enumerate(blocos):
            prox = blocos[g + 1][0]["i"] if g + 1 < len(blocos) else float("inf")
            if leg["modo"] in ("atual", "karaoke"):
                trechos = [(w["i"], bloco[n + 1]["i"] if n + 1 < len(bloco) else min(w["f"] + 0.15, prox), n) for n, w in enumerate(bloco)]
            else:
                trechos = [(bloco[0]["i"], min(bloco[-1]["f"] + 0.15, prox), None)]
            for j, (ini, ate, marca) in enumerate(trechos):
                for ta, tb in efeitos.intervalos_na_saida(segs, ini + leg["offset"], ate + leg["offset"]):
                    tb = min(tb, duracao)
                    if tb > ta:
                        tag = _anim(leg["anim"], lx, ly, 5, j == 0, j == len(trechos) - 1)
                        eventos.append(f"Dialogue: 100,{_tempo(ta)},{_tempo(tb)},L,,0,0,0,,{{{tag}}}{_texto_bloco(bloco, leg, marca, leg['popPalavra'])}\n")
    L, A = dims(p)
    cabecalho = render.CABECALHO.split("[V4+ Styles]")[0].replace("PlayResX: 1080", f"PlayResX: {L}").replace("PlayResY: 1920", f"PlayResY: {A}")
    formato = render.CABECALHO.split("\n")[8] + "\n"
    return (cabecalho + "[V4+ Styles]\n" + formato + "".join(estilos_ass) + "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + "".join(eventos))


# ---------------------------------------------------------------- lixeira

LIXEIRA = DADOS / "lixeira"


def _para_lixeira(arq: Path, pasta: Path) -> None:
    if arq.is_file():
        pasta = pasta / arq.parent.name  # cortes, fontes, projetos, editados: nomes iguais não se sobrescrevem
        pasta.mkdir(parents=True, exist_ok=True)
        arq.replace(pasta / arq.name)


def excluir_corte(corte_id: str, editado: str = "") -> dict:
    """Tira o corte (ou só um Reel exportado dele) do painel e guarda o necessário para desfazer."""
    r = _excluir(corte_id, editado)
    return r


def _excluir(corte_id: str, editado: str = "") -> dict:
    """Tira o corte (ou só um Reel exportado dele) do painel. Os arquivos vão para a pasta lixeira, não são apagados."""
    a = achar_corte(corte_id)
    destino = LIXEIRA / time.strftime("%Y-%m-%d_%H%M%S") / a.stem
    pasta_ed = a.pasta / "cortes" / "editados"
    lista_ed = ler_json(pasta_ed / "editados.json", []) or []
    if editado:
        nome = Path(editado).name
        if not any(e["arquivo"] == nome and e.get("origem") == a.corte["arquivo"] for e in lista_ed):
            raise ValueError("Reel não encontrado.")
        _para_lixeira(pasta_ed / nome, destino)
        gravar_json(pasta_ed / "editados.json", [e for e in lista_ed if e["arquivo"] != nome])
        gravar_json(destino / "corte.json", {"id": a.id, "so_reel": True, "editados": [e for e in lista_ed if e["arquivo"] == nome]})
        return {"ok": True, "lixeira": str(destino)}
    for e in lista_ed:
        if e.get("origem") == a.corte["arquivo"]:
            _para_lixeira(pasta_ed / e["arquivo"], destino)
    gravar_json(pasta_ed / "editados.json", [e for e in lista_ed if e.get("origem") != a.corte["arquivo"]])
    for arq in (a.pasta / "cortes" / a.corte["arquivo"], _arq_projeto(a), *(a.pasta / "fontes").glob(f"{a.stem}.*")):
        _para_lixeira(arq, destino)
    gravar_json(destino / "corte.json", {"corte": a.corte, "live": a.info, "id": a.id,
                                         "editados": [e for e in lista_ed if e.get("origem") == a.corte["arquivo"]]})
    lista = ler_json(a.pasta / "cortes" / "cortes.json", []) or []
    gravar_json(a.pasta / "cortes" / "cortes.json", [c for c in lista if c.get("arquivo") != a.corte["arquivo"]])
    return {"ok": True, "lixeira": str(destino)}


def excluir_varios(ids: list, editado: str = "") -> dict:
    lixeiras, erros = [], []
    for i in [str(x) for x in ids][:300]:
        try:
            lixeiras.append(_excluir(i, editado)["lixeira"])
        except ValueError as e:
            erros.append(f"{i}: {e}")
    return {"ok": True, "lixeiras": lixeiras, "erros": erros}


def restaurar(lixeiras: list) -> dict:
    """Desfaz exclusões: devolve os arquivos ao lugar e as entradas às listas."""
    raiz, voltou = LIXEIRA.resolve(), 0
    for caminho in [str(x) for x in lixeiras][:300]:
        pasta = Path(caminho).resolve()
        info = ler_json(pasta / "corte.json") if raiz in pasta.parents else None
        if not info:
            continue
        plat, live, _ = info["id"].split("/")
        base = (LIVES / plat / live).resolve()
        if LIVES.resolve() not in base.parents:
            continue
        destinos = {"cortes": base / "cortes", "fontes": base / "fontes", "projetos": base / "projetos", "editados": base / "cortes" / "editados"}
        for sub, alvo in destinos.items():
            for arq in (pasta / sub).glob("*") if (pasta / sub).is_dir() else []:
                alvo.mkdir(parents=True, exist_ok=True)
                arq.replace(alvo / arq.name)
        if info.get("corte"):
            lista = ler_json(base / "cortes" / "cortes.json", []) or []
            if not any(c.get("arquivo") == info["corte"]["arquivo"] for c in lista):
                gravar_json(base / "cortes" / "cortes.json", lista + [info["corte"]])
        if info.get("editados"):
            eds = ler_json(base / "cortes" / "editados" / "editados.json", []) or []
            nomes = {e["arquivo"] for e in eds}
            gravar_json(base / "cortes" / "editados" / "editados.json", eds + [e for e in info["editados"] if e["arquivo"] not in nomes])
        (pasta / "corte.json").unlink(missing_ok=True)
        voltou += 1
    return {"ok": True, "restaurados": voltou}


# ---------------------------------------------------------------- exportação

def codificadores(qualidade: str) -> dict[str, list[str]]:
    """Taxa alvo fixa por qualidade: assim dá para estimar o tamanho antes de renderizar."""
    bps = QUALIDADES.get(qualidade, QUALIDADES["alta"])
    alvo, teto, buffer = f"{bps // 1000}k", f"{bps * 3 // 2000}k", f"{bps * 2 // 1000}k"
    return {
        "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-b:v", alvo, "-maxrate", teto,
                       "-bufsize", buffer, "-spatial-aq", "1", "-profile:v", "high"],
        "libx264": ["-c:v", "libx264", "-preset", "medium", "-b:v", alvo, "-maxrate", teto, "-bufsize", buffer, "-profile:v", "high"],
    }


def tamanho_estimado(qualidade: str, duracao: float) -> int:
    return int((QUALIDADES.get(qualidade, QUALIDADES["alta"]) + AUDIO_BPS) * duracao / 8)


def _entrada_original(meta: dict, inicio: float) -> tuple[str, float]:
    """Arquivo do PC: lê direto do original para não comprimir duas vezes. Senão, usa a fonte preparada."""
    original = meta.get("origem_local")
    if original and Path(original).is_file():
        return original, float(meta["t0"]) + inicio
    return str(LIVES / meta["arquivo"]), inicio


def preparar_render(a: SimpleNamespace, meta: dict, p: dict, pasta: Path, prefixo: str, chat: list[dict] | None = None, com_audio: bool = True) -> tuple[list[str], float, list[Path]]:
    """Monta as entradas e os filtros do ffmpeg. Usado pela exportação e pelo quadro de conferência."""
    for s in p["segmentos"]:
        s["ini"] = max(0.0, min(s["ini"], meta["dur"] - 0.2))
        s["fim"] = min(meta["dur"], s["fim"])
    p["segmentos"] = [s for s in p["segmentos"] if s["fim"] - s["ini"] >= 0.2]
    if not p["segmentos"]:
        raise ValueError("O corte precisa ter pelo menos 1 segundo.")
    segs = p["segmentos"]
    _, duracao = efeitos.mapa(segs)
    if duracao < 1:
        raise ValueError("O corte precisa ter pelo menos 1 segundo.")
    p["inicio"], p["fim"] = min(s["ini"] for s in segs), max(s["fim"] for s in segs)
    base = p["inicio"]
    L, A = dims(p)
    temporarios = [pasta / f"{prefixo}.ass"]
    temporarios[0].write_text(gerar_ass(p, duracao, chat), encoding="utf-8")
    entrada, desde = _entrada_original(meta, base)
    tem_audio = bool(sondar(Path(entrada))["audio"])
    extras, n = [], 1

    def nova(*args: str) -> int:
        nonlocal n
        extras.extend(args)
        n += 1
        return n - 1
    imagens = {c["id"]: nova("-loop", "1", "-t", f"{duracao:.3f}", "-i", str(GRAFICOS / c["arquivo"]))
               for c in p["camadas"] if c["tipo"] == "imagem" and c["visivel"]}
    vinheta = str(efeitos.vinheta_png(L, A, GRAFICOS))
    vinhetas = {e["id"]: nova("-loop", "1", "-framerate", str(p["fps"]), "-t", f"{e['fim'] - e['ini']:.3f}", "-i", vinheta)
                for e in p["efeitos"] if e["tipo"] == "vinheta" and e["ativo"] and e["ini"] < duracao}
    au = p["audio"]
    if not com_audio:
        filtro = montar_filtro(p, meta, duracao, temporarios[0].name, imagens, base, vinhetas)
        return ["-ss", f"{desde:.3f}", "-t", f"{p['fim'] - base + 0.5:.3f}", "-i", entrada, *extras, "-filter_complex", filtro], duracao, temporarios
    clipes = [(c, nova(*(["-stream_loop", "-1"] if c["trilha"] == "musica" else []), "-i", str(efeitos.arquivo_som(c["arquivo"]))))
              for c in au["clipes"] if c["ini"] < duracao]
    falas = efeitos.falas_na_saida([w for b in p["legenda"]["blocos"] for w in b], segs)
    env = {}
    for nome in ("original", "musica", "sfx"):
        if nome != "original" and not any(c["trilha"] == nome for c, _ in clipes):
            continue
        g = efeitos.envelope(au[nome], duracao, falas if nome == "musica" else None, au["ducking"])
        if not efeitos.trivial(g):
            arq = pasta / f"{prefixo}_{nome}.f32"
            efeitos.gravar_envelope(g, arq)
            temporarios.append(arq)
            env[nome] = nova("-f", "f32le", "-ar", str(efeitos.TAXA_ENV), "-ac", "2", "-i", arq.name)
    filtro = montar_filtro(p, meta, duracao, temporarios[0].name, imagens, base, vinhetas)
    filtro += ";" + montar_audio(p, duracao, tem_audio, base, clipes, env)
    args = ["-ss", f"{desde:.3f}", "-t", f"{p['fim'] - base + 0.5:.3f}", "-i", entrada, *extras, "-filter_complex", filtro]
    return args, duracao, temporarios


def exportar(corte_id: str, projeto: dict, tarefa=None, chat: list[dict] | None = None) -> dict:
    a = achar_corte(corte_id)
    meta = fonte_pronta(a)
    if not meta:
        raise ValueError("A fonte deste corte ainda não foi preparada.")
    p = normalizar(projeto)
    pasta = a.pasta / "cortes" / "editados"
    pasta.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(m[1]) for f in pasta.glob(f"{a.stem}_ed*.mp4") if (m := re.search(r"_ed(\d+)\.mp4$", f.name))], default=0)
    saida = pasta / f"{a.stem}_ed{n:02d}.mp4"
    temp = pasta / f"_{saida.stem}.mp4"
    args, duracao, temporarios = preparar_render(a, meta, p, pasta, f"_{saida.stem}", chat)
    inicio = p["inicio"]
    base = [ffmpeg(), "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args, "-map", "[v]", "-map", "[a]",
            "-t", f"{duracao:.3f}", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    erro, usado = "", None
    try:
        for nome, opcoes in codificadores(p["qualidade"]).items():
            proc = subprocess.Popen(base + opcoes + [temp.name], cwd=pasta, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
            try:
                for linha in proc.stdout:
                    if linha.startswith("out_time_us=") and tarefa and linha[12:].strip().isdigit():
                        tarefa.avancar(min(0.98, int(linha[12:]) / 1e6 / duracao), f"Renderizando ({nome})")
            except BaseException:  # tarefa cancelada no meio do render: encerra o ffmpeg para o arquivo pela metade poder ser apagado
                proc.kill()
                proc.wait()
                raise
            erro = proc.stderr.read()
            if proc.wait() == 0:
                usado = nome
                break
        if not usado:
            raise RuntimeError(f"ffmpeg falhou: {erro[-500:]}")
        temp.replace(saida)
    finally:
        for t in temporarios:
            t.unlink(missing_ok=True)
        temp.unlink(missing_ok=True)
    s = sondar(saida)
    item = {"arquivo": saida.name, "origem": a.corte["arquivo"], "preset": p["preset"], "duracao": round(s["dur"], 2),
            "largura": s["w"], "altura": s["h"], "codificador": usado, "qualidade": p["qualidade"], "bytes": saida.stat().st_size,
            "inicio": inicio, "criado": round(time.time()),
            "url": "/video/" + saida.resolve().relative_to(LIVES.resolve()).as_posix(),
            "fonte_url": "/video/" + meta["arquivo"], "pasta": f"{a.plataforma}/{a.live}/cortes/editados"}
    gravar_json(pasta / "editados.json", (ler_json(pasta / "editados.json", []) or []) + [item])
    gravar_json(_arq_projeto(a), p)
    return item


def quadro(corte_id: str, projeto: dict, t: float, chat: list[dict] | None = None) -> bytes:
    """Um quadro PNG do vídeo final no instante t (tempo de saída): serve para conferir a prévia contra o export."""
    a = achar_corte(corte_id)
    meta = fonte_pronta(a)
    if not meta:
        raise ValueError("A fonte deste corte ainda não foi preparada.")
    p = normalizar(projeto)
    pasta = a.pasta / "cortes" / "editados"
    pasta.mkdir(parents=True, exist_ok=True)
    args, duracao, temporarios = preparar_render(a, meta, p, pasta, f"_quadro_{int(time.time() * 1000) % 10 ** 9}", chat, False)
    try:
        r = subprocess.run([ffmpeg(), "-y", "-loglevel", "error", *args, "-map", "[v]", "-an", "-ss", f"{max(0.0, min(t, duracao - 0.05)):.3f}",
                            "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"], cwd=pasta, capture_output=True, creationflags=SEM_JANELA)
    finally:
        for arq in temporarios:
            arq.unlink(missing_ok=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("ffmpeg falhou: " + r.stderr.decode("utf-8", "replace")[-400:])
    return r.stdout


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 4 and sys.argv[1] == "transcrever":
        _transcrever_agora(sys.argv[2], sys.argv[3])
