"""Biblioteca de referências: links salvos com metadados públicos, análise de arquivos autorizados e boas práticas com fonte.

Nada de login, cookies ou download dos links: só o que a plataforma mostra em público. A análise de vídeo roda
apenas em arquivos do PC que o usuário declara ter direito de usar, com quadros pequenos e poucos por segundo.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

from . import fontes
from .config import DADOS, ffmpeg, gravar_json, ler_json
from .editor import sondar
from .tarefas import fila

PASTA = DADOS / "referencias"
ARQ = PASTA / "referencias.json"
VERIFICACAO = PASTA / "verificacao.json"
BOAS = Path(__file__).with_name("boas_praticas.json")
SEM_JANELA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
trava = threading.Lock()

PLATAFORMAS = {"instagram": "Instagram", "tiktok": "TikTok", "twitch": "Twitch", "youtube": "YouTube", "arquivo": "Arquivo do PC"}
DOMINIOS = (("instagram", ("instagram.com", "instagr.am")), ("tiktok", ("tiktok.com",)), ("twitch", ("twitch.tv",)),
            ("youtube", ("youtube.com", "youtu.be", "youtube-nocookie.com")))
ETIQUETAS = ["choque", "editorial", "humor", "reação", "ranking", "cinemático", "gameplay", "podcast", "meme", "tutorial"]
TEMPLATES = {
    "editorial_branco": ("Editorial branco", "Faixa clara com título editorial e o vídeo abaixo."),
    "pagina_viral": ("Página viral", "Título grande no topo, vídeo no meio e espaço para a marca da página."),
    "cam_titulo_jogo": ("Vice Cortes Clássico", "Webcam em cima, faixa com título e gameplay embaixo."),
    "cam_jogo": ("Webcam em cima, jogo embaixo", "Duas regiões empilhadas, sem faixa."),
    "jogo_cam": ("Jogo em cima, webcam embaixo", "Duas regiões empilhadas, com a câmera embaixo."),
    "reacao_destaque": ("Reação em destaque", "A câmera do streamer é a protagonista."),
    "ranking": ("Ranking", "Partes numeradas, com título que muda a cada item."),
    "choque": ("Choque", "Cortes rápidos com impactos visuais e sonoros."),
    "humor": ("Humor", "Pausas, quadro congelado e efeitos no tempo da piada."),
    "cinematico": ("Cinemático", "Planos longos, barras e cor tratada."),
    "jogo_cheio": ("Gameplay em tela cheia", "Só o jogo, recortado sem distorcer."),
    "jogo_cam_sobre": ("Webcam sobreposta", "Jogo cheio com a webcam pequena por cima."),
    "livre": ("Layout livre", "Camadas soltas para montar do seu jeito."),
}
EFEITOS = {"pb": "Preto e branco", "zoom_cam": "Zoom na webcam", "cam_cheia": "Webcam em tela cheia", "flash": "Flash",
           "tremor": "Tremor", "freeze": "Congelar quadro", "vinheta": "Vinheta"}
VIDEOS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".ts", ".flv", ".avi"}
AUTORIZACAO = "Tenho direito de usar e analisar este arquivo (é meu, tenho permissão do criador ou licença)."
AVISO = ("Heurísticas com confiança declarada, medidas em quadros reduzidos. Não há reconhecimento de emoções. "
         "As sugestões são inspiração: nada do vídeo de referência é copiado nem reaproveitado.")
TEMPO_METADADOS = 40
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) verificador-de-links"
FPS = 5             # quadros por segundo amostrados
LADO = 480          # lado maior do quadro reduzido
LIMIAR_CENA = 0.3   # select='gt(scene,0.3)'
BLOCOS = 4          # partes do vídeo usadas para medir persistência
PADRAO, LIMITE = 180.0, 600.0


def iniciar() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)


def _agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _texto(v, limite: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limite]


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _etiquetas(v) -> list[str]:
    bruto = v if isinstance(v, list) else str(v or "").split(",")
    saida = []
    for e in bruto:
        e = _texto(e, 30).lower().lstrip("#")
        if e and e not in saida:
            saida.append(e)
    return saida[:12]


# ---------------------------------------------------------------- links

def identificar(url: str) -> tuple[str, str]:
    """Plataforma e formato pelo endereço."""
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ValueError("Cole o link completo do vídeo, começando com https://.")
    host, caminho = partes.hostname.lower(), partes.path.lower()
    plat = next((p for p, doms in DOMINIOS if any(host == d or host.endswith("." + d) for d in doms)), None)
    if not plat:
        raise ValueError("Use um link do Instagram, TikTok, Twitch ou YouTube.")
    if plat == "instagram":
        formato = "Reel" if re.match(r"/(reels?)/", caminho) else "Post" if caminho.startswith("/p/") else "IGTV" if caminho.startswith("/tv/") else "Link"
    elif plat == "tiktok":
        formato = "Vídeo" if "/video/" in caminho else "Link curto" if host.split(".")[0] in ("vm", "vt") else "Link"
    elif plat == "twitch":
        formato = "Clip" if host.startswith("clips.") or "/clip/" in caminho else "VOD" if caminho.startswith("/videos/") else "Canal"
    else:
        formato = "Shorts" if caminho.startswith("/shorts/") else "Live" if caminho.startswith("/live/") else "Vídeo"
    return plat, formato


def _chave_url(url: str) -> str:
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    chave = host + p.path.rstrip("/").lower()
    if p.path.rstrip("/") == "/watch":
        chave += "?v=" + (parse_qs(p.query).get("v") or [""])[0]
    return chave


def _ler() -> list[dict]:
    return ler_json(ARQ, []) or []


def _achar(itens: list[dict], ref_id) -> dict:
    ref = next((r for r in itens if r["id"] == str(ref_id or "")), None)
    if not ref:
        raise ValueError("Referência não encontrada.")
    return ref


def listar(_consulta=None) -> dict:
    return {"itens": _ler(), "plataformas": PLATAFORMAS, "etiquetas": ETIQUETAS, "autorizacao": AUTORIZACAO,
            "templates": {k: {"nome": n, "desc": d} for k, (n, d) in TEMPLATES.items()}, "efeitos": EFEITOS,
            "limite": {"padrao": PADRAO, "maximo": LIMITE}}


def salvar(d: dict) -> dict:
    url = _texto(d.get("url"), 800)
    campos = {"origem": _texto(d.get("origem"), 200), "estilo": _texto(d.get("estilo"), 200),
              "etiquetas": _etiquetas(d.get("etiquetas")), "observacoes": str(d.get("observacoes") or "").strip()[:2000]}
    with trava:
        itens = _ler()
        atual = _achar(itens, d["id"]) if d.get("id") else None
        if url:
            plat, formato = identificar(url)
            if any(r is not atual and r.get("url") and _chave_url(r["url"]) == _chave_url(url) for r in itens):
                raise ValueError("Esse link já está na biblioteca.")
        elif atual and atual["plataforma"] == "arquivo":
            plat, formato = "arquivo", atual.get("formato", "Arquivo")
        else:
            raise ValueError("Cole o link do vídeo (Instagram, TikTok, Twitch ou YouTube).")
        if atual:
            if url != atual.get("url"):
                atual["metadados"] = {"estado": "pendente"}
            atual.update(campos, url=url, plataforma=plat, formato=formato, editado_em=_agora())
        else:
            atual = {"id": uuid.uuid4().hex[:10], "url": url, "plataforma": plat, "formato": formato, "salvo_em": _agora(),
                     **campos, "metadados": {"estado": "pendente"}, "analise": None}
            itens.insert(0, atual)
        gravar_json(ARQ, itens)
    return {"item": atual}


def remover(d: dict) -> dict:
    """Tira da biblioteca. O arquivo analisado continua onde estava: ele nunca é copiado."""
    with trava:
        itens = _ler()
        ref = _achar(itens, d.get("id"))
        gravar_json(ARQ, [r for r in itens if r is not ref])
    return {"ok": True}


def _indisponivel(motivo: str, detalhe: str = "") -> dict:
    return {"estado": "indisponivel", "consultado_em": _agora(), "motivo": motivo, **({"detalhe": detalhe[:240]} if detalhe else {})}


def consultar_publico(url: str) -> dict:
    """Metadados públicos pelo yt-dlp, sem baixar, sem login e sem cookies. Se a plataforma recusar, só registra."""
    cmd = [*fontes.YTDLP, "-J", "--skip-download", "--flat-playlist", "--no-cookies", "--no-cookies-from-browser",
           "--socket-timeout", "15", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TEMPO_METADADOS, creationflags=SEM_JANELA)
    except subprocess.TimeoutExpired:
        return _indisponivel("A plataforma não respondeu a tempo.")
    if r.returncode != 0:
        linhas = [l.strip() for l in r.stderr.splitlines() if l.strip()]
        erro = re.sub(r"\x1b\[[0-9;]*m", "", linhas[-1] if linhas else "")
        login = re.search(r"log ?in|sign in|cookies|private|rate.?limit|authenticat|not available|registered users", erro, re.I)
        return _indisponivel("Metadados indisponíveis: a plataforma exige login ou recusou o acesso público. Nada foi contornado."
                             if login else "Metadados indisponíveis: a plataforma não liberou os dados deste link.", erro)
    try:
        dados = json.loads(r.stdout)
    except ValueError:
        return _indisponivel("Metadados indisponíveis: resposta inesperada da plataforma.")
    if dados.get("_type") == "playlist":
        return _indisponivel("Este link é de um canal ou lista. Salve o link de um vídeo para ver os dados.")
    data = str(dados.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", data):
        data = f"{data[:4]}-{data[4:6]}-{data[6:]}"
    elif isinstance(dados.get("timestamp"), (int, float)):
        data = time.strftime("%Y-%m-%d", time.localtime(dados["timestamp"]))
    mini = dados.get("thumbnail") if str(dados.get("thumbnail") or "").startswith("https://") else None
    num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    campos = {"titulo": _texto(dados.get("title"), 200),
              "autor": _texto(dados.get("uploader") or dados.get("channel") or dados.get("creator") or dados.get("uploader_id"), 120),
              "duracao": round(float(num(dados.get("duration"))), 1) if num(dados.get("duration")) else None,
              "data": data or None, "visualizacoes": int(num(dados.get("view_count"))) if num(dados.get("view_count")) is not None else None,
              "miniatura": mini}
    campos = {k: v for k, v in campos.items() if v not in (None, "")}
    if not campos:
        return _indisponivel("Metadados indisponíveis: a plataforma não informou dados públicos.")
    return {"estado": "ok", "consultado_em": _agora(), **campos}


def metadados(d: dict) -> dict:
    with trava:
        url = _achar(_ler(), d.get("id")).get("url")
    if not url:
        raise ValueError("Esta referência não tem link.")
    meta = consultar_publico(url)
    with trava:
        itens = _ler()
        ref = _achar(itens, d.get("id"))
        ref["metadados"] = meta
        gravar_json(ARQ, itens)
    return {"item": ref}


# ---------------------------------------------------------------- análise de arquivo autorizado

def _escolher_arquivo() -> str:
    codigo = ("import tkinter as t, tkinter.filedialog as f; r=t.Tk(); r.withdraw(); r.attributes('-topmost', True); "
              "print(f.askopenfilename(title='Escolha o vídeo que você tem direito de analisar', "
              "filetypes=[('Vídeos','*.mp4 *.mkv *.mov *.webm *.m4v *.ts *.flv *.avi'),('Todos','*.*')]))")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip().replace("/", "\\")


def pedir_analise(d: dict) -> dict:
    if d.get("autorizado") is not True:
        raise ValueError("Confirme que você tem direito de usar e analisar este arquivo.")
    inicio, segundos = float(d.get("inicio") or 0), float(d.get("segundos") or PADRAO)
    if inicio < 0 or not 1 <= segundos <= LIMITE:
        raise ValueError(f"Analise de 1 a {int(LIMITE)} segundos, começando em 0 ou depois.")
    if d.get("id"):
        with trava:
            _achar(_ler(), d["id"])
    caminho = str(d.get("caminho") or "").strip().strip('"') or _escolher_arquivo()
    if not caminho:
        return {"cancelado": True}
    arq = Path(caminho)
    if not arq.is_file() or arq.suffix.lower() not in VIDEOS:
        raise ValueError("Escolha um arquivo de vídeo deste PC (MP4, MOV, MKV ou WEBM).")
    with trava:
        itens = _ler()
        if d.get("id"):
            ref = _achar(itens, d["id"])
        else:  # referência só com o arquivo, sem link
            ref = next((r for r in itens if r["plataforma"] == "arquivo" and r.get("arquivo") == str(arq)), None)
            if not ref:
                ref = {"id": uuid.uuid4().hex[:10], "url": "", "plataforma": "arquivo", "formato": "Arquivo", "arquivo": str(arq),
                       "salvo_em": _agora(), "origem": "", "estilo": "", "etiquetas": [], "observacoes": "",
                       "metadados": {"estado": "local", "titulo": arq.stem}, "analise": None}
                itens.insert(0, ref)
                gravar_json(ARQ, itens)
        ref_id, etiquetas = ref["id"], list(ref.get("etiquetas") or [])

    def trabalho(t):
        analise = analisar_arquivo(arq, inicio, segundos, etiquetas, t)
        analise["autorizacao"] = {"declaracao": AUTORIZACAO, "confirmada_em": _agora()}
        with trava:
            itens = _ler()
            alvo = next((r for r in itens if r["id"] == ref_id), None)
            if alvo:
                alvo["analise"] = analise
                gravar_json(ARQ, itens)
        melhor = analise["sugestoes"]["templates"][:1]
        return {"id": ref_id, "template": melhor[0]["id"] if melhor else None, "caracteristicas": len(analise["caracteristicas"])}
    return {**fila.adicionar("referencia", f"Analisando {arq.name}", trabalho, f"ref:{ref_id}").publico(), "ref": ref_id}


def _trechos(mascara, minimo: int = 1, folga: int = 0) -> list[tuple[int, int]]:
    """Trechos contínuos [início, fim) onde a máscara vale; junta buracos de até `folga` posições."""
    idx = np.flatnonzero(mascara)
    if not len(idx):
        return []
    saida, i0, ant = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - ant > folga + 1:
            saida.append((i0, ant + 1))
            i0 = i
        ant = i
    saida.append((i0, ant + 1))
    return [(int(a), int(b)) for a, b in saida if b - a >= minimo]


def _reduzido(w: int, h: int) -> tuple[int, int]:
    if h >= w:
        return max(32, round(LADO * w / h / 2) * 2), LADO
    return LADO, max(32, round(LADO * h / w / 2) * 2)


def _quadros(arq: Path, ini: float, seg: float, meta: dict, avancar) -> dict:
    """Uma leitura só: quadros pequenos a 5 por segundo (SATAVG do signalstats) e detecção de cena no ritmo original."""
    import cv2
    l, a = _reduzido(meta["w"], meta["h"])
    grafo = (f"[0:v]scale={l}:{a}:flags=area,split=2[a][b];"
             f"[a]fps={FPS},format=yuv420p,signalstats,metadata=print:key=lavfi.signalstats.SATAVG,format=rgb24[o];"
             f"[b]select='gt(scene,{LIMIAR_CENA})',metadata=print:key=lavfi.scene_score[c]")
    proc = subprocess.Popen([ffmpeg(), "-hide_banner", "-nostats", "-loglevel", "info", "-ss", f"{ini:.3f}", "-t", f"{seg:.3f}",
                             "-i", str(arq), "-an", "-sn", "-dn", "-filter_complex", grafo,
                             "-map", "[o]", "-f", "rawvideo", "pipe:1", "-map", "[c]", "-f", "null", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=SEM_JANELA)
    cenas, sats = [], []

    def ler_log():
        t = 0.0
        for bruto in proc.stderr:
            linha = bruto.decode("utf-8", "replace")
            m = re.search(r"pts_time:\s*(-?[\d.]+)", linha)
            if m:
                t = float(m[1])
                continue
            m = re.search(r"lavfi\.(scene_score|signalstats\.SATAVG)=([\d.]+)", linha)
            if m:
                (cenas if m[1] == "scene_score" else sats).append((t, float(m[2])))
    leitor = threading.Thread(target=ler_log, daemon=True)
    leitor.start()

    n_est = max(1, int(seg * FPS))
    soma, soma2 = np.zeros((a, l)), np.zeros((a, l))
    blocos = [{"s": np.zeros((a, l)), "s2": np.zeros((a, l)), "n": 0, "i0": None, "i1": None} for _ in range(BLOCOS)]
    z0, z1, c0 = int(a * 0.35), int(a * 0.9), int(l * 0.06)
    zona = (z0, z1, c0, l - c0)
    nucleo = np.ones((3, 3), np.uint8)
    lum, dif, atividade, textos, cores = [], [], [], [], []
    nitidez = np.zeros(a)
    anterior = None
    tam, i = l * a * 3, 0
    try:
        while True:
            bruto = proc.stdout.read(tam)
            if len(bruto) < tam:
                break
            rgb = np.frombuffer(bruto, np.uint8).reshape(a, l, 3)
            cinza = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            g = cinza.astype(np.float32)
            soma += g
            soma2 += g * g
            b = blocos[min(BLOCOS - 1, i * BLOCOS // n_est)]
            b["s"] += g
            b["s2"] += g * g
            b["n"] += 1
            b["i0"] = i if b["i0"] is None else b["i0"]
            b["i1"] = i
            lum.append(float(g.mean()))
            if anterior is None:
                dif.append(0.0)
                atividade.append(np.zeros(a, np.float32))
            else:
                d = np.abs(g - anterior)
                dif.append(float(d.mean()))
                atividade.append(d.mean(axis=1))
            nitidez += np.abs(cv2.Laplacian(cinza, cv2.CV_32F)).mean(axis=1)
            # texto claro com contorno escuro na região central/inferior (onde ficam as legendas)
            z = rgb[z0:z1, c0:l - c0]
            claro = z.max(axis=2) > 205
            perto = cv2.dilate((cinza[z0:z1, c0:l - c0] < 60).astype(np.uint8), nucleo) > 0
            texto = claro & perto
            if texto.any():
                px = z[texto].astype(np.int16)
                cores.append(float(((px.max(axis=1) - px.min(axis=1)) > 80).mean()))
            else:
                cores.append(0.0)
            textos.append(np.packbits(texto))
            anterior = g
            i += 1
            if i % 25 == 0:
                avancar(0.05 + 0.65 * min(1.0, i / n_est), f"Lendo quadros ({min(i, n_est)}/{n_est})")
    finally:
        proc.stdout.close()
        proc.wait()
        leitor.join(5)
    n = len(lum)
    if n < 3:
        raise ValueError("Não consegui ler quadros suficientes desse vídeo.")
    media = soma / n
    desvio = np.sqrt(np.maximum(soma2 / n - media * media, 0))
    tempos = ini + (np.array([t for t, _ in sats]) if len(sats) == n else np.arange(n) / FPS)
    lista_blocos = []
    for b in blocos:
        if b["n"] >= 3:
            m = b["s"] / b["n"]
            lista_blocos.append({"media": m, "desvio": np.sqrt(np.maximum(b["s2"] / b["n"] - m * m, 0)),
                                 "t0": float(tempos[b["i0"]]), "t1": float(tempos[b["i1"]]) + 1 / FPS})
    return {"n": n, "l": l, "a": a, "tempos": tempos, "lum": np.array(lum), "dif": np.array(dif), "act": np.array(atividade),
            "media": media, "desvio": desvio, "blocos": lista_blocos, "nitidez": nitidez / n, "zona": zona,
            "textos": textos, "cores": np.array(cores), "sats": np.array([s for _, s in sats]) if len(sats) == n else None,
            "cenas": sorted(ini + t for t, _ in cenas)}


def _rostos(arq: Path, ini: float, seg: float, meta: dict, amostras: int = 10) -> dict:
    """Rosto que fica no mesmo lugar (webcam). Só posição e tamanho: nenhuma leitura de expressão."""
    import cv2
    largura = 480 if meta["h"] >= meta["w"] else 640
    altura = 2 * round(largura * meta["h"] / meta["w"] / 2)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    achados, lidas = [], 0
    for k in range(amostras):
        t = ini + seg * (k + 0.5) / amostras
        try:
            bruto = subprocess.run([ffmpeg(), "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(arq), "-frames:v", "1",
                                    "-vf", f"scale={largura}:{altura}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                   capture_output=True, creationflags=SEM_JANELA, timeout=60).stdout
        except subprocess.TimeoutExpired:
            continue
        if len(bruto) != largura * altura:
            continue
        lidas += 1
        quadro = np.frombuffer(bruto, np.uint8).reshape(altura, largura)
        for x, y, w, h in detector.detectMultiScale(quadro, 1.1, 6, minSize=(28, 28)):
            achados.append((k, t, (x + w / 2) / largura, (y + h / 2) / altura, w / largura, h / altura))
    melhor, apoio = None, 0
    for f in achados:
        perto = {g[0] for g in achados if abs(g[2] - f[2]) < 0.08 and abs(g[3] - f[3]) < 0.08}
        if len(perto) > apoio:
            melhor, apoio = f, len(perto)
    if not melhor:
        return {"amostras": lidas, "apoio": 0}
    grupo = [g for g in achados if abs(g[2] - melhor[2]) < 0.08 and abs(g[3] - melhor[3]) < 0.08]
    tempos = sorted({round(g[1], 2) for g in grupo})
    return {"amostras": lidas, "apoio": apoio, "tempos": tempos, **{k: float(np.median([g[i] for g in grupo])) for k, i in
            (("cx", 2), ("cy", 3), ("w", 4), ("h", 5))}, "h_min": float(min(g[5] for g in grupo)), "h_max": float(max(g[5] for g in grupo))}


def _audio(arq: Path, ini: float, seg: float) -> np.ndarray:
    """Energia RMS em janelas de 50 ms (dBFS), lida aos poucos."""
    janela = 800  # 50 ms a 16 kHz
    proc = subprocess.Popen([ffmpeg(), "-loglevel", "error", "-ss", f"{ini:.3f}", "-t", f"{seg:.3f}", "-i", str(arq), "-vn",
                             "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA)
    niveis, resto = [], b""
    try:
        while bloco := proc.stdout.read(janela * 2 * 200):
            dados = resto + bloco
            usar = len(dados) // (janela * 2) * janela * 2
            x = np.frombuffer(dados[:usar], np.int16).astype(np.float32).reshape(-1, janela) / 32768
            niveis.extend((20 * np.log10(np.sqrt((x * x).mean(axis=1)) + 1e-6)).tolist())
            resto = dados[usar:]
    finally:
        proc.stdout.close()
        proc.wait()
    return np.array(niveis)


def _caract(id_: str, nome: str, valor: str, confianca: float, evidencia: list, metodo: str, **dados) -> dict:
    c = max(0.0, min(1.0, float(confianca)))
    return {"id": id_, "nome": nome, "valor": valor, "confianca": round(c, 2),
            "nivel": "alta" if c >= 0.75 else "média" if c >= 0.5 else "baixa", "evidencia": evidencia, "metodo": metodo, "dados": dados}


def _ev_t(tempos, limite: int = 30) -> list[dict]:
    return [{"t": round(float(t), 2)} for t in list(tempos)[:limite]]


def _ev_r(faixas, limite: int = 20) -> list[dict]:
    return [{"t0": round(float(x), 2), "t1": round(float(y), 2)} for x, y in list(faixas)[:limite]]


def _proporcao(w: int, h: int) -> str:
    tabela = {"9:16": 9 / 16, "3:4": 0.75, "4:5": 0.8, "1:1": 1.0, "4:3": 4 / 3, "16:9": 16 / 9, "1,91:1": 1.91, "21:9": 21 / 9}
    nome = min(tabela, key=lambda k: abs(tabela[k] - w / h))
    return nome if abs(tabela[nome] - w / h) < 0.02 else f"≈{nome}"


def _faixas(q: dict, linhas_fixas, cols, px) -> list[dict]:
    """Faixas horizontais paradas, separadas onde o brilho muda de repente (faixa branca encostada em jogo escuro, por exemplo)."""
    import cv2
    a = q["a"]
    m32 = q["media"].astype(np.float32)
    sobel = cv2.magnitude(cv2.Sobel(m32, cv2.CV_32F, 1, 0), cv2.Sobel(m32, cv2.CV_32F, 0, 1))
    perfil = np.median(q["media"][:, cols], axis=1)
    minimo, faixas = max(3, int(a * 0.03)), []
    for r0, r1 in _trechos(linhas_fixas, minimo=minimo, folga=1):
        quebras = [r0, *[y for y in range(r0 + 1, r1) if abs(perfil[y] - perfil[y - 1]) > 60], r1]
        pecas, atual = [], None
        for i0, i1 in zip(quebras, quebras[1:]):  # linhas de texto picotam a faixa: pedaços curtos seguidos ficam juntos
            curta = i1 - i0 < minimo
            if curta and atual and atual[2]:
                atual[1] = i1
            else:
                atual = [i0, i1, curta]
                pecas.append(atual)
        for i0, i1, _ in pecas:
            if i1 - i0 < minimo:
                continue
            m = q["media"][i0:i1, cols]
            lum_f, detalhe = float(m.mean()), float(sobel[i0:i1, cols].mean())
            plano = float(np.bincount((m // 16).astype(int).ravel(), minlength=17).max() / m.size)
            ok = sum(1 for b in q["blocos"] if ((b["desvio"][i0:i1, cols] < 5).mean(axis=1) > 0.85).mean() >= 0.7)
            faixas.append({"y0": px(i0), "y1": px(i1), "i0": i0, "i1": i1, "lum": round(lum_f), "plano": round(plano, 2),
                           "persistencia": round(ok / max(1, len(q["blocos"])), 2),
                           "tipo": "lisa" if detalhe < 12 else "com texto ou arte" if plano >= 0.45 else "com detalhes",
                           "cor": "branca" if lum_f > 200 else "preta" if lum_f < 35 else "clara" if lum_f > 150 else "escura" if lum_f < 80 else "média",
                           "posicao": "topo" if i0 <= a * 0.02 else "base" if i1 >= a * 0.98 else "meio"})
    return faixas


def _textos_fixos(q: dict, faixas: list[dict], cols, px) -> tuple[list[dict], list[dict]]:
    """Texto parado de alto contraste, medido em cada quarto do vídeo. Título = largo e baixo, sobre faixa lisa
    ou com traço claro encostado em escuro sobre imagem que se mexe. O resto vira 'área parada com detalhes'."""
    import cv2
    a, l = q["a"], q["l"]
    nucleo = np.ones((3, 3), np.uint8)
    achados = []
    for nb_, b in enumerate(q["blocos"]):
        bm = b["media"].astype(np.float32)
        sob = cv2.magnitude(cv2.Sobel(bm, cv2.CV_32F, 1, 0), cv2.Sobel(bm, cv2.CV_32F, 0, 1))
        parado = b["desvio"] < 8
        fixo = parado & (sob > 160)
        par = parado & (bm > 190) & (cv2.dilate((bm < 70).astype(np.uint8), nucleo) > 0)
        dens = fixo[:, cols].mean(axis=1)
        for i0, i1 in _trechos(dens > 0.04, minimo=max(3, int(a * 0.012)), folga=max(2, int(a * 0.015))):
            usadas = np.flatnonzero(fixo[i0:i1].any(axis=0))
            achados.append({"b": nb_, "i0": i0, "i1": i1, "ext": float(fixo[i0:i1].any(axis=0).mean()), "esq": usadas[0] / l,
                            "dir": (usadas[-1] + 1) / l, "parado": [float(parado[i0:i1, cols].mean())], "par": [float(par[i0:i1, cols].mean())]})
    grupos = []
    for f in sorted(achados, key=lambda x: x["i0"]):
        g = next((g for g in grupos if f["i0"] < g["i1"] and f["i1"] > g["i0"]), None)
        if g:
            g.update(i0=min(g["i0"], f["i0"]), i1=max(g["i1"], f["i1"]), ext=max(g["ext"], f["ext"]), esq=min(g["esq"], f["esq"]), dir=max(g["dir"], f["dir"]))
            g["blocos"].add(f["b"])
            g["parado"] += f["parado"]
            g["par"] += f["par"]
        else:
            grupos.append({**f, "blocos": {f["b"]}})
    titulos, outros = [], []
    for g in grupos:
        alto, parado, par = (g["i1"] - g["i0"]) / a, float(np.mean(g["parado"])), float(np.mean(g["par"]))
        largo = g["ext"] >= 0.3 or g["dir"] - g["esq"] >= 0.45
        bl = [q["blocos"][i]["media"][g["i0"]:g["i1"]] for i in sorted(g["blocos"])]
        centro_y = (g["i0"] + g["i1"]) / 2 / a
        sobre = next((f for f in faixas if f["i0"] - 3 <= g["i0"] and g["i1"] <= f["i1"] + 3), None)
        item = {"y0": px(g["i0"]), "y1": px(g["i1"]), "largura": round(g["dir"] - g["esq"], 2),
                "persistencia": round(len(g["blocos"]) / max(1, len(q["blocos"])), 2),
                "muda": len(bl) > 1 and max(float(np.abs(x - y).mean()) for x in bl for y in bl) > 18,
                "posicao": "topo" if centro_y < 0.33 else "base" if centro_y > 0.66 else "meio",
                "fundo": f"faixa {sobre['cor']}" if sobre else "imagem em movimento", "fundo_claro": bool(sobre and sobre["lum"] > 150),
                "parado": round(parado, 2), "contorno": round(par, 3),
                "periodos": [(q["blocos"][i]["t0"], q["blocos"][i]["t1"]) for i in sorted(g["blocos"])]}
        texto = par >= 0.02 or bool(sobre and sobre["plano"] >= 0.45 and sobre["tipo"] != "lisa")
        (titulos if largo and alto <= 0.22 and texto else outros).append(item)
    return titulos, outros


def _caracteristicas(meta: dict, ini: float, seg: float, q: dict, rostos: dict, audio: np.ndarray | None) -> list[dict]:
    import cv2
    n, l, a, T = q["n"], q["l"], q["a"], q["tempos"]
    px = lambda i: int(round(i / a * meta["h"]))  # linha do quadro reduzido -> pixel do original
    fim = ini + seg
    saida = []

    saida.append(_caract("proporcao", "Proporção", f"{_proporcao(meta['w'], meta['h'])} · {meta['w']}x{meta['h']} · "
                         f"{'vertical' if meta['h'] > meta['w'] else 'horizontal' if meta['w'] > meta['h'] else 'quadrado'} · {meta['fps']:g} fps",
                         1.0, [], "Lido do arquivo com ffprobe.", largura=meta["w"], altura=meta["h"], fps=meta["fps"]))

    # faixas horizontais paradas (cabeçalho, faixa de título, barras)
    cols = slice(int(l * 0.05), l - int(l * 0.05))
    linhas_fixas = (q["desvio"][:, cols] < 4.0).mean(axis=1) > 0.92
    quase_parado = linhas_fixas.mean() > 0.85
    faixas = _faixas(q, linhas_fixas, cols, px)
    if faixas:
        valor = "; ".join(f"{f['posicao']} y {f['y0']}–{f['y1']} px ({f['cor']}, {f['tipo']})" for f in faixas)
        conf = float(np.mean([0.5 + 0.45 * f["persistencia"] for f in faixas])) - (0.3 if quase_parado else 0)
    else:
        valor, conf = "Nenhuma faixa horizontal parada", 0.7
    saida.append(_caract("faixas", "Faixas paradas", valor + (" · vídeo quase sem movimento: medida pouco confiável" if quase_parado else ""),
                         conf, _ev_r([(ini, fim)]) if faixas else [],
                         "Linhas com variação temporal muito baixa (desvio < 4 níveis de cinza em 92% da largura), conferidas em 4 partes do vídeo.",
                         faixas=[{k: v for k, v in f.items() if k not in ("i0", "i1")} for f in faixas]))

    # duas regiões empilhadas: movimento de cima e de baixo independentes
    act = q["act"][1:]
    altura_b = max(2, a // 64)
    nb = a // altura_b
    actb = act[:, :nb * altura_b].reshape(len(act), nb, altura_b).mean(axis=2)
    fixa_b = linhas_fixas[:nb * altura_b].reshape(nb, altura_b).mean(axis=1) > 0.5
    ativa = (actb.mean(axis=0) > 0.4) & ~fixa_b
    melhor = None
    for k in range(int(nb * 0.2), int(nb * 0.8) + 1):
        cima, baixo = ativa.copy(), ativa.copy()
        cima[k:], baixo[:k] = False, False
        if cima.sum() < nb * 0.12 or baixo.sum() < nb * 0.12:
            continue
        A, B = actb[:, cima].mean(axis=1), actb[:, baixo].mean(axis=1)
        if A.std() < 1e-6 or B.std() < 1e-6:
            continue
        c = float(np.corrcoef(A, B)[0, 1])
        if melhor is None or c < melhor[0]:
            melhor = (c, k, A, B, np.flatnonzero(cima), np.flatnonzero(baixo))
    emp = {"sim": False}
    if melhor and len(act) >= 8:
        c, k, A, B, ic, ib = melhor
        mA, mB = float(np.median(A)) + 1e-3, float(np.median(B)) + 1e-3
        def pico(X, m):  # mudança brusca de um quadro para o outro, isolada (cara de corte), não movimento contínuo
            viz = np.maximum(np.concatenate([[0], X[:-1]]), np.concatenate([X[1:], [0]]))
            return (X > max(8.0, 4 * m)) & (X > 2 * viz)
        pa, pb = pico(A, mA), pico(B, mB)
        so_a, so_b = pa & (B < 1.8 * mB + 1), pb & (A < 1.8 * mA + 1)
        tA, tB = T[1:][so_a], T[1:][so_b]
        corte_y = k * altura_b
        sep = next((f for f in faixas if f["posicao"] == "meio" and abs((f["i0"] + f["i1"]) / 2 - corte_y) < a * 0.15), None)
        indep = len(tA) + len(tB)
        if c < 0.45 and (indep >= 2 or sep or c < 0.2):
            conf = min(0.92, 0.45 + (0.45 - c) * 0.8 + 0.06 * min(indep, 4) + (0.15 if sep else 0))
            cima_px = (px(ic[0] * altura_b), px(sep["i0"] if sep else corte_y))
            baixo_px = (px(sep["i1"] if sep else corte_y), px((ib[-1] + 1) * altura_b))
            emp = {"sim": True, "divisao": px((sep["i0"] + sep["i1"]) // 2 if sep else corte_y), "cima": cima_px, "baixo": baixo_px, "correlacao": round(c, 2),
                   "trocas_cima": len(tA), "trocas_baixo": len(tB), "separador": bool(sep),
                   "mais_ativa": "superior" if A.mean() > B.mean() else "inferior"}
            valor = (f"Sim: região superior y {cima_px[0]}–{cima_px[1]} px e inferior y {baixo_px[0]}–{baixo_px[1]} px"
                     f"{' com faixa parada entre elas' if sep else ''} · correlação de movimento {c:.2f}"
                     f" · trocas bruscas só em cima: {len(tA)}, só embaixo: {len(tB)}")
            saida.append(_caract("empilhado", "Vídeo empilhado em 2 regiões", valor, conf, _ev_t(sorted([*tA, *tB]), 20),
                                 "Variação temporal por faixas horizontais: busca a divisão em que o movimento de cima e o de baixo menos se parecem; "
                                 "as evidências são instantes em que só uma das regiões mudou de repente.", **emp))
    if not emp["sim"]:
        c_txt = f" (menor correlação entre cima e baixo: {melhor[0]:.2f})" if melhor else ""
        saida.append(_caract("empilhado", "Vídeo empilhado em 2 regiões", "Não: o movimento parece de uma imagem só" + c_txt,
                             0.6 if len(act) >= 8 else 0.3, [], "Variação temporal por faixas horizontais.", sim=False))

    # barras pretas ou fundo desfocado em cima e embaixo
    nit = q["nitidez"]
    centro = float(np.median(nit[int(a * 0.3):int(a * 0.7)])) + 1e-3
    mov = q["act"].mean(axis=0)
    def borda(linhas):
        tamanho = 0
        for y in linhas:
            if nit[y] < 0.3 * centro:
                tamanho += 1
            else:
                break
        return tamanho
    topo, base = borda(range(a)), borda(range(a - 1, -1, -1))
    lisas = [f for f in faixas if f["tipo"] == "lisa" and f["posicao"] in ("topo", "base")]
    if topo >= a * 0.08 and base >= a * 0.08:
        parado = mov[:topo].mean() < 0.3 and mov[a - base:].mean() < 0.3
        tipo = "barras lisas paradas" if parado else "fundo desfocado em movimento"
        saida.append(_caract("barras", "Barras em cima e embaixo", f"{tipo}: topo {px(topo)} px, base {px(base)} px · imagem nítida no meio",
                             0.75 if parado else 0.6, _ev_r([(ini, fim)]),
                             "Nitidez (Laplaciano) por linha: bordas com menos de 30% da nitidez do centro.",
                             tipo="lisa" if parado else "desfocada", topo=px(topo), base=px(base)))
    elif lisas:
        saida.append(_caract("barras", "Barras em cima e embaixo", "; ".join(f"barra {f['cor']} no {f['posicao']} ({f['y1'] - f['y0']} px)" for f in lisas),
                             0.6, _ev_r([(ini, fim)]), "Faixa parada e lisa encostada na borda.", tipo="lisa"))
    else:
        saida.append(_caract("barras", "Barras em cima e embaixo", "Não: a imagem ocupa a altura toda", 0.6, [],
                             "Nitidez (Laplaciano) por linha.", tipo=None))

    # cortes de cena
    cortes = []
    for t in q["cenas"]:
        if t > ini + 0.05 and (not cortes or t - cortes[-1] > 0.25):
            cortes.append(t)
    limites = [ini, *cortes, fim]
    planos = [y - x for x, y in zip(limites, limites[1:]) if y - x > 0]
    por_min = len(cortes) / (seg / 60)
    if cortes:
        valor = (f"{len(cortes)} cortes · plano médio {np.mean(planos):.1f} s (mín {min(planos):.1f} s, máx {max(planos):.1f} s)"
                 f" · {por_min:.1f} por minuto")
    else:
        valor = f"Nenhum corte acima do limiar: plano contínuo de {seg:.1f} s"
    saida.append(_caract("cortes", "Cortes e trocas de enquadramento", valor, 0.65 if emp["sim"] else 0.85, _ev_t(cortes, 40),
                         f"Detecção de cena do ffmpeg (select='gt(scene,{LIMIAR_CENA})') no ritmo original do vídeo."
                         + (" Em vídeo empilhado, uma troca que muda só uma região pode ficar abaixo do limiar." if emp["sim"] else ""),
                         quantidade=len(cortes), por_minuto=round(por_min, 1), plano_medio=round(float(np.mean(planos)), 2) if planos else None,
                         plano_min=round(min(planos), 2) if planos else None, plano_max=round(max(planos), 2) if planos else None))

    # texto parado de alto contraste (título), parte por parte
    titulos, pequenos = _textos_fixos(q, faixas, cols, px)
    if titulos:
        t0 = max(titulos, key=lambda x: (x["persistencia"], x["largura"]))
        conf = min(0.85, 0.4 + 0.12 * len(t0["periodos"]) + (0.1 if t0["largura"] > 0.6 else 0)) - (0.25 if quase_parado else 0)
        valor = (f"Texto parado provável no {t0['posicao']} (y {t0['y0']}–{t0['y1']} px, {round(t0['largura'] * 100)}% da largura) sobre {t0['fundo']}"
                 + (" · muda ao longo do vídeo" if t0["muda"] else " · o mesmo do começo ao fim" if t0["persistencia"] == 1 else ""))
        saida.append(_caract("titulo", "Título fixo", valor, conf, _ev_r(t0["periodos"]),
                             "Bordas fortes (Sobel) que não mudam dentro de cada quarto do vídeo; pode ser título, faixa de texto ou arte fixa.",
                             **{k: v for k, v in t0.items() if k != "periodos"}, outros=len(titulos) - 1))
    else:
        saida.append(_caract("titulo", "Título fixo", "Nenhum texto parado largo encontrado", 0.55, [],
                             "Bordas fortes (Sobel) que não mudam dentro de cada quarto do vídeo.", posicao=None))
    if pequenos:
        saida.append(_caract("areas_paradas", "Outras áreas paradas com detalhes",
                             "; ".join(f"{p['posicao']} y {p['y0']}–{p['y1']} px ({round(p['largura'] * 100)}% da largura)" for p in pequenos[:4]),
                             0.45, _ev_r(pequenos[0]["periodos"]), "Bordas que não mudam, mas sem cara de título: logo, @ da página, HUD do jogo, chat ou cenário parado.",
                             quantidade=len(pequenos)))

    # legendas: texto claro com contorno escuro mudando na região central/inferior
    z0, z1, c0, c1 = q["zona"]
    forma = (z1 - z0, c1 - c0)
    total = forma[0] * forma[1]
    abrir = lambda p: np.unpackbits(p, count=total).reshape(forma).astype(bool)
    soma_txt = np.zeros(forma)
    for p in q["textos"]:
        soma_txt += abrir(p)
    parado = soma_txt / n > 0.6  # texto que fica (título) não conta como legenda
    faixa_h = max(4, int(a * 0.03))
    presente, trocas, ys, anterior = np.zeros(n, bool), [], [], None
    for i, p in enumerate(q["textos"]):
        m = abrir(p) & ~parado
        linhas = m.sum(axis=1)
        cumul = np.concatenate([[0], np.cumsum(linhas)])
        dens = (cumul[faixa_h:] - cumul[:-faixa_h]) / (faixa_h * forma[1])
        k = int(dens.argmax()) if len(dens) else 0
        if len(dens) and dens[k] > 0.012:
            colunas = np.flatnonzero(m[k:k + faixa_h].any(axis=0))
            cx = (colunas.mean() + c0) / l if len(colunas) else 0
            if 0.3 <= cx <= 0.7:
                presente[i] = True
                ys.append((z0 + k + faixa_h / 2) / a)
                if anterior is not None and presente[i - 1]:
                    uniao = (m | anterior).sum()
                    if uniao and (m & anterior).sum() / uniao < 0.35:
                        trocas.append(T[i])
        anterior = m
    pres = float(presente.mean())
    trocas_min = len(trocas) / (seg / 60)
    espalhado = float(np.std(ys)) if ys else 1.0
    periodos = [(T[x], T[min(y, n - 1)] + 1 / FPS) for x, y in _trechos(presente, minimo=2, folga=3)]
    colorido = float((q["cores"][presente] > 0.2).mean()) if presente.any() else 0.0
    if pres >= 0.2 and trocas_min >= 8 and espalhado < 0.12:
        y_med = float(np.median(ys))
        estilo = ["texto claro com contorno escuro", "central" if y_med < 0.62 else "inferior"]
        if colorido >= 0.2:
            estilo.append("parte do texto colorida (destaque provável)")
        ritmo = "palavra a palavra ou frases curtas" if trocas_min >= 40 else "frases"
        conf = min(0.75, 0.35 + 0.25 * min(1.0, pres / 0.6) + (0.15 if espalhado < 0.06 else 0))
        saida.append(_caract("legendas", "Legendas dinâmicas", f"Prováveis em {round(pres * 100)}% do tempo · {', '.join(estilo)} · y≈{round(y_med * 100)}% da altura"
                             f" · {trocas_min:.0f} trocas por minuto ({ritmo})", conf, _ev_r(periodos, 12),
                             "Pixels claros encostados em contorno escuro, centralizados, na região de 35% a 90% da altura, que mudam de forma entre quadros. "
                             "Texto sem contorno ou muito pequeno pode passar despercebido.",
                             sim=True, presenca=round(pres, 2), trocas_min=round(trocas_min, 1), y=round(y_med, 3), colorido=round(colorido, 2)))
    else:
        saida.append(_caract("legendas", "Legendas dinâmicas", f"Não detectadas (texto em {round(pres * 100)}% dos quadros, {trocas_min:.0f} trocas por minuto)",
                             0.5, _ev_r(periodos, 6), "Pixels claros encostados em contorno escuro, centralizados, na região central/inferior. "
                             "Texto sem contorno ou muito pequeno pode passar despercebido.", sim=False, presenca=round(pres, 2)))

    # rosto fixo (posição da webcam)
    if rostos.get("apoio", 0) >= max(2, round(rostos["amostras"] * 0.3)):
        conf = rostos["apoio"] / max(1, rostos["amostras"])
        regiao = "superior" if rostos["cy"] < 0.4 else "inferior" if rostos["cy"] > 0.6 else "central"
        canto = rostos["cx"] < 0.3 or rostos["cx"] > 0.7
        valor = (f"Rosto em posição fixa em {rostos['apoio']} de {rostos['amostras']} amostras · região {regiao}"
                 f"{' (canto)' if canto else ''} · altura do rosto ≈{round(rostos['h'] * 100)}% do quadro")
        saida.append(_caract("rosto", "Câmera do streamer", valor, conf, _ev_t(rostos["tempos"]),
                             "Detector de rosto do OpenCV (Haar) em quadros espalhados; só posição e tamanho, sem ler expressões.",
                             sim=True, regiao=regiao, canto=canto, **{k: round(rostos[k], 3) for k in ("cx", "cy", "w", "h", "h_min", "h_max")}))
    else:
        saida.append(_caract("rosto", "Câmera do streamer", f"Nenhum rosto em posição fixa ({rostos.get('apoio', 0)} de {rostos.get('amostras', 0)} amostras)",
                             0.5, [], "Detector de rosto do OpenCV (Haar). Rosto de perfil, pequeno ou escuro pode não ser encontrado.", sim=False))

    # cor: saturação média por quadro (SATAVG do signalstats)
    sat = q["sats"]
    if sat is not None and len(sat) == n:
        med = float(np.median(sat))
        if med < 3:
            saida.append(_caract("cor", "Cor e P&B", f"Vídeo inteiro quase sem cor (saturação mediana {med:.1f})", 0.85, _ev_r([(ini, fim)]),
                                 "SATAVG do filtro signalstats do ffmpeg, a 5 quadros por segundo.", pb=[], dessaturado=[], mediana=round(med, 1)))
        else:
            pb = [(T[x], T[min(y, n - 1)] + 1 / FPS) for x, y in _trechos(sat < max(2.5, 0.12 * med), minimo=2)]
            fraco = (sat < 0.45 * med) & ~(sat < max(2.5, 0.12 * med))
            des = [(T[x], T[min(y, n - 1)] + 1 / FPS) for x, y in _trechos(fraco, minimo=3, folga=1) if y < n and sat[y:y + 5].max(initial=0) > 0.7 * med]
            if pb or des:
                partes = ([f"{len(pb)} trecho(s) em P&B somando {sum(y - x for x, y in pb):.1f} s"] if pb else []) + \
                         ([f"{len(des)} queda(s) de saturação com volta à cor"] if des else [])
                saida.append(_caract("cor", "Cor e P&B", " · ".join(partes) + f" (saturação mediana {med:.1f})", 0.8, _ev_r(sorted(pb + des)),
                                     "SATAVG do signalstats: P&B abaixo de 12% da mediana do vídeo; dessaturação abaixo de 45% com retorno.",
                                     pb=_ev_r(pb), dessaturado=_ev_r(des), mediana=round(med, 1)))
            else:
                saida.append(_caract("cor", "Cor e P&B", f"Cor constante, sem trechos em P&B (saturação mediana {med:.1f})", 0.8, [],
                                     "SATAVG do filtro signalstats do ffmpeg.", pb=[], dessaturado=[], mediana=round(med, 1)))

    # flash: clarão curto que volta
    L = q["lum"]
    flashes = []
    for i in range(1, n):
        base = float(np.median(L[max(0, i - 5):i]))
        depois = L[i + 1:i + 4]
        if L[i] > 170 and L[i] - base > 50 and len(depois) and depois.min() < L[i] - 30 and (not flashes or T[i] - flashes[-1] > 0.5):
            flashes.append(T[i])
    saida.append(_caract("flash", "Flashes", f"{len(flashes)} clarão(ões) curtos" if flashes else "Nenhum clarão curto", 0.6 if flashes else 0.5,
                         _ev_t(flashes), "Brilho médio que sobe mais de 50 níveis e volta em até 0,6 s. Clarões mais curtos que 0,2 s podem escapar da amostragem.",
                         quantidade=len(flashes)))

    # quadro congelado
    D = q["dif"]
    congelados = []
    if n > 6 and float(np.median(D[1:])) > 1.5:
        congelados = [(T[max(0, x - 1)], T[min(y, n - 1)]) for x, y in _trechos(D < 0.35, minimo=3) if x > 0]
    saida.append(_caract("congelamento", "Quadro congelado", f"{len(congelados)} trecho(s) com a imagem parada" if congelados else "Nenhum",
                         0.55 if congelados else 0.5, _ev_r(congelados),
                         "Quadros seguidos praticamente iguais (diferença média < 0,35) por 0,6 s ou mais, num vídeo que normalmente se mexe.",
                         quantidade=len(congelados)))

    # áudio
    if audio is None or not len(audio):
        saida.append(_caract("audio", "Áudio", "Sem faixa de áudio", 1.0, [], "Lido do arquivo com ffprobe."))
        return saida
    passo = 0.05
    ta = ini + np.arange(len(audio)) * passo
    validos = audio[audio > -60]
    media_db = float(10 * np.log10(np.mean(10 ** (validos / 10)))) if len(validos) else -90.0
    saida.append(_caract("audio", "Nível do áudio", f"RMS médio {media_db:.0f} dBFS · pico {audio.max():.0f} dBFS (janelas de 50 ms)", 0.95, [],
                         "Energia RMS do áudio mono a 16 kHz.", media=round(media_db, 1), pico=round(float(audio.max()), 1)))
    silencios = [(ta[x], ta[min(y, len(ta) - 1)] + passo) for x, y in _trechos(audio < -45, minimo=12)]
    saida.append(_caract("silencios", "Silêncios", f"{len(silencios)} trecho(s) somando {sum(y - x for x, y in silencios):.1f} s" if silencios
                         else "Nenhum silêncio de 0,6 s ou mais", 0.85, _ev_r(silencios),
                         "Janelas abaixo de −45 dBFS por 0,6 s ou mais.", quantidade=len(silencios)))
    picos, i = [], 20
    while i < len(audio):
        antes = float(np.median(audio[i - 20:i - 2]))
        if audio[i] > -30 and antes > -48 and audio[i] - antes >= 12 and audio[i] - audio[i - 2] >= 8:
            picos.append(ta[i])
            i += 6
        else:
            i += 1
    nos_cortes = sum(1 for p in picos if any(abs(p - c) <= 0.2 for c in cortes))
    saida.append(_caract("transientes", "Picos súbitos de som", (f"{len(picos)} picos ({len(picos) / (seg / 60):.1f} por minuto) · {nos_cortes} junto de cortes de imagem"
                         if picos else "Nenhum pico súbito"), 0.6 if picos else 0.55, _ev_t(picos),
                         "Ataque rápido (8 dB em até 100 ms) e 12 dB acima da mediana do segundo anterior, sem contar fala que começa depois de silêncio. Pode ser efeito sonoro, batida, grito ou risada: o tipo do som não é identificado.",
                         quantidade=len(picos), por_minuto=round(len(picos) / (seg / 60), 1), nos_cortes=nos_cortes))
    return saida


def sugerir(caracteristicas: list[dict], etiquetas=()) -> dict:
    """Templates e efeitos do editor como inspiração, cada um com o motivo."""
    c = {x["id"]: x for x in caracteristicas}
    D = lambda k: c[k]["dados"] if k in c else {}
    tpl = {k: {"pontos": 0.0, "porque": []} for k in TEMPLATES}
    efx = {k: {"pontos": 0.0, "porque": []} for k in EFEITOS}

    def dar(alvo, chave, pontos, texto, base="medido"):
        alvo[chave]["pontos"] += pontos
        alvo[chave]["porque"].append({"texto": texto, "base": base})
    emp, tit, rosto, barras, cortes = D("empilhado"), D("titulo"), D("rosto"), D("barras"), D("cortes")
    cor, legendas = D("cor"), D("legendas")
    n_flash, n_cong, picos = D("flash").get("quantidade", 0), D("congelamento").get("quantidade", 0), D("transientes")
    por_min, plano = cortes.get("por_minuto", 0), cortes.get("plano_medio")
    if emp.get("sim"):
        ce = c["empilhado"]["confianca"]
        ondes = f"divisão em y≈{emp['divisao']} px"
        if emp.get("separador") or tit.get("posicao") == "meio":
            dar(tpl, "cam_titulo_jogo", 3 * ce, f"Duas regiões empilhadas com faixa parada entre elas ({ondes}), como câmera + faixa de título + jogo.")
        if rosto.get("regiao") == "superior":
            dar(tpl, "cam_titulo_jogo" if emp.get("separador") else "cam_jogo", 1.5, "Rosto fixo na região de cima.")
            if not emp.get("separador"):
                dar(tpl, "cam_jogo", 1.5 * ce, f"Duas regiões empilhadas sem faixa entre elas ({ondes}).")
        elif rosto.get("regiao") == "inferior":
            dar(tpl, "jogo_cam", 2.5 * ce, f"Duas regiões empilhadas ({ondes}) com o rosto fixo na de baixo.")
        else:
            dar(tpl, "cam_jogo", 1.2 * ce, f"Duas regiões empilhadas ({ondes}); não achei rosto para saber qual é a câmera.")
        mudam = "superior" if emp.get("trocas_cima", 0) > emp.get("trocas_baixo", 0) else "inferior"
        if emp.get("trocas_cima", 0) + emp.get("trocas_baixo", 0) >= 2:
            dar(tpl, "cam_titulo_jogo" if emp.get("separador") else "cam_jogo" if mudam == "inferior" else "jogo_cam", 0.5,
                f"As trocas bruscas acontecem mais na região {mudam}, típico do jogo.")
    else:
        if tit.get("posicao") == "topo":
            if tit.get("fundo_claro"):
                dar(tpl, "editorial_branco", 2.5 * c["titulo"]["confianca"], f"Texto parado no topo sobre {tit.get('fundo')} (y {tit['y0']}–{tit['y1']} px).")
            dar(tpl, "pagina_viral", 1.5 * c["titulo"]["confianca"], "Título fixo no topo com o vídeo abaixo.")
        if barras.get("tipo"):
            dar(tpl, "pagina_viral", 1.0, f"Vídeo encaixado com {'barras lisas' if barras['tipo'] == 'lisa' else 'fundo desfocado'} em cima e embaixo, espaço típico de título e marca.")
        if rosto.get("sim") and rosto.get("h", 0) >= 0.16:
            dar(tpl, "reacao_destaque", 2.5 * c["rosto"]["confianca"], f"Rosto grande e fixo (≈{round(rosto['h'] * 100)}% da altura do quadro).")
        elif rosto.get("sim") and rosto.get("h", 1) < 0.12:
            dar(tpl, "jogo_cam_sobre", 2.0 * c["rosto"]["confianca"], f"Rosto pequeno e fixo na região {rosto['regiao']}{' (canto)' if rosto.get('canto') else ''}, como webcam sobreposta.")
        if not rosto.get("sim") and not tit.get("posicao") and not barras.get("tipo"):
            dar(tpl, "jogo_cheio", 1.6, "Uma imagem só, sem rosto fixo, sem título e sem barras.")
    if tit.get("muda"):
        dar(tpl, "ranking", 1.5, "O texto fixo muda de uma parte do vídeo para outra, como itens de uma lista.")
    if cor.get("pb") or cor.get("dessaturado"):
        dar(efx, "pb", 2.5, f"Trechos sem cor medidos em {', '.join(_fmt_ev(x) for x in (cor.get('pb') or cor.get('dessaturado'))[:3])}.")
    if n_flash:
        dar(efx, "flash", 2.0 + 0.3 * min(n_flash, 5), f"{n_flash} clarão(ões) curto(s) medidos.")
    if n_cong:
        dar(efx, "freeze", 2.0, f"{n_cong} trecho(s) com a imagem congelada.")
        dar(tpl, "humor", 1.2, "Quadro congelado, recurso comum para marcar o tempo de uma piada.")
    choques = [x for x in ((f"{n_flash} flash(es)" if n_flash else ""), ("trechos em P&B" if cor.get("pb") else ""),
               (f"{picos.get('nos_cortes')} picos de som junto dos cortes" if picos.get("nos_cortes", 0) >= 2 else "")) if x]
    if por_min >= 10 and choques:
        dar(tpl, "choque", 1.5 + 0.5 * len(choques), f"Ritmo de {por_min} cortes por minuto com {', '.join(choques)}.")
        dar(efx, "tremor", 1.0, "Impactos medidos (cortes rápidos com picos de som); um tremor curto acompanha esse tipo de impacto.", "ideia")
    elif choques:
        dar(tpl, "choque", 0.8 * len(choques), f"Impactos medidos: {', '.join(choques)}.")
    if n_cong and picos.get("quantidade", 0):
        dar(tpl, "humor", 0.6, "Picos de som perto de pausas da imagem.")
    if barras.get("tipo") == "lisa":
        dar(tpl, "cinematico", 1.5, "Barras lisas em cima e embaixo, como formato de cinema.")
    if cortes.get("quantidade", 0) >= 2 and plano and plano >= 4 and por_min < 12:
        dar(tpl, "cinematico", 1.0, f"Planos longos (média de {plano:.1f} s).")
    if cor.get("dessaturado"):
        dar(tpl, "cinematico", 0.8, "Mudanças de saturação com volta à cor, como tratamento de cor.")
    if rosto.get("sim"):
        if picos.get("quantidade", 0) >= 2:
            dar(efx, "zoom_cam", 1.2, f"Rosto fixo na tela e {picos['quantidade']} picos de som: um zoom na webcam nesses instantes destaca a reação.", "ideia")
        if rosto.get("h_max", 0) >= 2 * max(rosto.get("h_min", 1), 1e-3) and rosto.get("h_max", 0) >= 0.16:
            dar(efx, "cam_cheia", 1.5, f"O rosto muda de tamanho entre as amostras (≈{round(rosto['h_min'] * 100)}% a {round(rosto['h_max'] * 100)}% da altura): a câmera parece ir para a tela cheia em alguns trechos.")
    if legendas.get("sim") and tit.get("posicao") == "topo" and not emp.get("sim"):
        dar(tpl, "pagina_viral", 0.5, "Título no topo e legendas dinâmicas no meio da tela.")
    mapa_etq = {"choque": (["choque"], ["flash", "tremor"]), "humor": (["humor"], ["freeze"]), "editorial": (["editorial_branco", "pagina_viral"], []),
                "ranking": (["ranking"], []), "cinematico": (["cinematico"], ["vinheta", "pb"]), "cinema": (["cinematico"], ["vinheta"]),
                "reacao": (["reacao_destaque"], ["zoom_cam"]), "gameplay": (["jogo_cheio"], []), "meme": (["pagina_viral", "humor"], ["freeze"])}
    for e in etiquetas or []:
        alvo_t, alvo_e = mapa_etq.get(_sem_acento(e), ([], []))
        for k in alvo_t:
            dar(tpl, k, 1.0, f"Você marcou a etiqueta “{e}”.", "etiqueta")
        for k in alvo_e:
            dar(efx, k, 0.8, f"Combina com a etiqueta “{e}”.", "etiqueta")

    def ordenar(tabela, nomes):
        itens = [{"id": k, "nome": nomes(k), "pontos": round(v["pontos"], 2), "confianca": round(min(0.9, v["pontos"] / 5), 2), "porque": v["porque"]}
                 for k, v in tabela.items() if v["pontos"] > 0]
        return sorted(itens, key=lambda x: -x["pontos"])
    templates = ordenar(tpl, lambda k: TEMPLATES[k][0])[:3]
    if not templates or templates[0]["pontos"] < 1.5:
        templates.append({"id": "livre", "nome": TEMPLATES["livre"][0], "pontos": 0, "confianca": 0.3,
                          "porque": [{"texto": "A estrutura do vídeo não bateu com nenhum template com segurança; monte as camadas à mão.", "base": "medido"}]})
    return {"templates": templates, "efeitos": ordenar(efx, EFEITOS.get)[:4],
            "aviso": "Inspiração, não cópia: o vídeo de referência não é reaproveitado e nenhum elemento dele (arte, logo, música) vai para o seu corte."}


def _fmt_ev(x: dict) -> str:
    f = lambda s: f"{int(s // 60)}:{s % 60:04.1f}"
    return f"{f(x['t0'])}–{f(x['t1'])}" if "t0" in x else f(x["t"])


def analisar_arquivo(arq: Path, inicio: float = 0.0, segundos: float = PADRAO, etiquetas=(), tarefa=None) -> dict:
    try:
        import cv2  # noqa: F401
    except ImportError as erro:
        raise ValueError("OpenCV não está instalado: a análise de vídeo fica indisponível.") from erro
    avancar = tarefa.avancar if tarefa else (lambda *_: None)
    try:
        meta = sondar(arq)
    except Exception as erro:
        raise ValueError("Não consegui ler esse arquivo de vídeo.") from erro
    if not meta["w"] or not meta["h"] or meta["dur"] <= 0:
        raise ValueError("O arquivo não tem imagem de vídeo.")
    ini = min(max(0.0, inicio), max(0.0, meta["dur"] - 1))
    seg = min(meta["dur"] - ini, segundos, LIMITE)
    if seg < 1:
        raise ValueError("O trecho analisado precisa ter pelo menos 1 segundo.")
    avancar(0.02, "Lendo quadros em resolução reduzida")
    q = _quadros(arq, ini, seg, meta, avancar)
    avancar(0.75, "Procurando a câmera do streamer")
    rostos = _rostos(arq, ini, seg, meta)
    avancar(0.85, "Medindo o áudio")
    audio = _audio(arq, ini, seg) if meta["audio"] else None
    avancar(0.95, "Montando as sugestões")
    carac = _caracteristicas(meta, ini, seg, q, rostos, audio)
    return {"data": _agora(), "arquivo": str(arq), "nome_arquivo": arq.name, "inicio": round(ini, 2), "fim": round(ini + seg, 2),
            "video": {"largura": meta["w"], "altura": meta["h"], "fps": meta["fps"], "duracao": round(meta["dur"], 2), "audio": bool(meta["audio"])},
            "amostragem": {"fps": FPS, "largura": q["l"], "altura": q["a"], "quadros": q["n"], "limiar_cena": LIMIAR_CENA},
            "caracteristicas": carac, "sugestoes": sugerir(carac, etiquetas), "aviso": AVISO}


# ---------------------------------------------------------------- boas práticas

def boas_praticas(_consulta=None) -> dict:
    dados = ler_json(BOAS, None)
    if not dados:
        raise ValueError("Biblioteca de boas práticas não encontrada.")
    return {**dados, "verificacao": ler_json(VERIFICACAO, None)}


def _checar(url: str) -> dict:
    """Só confere se o endereço responde. O conteúdo da biblioteca não muda."""
    erro = {}
    for metodo in ("HEAD", "GET"):
        pedido = urllib.request.Request(url, method=metodo, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})
        try:
            with urllib.request.urlopen(pedido, timeout=15) as r:
                if metodo == "GET":
                    r.read(4096)
                final = r.geturl()
                return {"status": "ok", "codigo": r.status, "metodo": metodo, **({"final": final} if final != url else {})}
        except urllib.error.HTTPError as e:
            erro = {"status": "erro", "codigo": e.code, "metodo": metodo, "erro": f"HTTP {e.code}"}
        except (urllib.error.URLError, OSError, ValueError) as e:
            erro = {"status": "erro", "metodo": metodo, "erro": str(getattr(e, "reason", e))[:160]}
    return erro


def verificar(_d=None) -> dict:
    dados = ler_json(BOAS, {}) or {}
    itens = dados.get("itens", [])
    urls = sorted({i["url"] for i in itens})
    with ThreadPoolExecutor(6) as ex:
        resultado = dict(zip(urls, ex.map(_checar, urls)))
    saida = {"data": _agora(), "versao": dados.get("versao"), "itens": {i["id"]: {"url": i["url"], **resultado[i["url"]]} for i in itens}}
    saida["ok"] = sum(1 for v in saida["itens"].values() if v["status"] == "ok")
    saida["total"] = len(itens)
    gravar_json(VERIFICACAO, saida)
    return saida


GET = {"/api/referencias": listar, "/api/boas-praticas": boas_praticas}
POST = {
    "/api/referencias/salvar": salvar,
    "/api/referencias/remover": remover,
    "/api/referencias/metadados": metadados,
    "/api/referencias/analisar": pedir_analise,
    "/api/boas-praticas/verificar": verificar,
}
