"""Gravações (VODs) e arquivos do PC: identifica, mostra e transforma um trecho escolhido à mão em corte editável.

Só o trecho escolhido (com folga) é processado. Links exigem a confirmação de que o uso é autorizado,
e nada aqui contorna login, DRM ou gravações restritas: se a plataforma recusar, o erro é mostrado.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from . import editor, fontes
from .canais import ErroApi, canais
from .config import DADOS, LIVES, ffmpeg, gravar_json, ler_json, pasta_da_live

ARQ_RECENTES = DADOS / "gravacoes.json"
ARQ_LOCAIS = DADOS / "locais.json"
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".ts", ".flv"}
TIPO_NAVEGADOR = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4", ".mkv": "video/webm", ".webm": "video/webm"}
CODECS_NAVEGADOR = {"h264", "vp8", "vp9", "av1"}
MARGEM = 12.0
MARGEM_SEM_PLAYER = 30.0  # Kick: sem player oficial, o ajuste fino fica na timeline do editor
PARADO = 90  # segundos sem progresso antes de desistir do download

RE_TWITCH_VOD = re.compile(r"twitch\.tv/(?:videos/|\w+/v(?:ideo)?/)(\d+)", re.I)
RE_TWITCH_CLIP = re.compile(r"(?:clips\.twitch\.tv/(?:embed\?clip=)?|twitch\.tv/\w+/clip/)([\w-]+)", re.I)
RE_KICK_VOD = re.compile(r"kick\.com/(?:([\w-]+)/videos/|video/)([0-9a-f]{8}-[0-9a-f-]{27})", re.I)


def _hora(s: float) -> str:
    s = int(s)
    return f"{s // 3600:02d}h{s // 60 % 60:02d}m{s % 60:02d}s"


def _duracao_twitch(texto: str) -> float:
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", texto or "")
    return float(int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + int(m[3] or 0)) if m else 0.0


def identificar(url: str) -> dict:
    url = url.strip()
    if m := RE_TWITCH_VOD.search(url):
        return {"plataforma": "Twitch", "tipo": "vod", "id": m[1], "link": f"https://www.twitch.tv/videos/{m[1]}"}
    if m := RE_TWITCH_CLIP.search(url):
        return {"plataforma": "Twitch", "tipo": "clip", "id": m[1], "link": url}
    if m := RE_KICK_VOD.search(url):
        return {"plataforma": "Kick", "tipo": "vod", "id": m[2].lower(), "canal": (m[1] or "").lower(), "link": url}
    if fontes.eh_link(url):
        return {"plataforma": "Outros", "tipo": "vod", "id": hashlib.sha1(url.encode()).hexdigest()[:12], "link": url}
    raise ValueError("Cole o link de uma gravação, por exemplo https://www.twitch.tv/videos/123456789 ou https://kick.com/canal/videos/...")


def _guardar_recente(item: dict) -> None:
    lista = [r for r in ler_json(ARQ_RECENTES, []) or [] if not (r.get("tipo") == item["tipo"] and r.get("id") == item["id"])]
    resumo = {k: item.get(k) for k in ("tipo", "plataforma", "id", "link", "caminho", "titulo", "canal", "duracao", "thumb")}
    gravar_json(ARQ_RECENTES, [{**resumo, "aberto": time.time()}] + lista[:19])


def recentes() -> list[dict]:
    return ler_json(ARQ_RECENTES, []) or []


def abrir_link(url: str) -> dict:
    v = identificar(url)
    if v["tipo"] == "clip":
        raise ValueError("Esse link é de um clip. Os clips ficam na aba Clips criados. Aqui use o link da gravação (twitch.tv/videos/...).")
    dados, origem_dados = {}, ""
    if v["plataforma"] == "Twitch":
        try:
            d = canais.video_twitch(v["id"])
        except (ErroApi, ValueError):
            d = None
        if d:
            origem_dados = "API oficial da Twitch"
            dados = {"titulo": d.get("title", ""), "canal": d.get("user_login", ""), "nome": d.get("user_name", ""),
                     "duracao": _duracao_twitch(d.get("duration", "")), "criado": d.get("created_at", ""),
                     "thumb": (d.get("thumbnail_url") or "").replace("%{width}", "640").replace("%{height}", "360"),
                     "silenciado": bool(d.get("muted_segments"))}
    if not dados:
        try:
            j = fontes.info(v["link"])
        except SystemExit as e:
            raise ValueError(f"{e} Se a gravação for restrita, assista na plataforma e importe um arquivo autorizado.") from None
        if j.get("is_live"):
            raise ValueError("Essa transmissão ainda está ao vivo. Use a aba Ao vivo para criar clips, ou volte quando a gravação estiver pronta.")
        origem_dados = "Página pública da gravação"
        dados = {"titulo": j.get("title", ""), "canal": (j.get("channel") or j.get("uploader_id") or j.get("uploader") or v.get("canal") or ""),
                 "nome": j.get("uploader") or "", "duracao": float(j.get("duration") or 0), "criado": j.get("upload_date", ""),
                 "thumb": j.get("thumbnail", "")}
    player = {"tipo": "twitch", "video": v["id"]} if v["plataforma"] == "Twitch" else {"tipo": "externo"}
    item = {**v, **dados, "origem_dados": origem_dados, "player": player,
            "margem": MARGEM if player["tipo"] == "twitch" else MARGEM_SEM_PLAYER}
    _guardar_recente(item)
    return item


# ---------------------------------------------------------------- arquivos do PC

def _id_local(caminho: Path) -> str:
    return hashlib.sha1(str(caminho).lower().encode()).hexdigest()[:12]


def caminho_local(ident: str) -> Path | None:
    caminho = (ler_json(ARQ_LOCAIS, {}) or {}).get(str(ident))
    return Path(caminho) if caminho and Path(caminho).is_file() else None


def tipo_navegador(caminho: Path) -> str:
    return TIPO_NAVEGADOR.get(caminho.suffix.lower(), "application/octet-stream")


def abrir_arquivo(caminho: str) -> dict:
    p = Path(str(caminho).strip().strip('"'))
    if not p.is_file():
        raise ValueError("Arquivo não encontrado.")
    if p.suffix.lower() not in EXT_VIDEO:
        raise ValueError("Escolha um vídeo MP4, MOV, MKV ou WEBM.")
    p = p.resolve()
    try:
        s = editor.sondar(p)
    except (subprocess.CalledProcessError, ValueError, KeyError):
        raise ValueError("Não consegui ler esse vídeo. O arquivo pode estar incompleto.") from None
    if not s["w"]:
        raise ValueError("Esse arquivo não tem imagem de vídeo.")
    ident = _id_local(p)
    locais = ler_json(ARQ_LOCAIS, {}) or {}
    locais[ident] = str(p)
    gravar_json(ARQ_LOCAIS, locais)
    toca = p.suffix.lower() in TIPO_NAVEGADOR and s["video"] in CODECS_NAVEGADOR
    aviso = "" if toca else (f"O navegador não reproduz este formato ({s['video']}). Digite os tempos de início e fim; "
                             "o corte e o editor funcionam normalmente.")
    item = {"tipo": "arquivo", "plataforma": "Arquivos", "id": ident, "caminho": str(p), "titulo": p.stem, "canal": "",
            "duracao": s["dur"], "w": s["w"], "h": s["h"], "fps": s["fps"], "url": f"/local/{ident}" if toca else "",
            "aviso": aviso, "origem_dados": "Arquivo deste PC", "player": {"tipo": "local" if toca else "nenhum"}, "margem": MARGEM}
    _guardar_recente(item)
    return item


# ---------------------------------------------------------------- recorte do trecho

def extrair_trecho(entradas: list[str], inicio: float, duracao: float, destino: Path, tarefa=None, faixa=(0.1, 0.7)) -> None:
    """Recodifica só o trecho pedido. Recodificar garante o início exato, o que a cópia direta não garante."""
    leitura = []
    for e in entradas:
        leitura += ["-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}", "-i", e]
    base = [ffmpeg(), "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *leitura, "-map", "0:v:0",
            "-map", f"{len(entradas) - 1}:a:0?", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart"]
    codecs = {"h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "18", "-b:v", "0", "-maxrate", "30M", "-bufsize", "40M"],
              "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17"]}
    temp = destino.with_name(f"_{destino.name}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    erro = ""
    for nome, cod in codecs.items():
        proc = subprocess.Popen(base + cod + [str(temp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", creationflags=editor.SEM_JANELA)
        visto = [time.time()]
        parado = threading.Event()

        def vigiar(p=proc, v=visto, ev=parado):
            while p.poll() is None:
                if time.time() - v[0] > PARADO:
                    ev.set()
                    p.kill()
                    return
                time.sleep(2)

        threading.Thread(target=vigiar, daemon=True).start()
        try:
            for linha in proc.stdout:
                if linha.startswith("out_time_us=") and linha[12:].strip().isdigit():
                    visto[0] = time.time()
                    if tarefa:
                        fr = min(1.0, int(linha[12:]) / 1e6 / max(duracao, 0.1))
                        tarefa.avancar(faixa[0] + (faixa[1] - faixa[0]) * fr, f"Processando o trecho ({nome}) {round(fr * 100)}%")
        except BaseException:  # tarefa cancelada no meio: encerra o ffmpeg e apaga o arquivo pela metade
            proc.kill()
            proc.wait()
            temp.unlink(missing_ok=True)
            raise
        erro = proc.stderr.read()
        if proc.wait() == 0 and temp.exists():
            temp.replace(destino)
            return
        temp.unlink(missing_ok=True)
        if parado.is_set():
            raise RuntimeError("A plataforma parou de enviar o vídeo por mais de 90 segundos. Tente de novo mais tarde.")
    linhas = [l for l in erro.splitlines() if l.strip()]
    if any(x in erro for x in ("403", "401", "Forbidden")):
        raise RuntimeError("A plataforma recusou o acesso ao vídeo deste trecho (gravação restrita ou protegida).")
    raise RuntimeError(f"Não consegui processar o trecho: {linhas[-1] if linhas else 'erro desconhecido'}")


def _chat_twitch(bruto: Path, base: float) -> list[dict]:
    """Converte o chat do TwitchDownloader para o tempo da fonte (0 = início do arquivo)."""
    saida = []
    for c in (ler_json(bruto, {}) or {}).get("comments", []):
        msg = c.get("message") or {}
        texto = str(msg.get("body") or "").strip()
        if not texto:
            continue
        cor = msg.get("user_color") or ""
        saida.append({"t": round(float(c.get("content_offset_seconds", 0)) - base, 2),
                      "n": str((c.get("commenter") or {}).get("display_name") or "")[:25], "m": texto[:220],
                      "c": cor.upper() if re.fullmatch(r"#[0-9a-fA-F]{6}", cor) else ""})
    return sorted(saida, key=lambda x: x["t"])


def _origem(o) -> dict | None:
    """De onde o corte veio e por que (clipe e views, regra do automático, momento e nota da gravação): vai junto no cortes.json."""
    if not isinstance(o, dict):
        return None
    try:
        return o if len(json.dumps(o, ensure_ascii=False)) <= 6000 else None
    except (TypeError, ValueError):
        return None


def criar_corte(d: dict, tarefa=None) -> dict:
    avancar = tarefa.avancar if tarefa else (lambda *_: None)
    ini, fim = float(d.get("inicio", -1)), float(d.get("fim", -1))
    if ini < 0 or fim - ini < 1:
        raise ValueError("Marque um início e um fim com pelo menos 1 segundo de diferença.")
    if fim - ini > 600:
        raise ValueError("O trecho pode ter no máximo 10 minutos.")
    titulo_corte = str(d.get("titulo") or "").strip()[:200]
    streamer = str(d.get("streamer") or "").strip()[:60]

    video_twitch = None
    if d.get("tipo") == "arquivo":
        caminho = caminho_local(str(d.get("id", "")))
        if not caminho:
            raise ValueError("Abra o arquivo de novo: ele foi movido ou renomeado.")
        total = editor.sondar(caminho)["dur"]
        plataforma = d.get("plataforma") if d.get("plataforma") in ("Twitch", "Kick") else "Arquivos"  # gravação de live vai para a pasta da plataforma
        nome, origem, titulo_live = caminho.stem, str(caminho), caminho.stem
        entradas, margem = [str(caminho)], MARGEM
    else:
        if not d.get("autorizado"):
            raise ValueError("Confirme que você tem autorização para usar este trecho.")
        v = identificar(str(d.get("link", "")))
        if v["tipo"] != "vod":
            raise ValueError("Use o link de uma gravação.")
        prefixo = {"Twitch": "TwitchVod_v", "Kick": "KickVOD_"}.get(v["plataforma"], "Video_")
        nome, plataforma, origem = f"{prefixo}{v['id']}", v["plataforma"], v["link"]
        titulo_live = str(d.get("titulo_live") or "") or nome
        total = float(d.get("duracao") or 0)
        margem = MARGEM if v["plataforma"] == "Twitch" else MARGEM_SEM_PLAYER
        if v["plataforma"] == "Twitch":
            video_twitch = v["id"]
        avancar(0.04, "Pedindo o endereço do vídeo à plataforma")
        try:
            entradas = fontes.enderecos(v["link"], fontes.FORMATO_VIDEO)
        except SystemExit as e:
            raise RuntimeError(f"{e} Nada foi baixado. Se você recebeu o arquivo do criador, use Arquivo do PC.") from None
    if total and ini >= total:
        raise ValueError("O início marcado passa do fim do vídeo.")

    pasta = pasta_da_live(nome, plataforma)
    info = ler_json(pasta / "live.json", {}) or {}
    info.update({"titulo": info.get("titulo") or titulo_live, "plataforma": plataforma, "origem": origem})
    if streamer:
        info["streamer"] = streamer
    gravar_json(pasta / "live.json", info)

    a = max(0.0, ini - margem)
    b = min(total, fim + margem) if total else fim + margem
    stem = f"manual_{_hora(ini)}_{int(time.time()) % 100000:05d}"
    destino = pasta / "fontes" / f"{stem}.mp4"
    avancar(0.08, "Processando só o trecho escolhido")
    extrair_trecho(entradas, a, b - a, destino, tarefa)
    s = editor.sondar(destino)
    if s["dur"] < (fim - ini) * 0.5:
        destino.unlink(missing_ok=True)
        raise RuntimeError("O trecho veio incompleto. Confira se os tempos estão dentro da duração do vídeo.")
    gravar_json(destino.with_suffix(".json"), {"arquivo": destino.resolve().relative_to(LIVES.resolve()).as_posix(), "t0": round(a, 3),
                                                 "dur": s["dur"], "w": s["w"], "h": s["h"], "fps": s["fps"], "original": True, "aviso": "",
                                                 "origem_local": origem if d.get("tipo") == "arquivo" else ""})
    chat_msg = ""
    if video_twitch:
        avancar(0.74, "Buscando o chat da gravação")
        bruto = pasta / "fontes" / f"_{stem}_chat.json"
        if fontes.baixar_chat_twitch(video_twitch, bruto, a, b - a):
            gravar_json(pasta / "fontes" / f"{stem}.chat.json", _chat_twitch(bruto, a))
            bruto.unlink(missing_ok=True)
        else:
            chat_msg = "O chat desta gravação não pôde ser baixado."

    lista = ler_json(pasta / "cortes" / "cortes.json", []) or []
    nota = d.get("nota")
    item = {"nota": int(nota) if isinstance(nota, (int, float)) and 0 <= nota <= 100 else None, "manual": True,  # manual: a fonte fica em fontes/
            "inicio": round(ini, 2), "fim": round(fim, 2), "desloc": 0, "pico": round(ini, 2),
            "arquivo": f"{stem}.mp4", "texto": titulo_corte, "motivo": str(d.get("motivo") or "").strip()[:300] or "Trecho escolhido manualmente.",
            "momento_na_live": _hora(ini), "criado": time.time(),
            "formato": d.get("formato") if d.get("formato") in editor.FORMATOS else "9:16"}
    origem = _origem(d.get("origem_info"))
    if origem:
        item["origem"] = origem
    lista.append(item)
    gravar_json(pasta / "cortes" / "cortes.json", lista)
    corte_id = f"{plataforma}/{pasta.name}/{stem}.mp4"

    avancar(0.8, "Transcrevendo a fala para as legendas")
    aviso = chat_msg
    try:
        editor.transcrever_fonte(corte_id, "medium")
    except RuntimeError as e:
        aviso = (aviso + " " + str(e)).strip()
    return {"corte": corte_id, "aviso": aviso}
