"""Painel Vice Clips: gera, organiza e edita cortes. Só responde neste PC, em http://127.0.0.1:8765."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from cortes import armazenamento, descobrir, editor, efeitos, producao, referencias, sons, vods
from cortes.canais import canais
from cortes.config import DADOS, LIVES, ffmpeg, ler_json
from cortes.fontes import eh_link
from cortes.tarefas import fila

BASE = Path(__file__).parent
WEB = BASE / "cortes" / "web"
THUMBS = DADOS / "thumbs"
PORTA = int(os.environ.get("VC_PORTA", 8765))
HOSTS = {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}
MODELOS = {"small", "medium", "large-v3"}
WEBCAMS = {
    "inferior-direito": "0.72,0.68,0.26,0.30",
    "inferior-esquerdo": "0.02,0.68,0.26,0.30",
    "superior-direito": "0.72,0.02,0.26,0.30",
    "superior-esquerdo": "0.02,0.02,0.26,0.30",
}
SEM_JANELA = subprocess.CREATE_NO_WINDOW
vagas_thumb = threading.Semaphore(2)


class Trabalho:
    """Roda um corte por vez e guarda o que ele vai escrevendo."""

    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.ativo = False
        self.codigo: int | None = None
        self.linhas: deque[str] = deque(maxlen=300)

    def iniciar(self, argumentos: list[str]) -> bool:
        with self.trava:
            if self.ativo:
                return False
            self.ativo, self.codigo = True, None
            self.linhas.clear()
            self.proc = subprocess.Popen(
                [sys.executable, "-u", str(BASE / "cortar.py"), *argumentos], cwd=BASE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=SEM_JANELA,
            )
        threading.Thread(target=self._ler, args=(self.proc,), daemon=True).start()
        return True

    def _ler(self, proc: subprocess.Popen) -> None:
        for linha in proc.stdout:
            self.linhas.append(linha.rstrip())
        self.codigo = proc.wait()
        self.ativo = False

    def parar(self) -> None:
        if self.ativo and self.proc:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, creationflags=SEM_JANELA)


trabalho = Trabalho()


def listar_lives() -> list[dict]:
    """Cada corte sai com o estado: pronto para editar, em edição ou exportado."""
    lives = []
    arquivos = sorted(LIVES.glob("*/*/cortes/cortes.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for resumo in arquivos:
        pasta = resumo.parent
        live = pasta.parent
        info = ler_json(live / "live.json", {}) or {}
        base = f"{live.parent.name}/{live.name}"
        editados = [e for e in ler_json(pasta / "editados" / "editados.json", []) or [] if (pasta / "editados" / e["arquivo"]).exists()]
        cortes = []
        for c in ler_json(resumo, []) or []:
            stem = Path(c["arquivo"]).stem
            momento = 1.5
            if (pasta / c["arquivo"]).exists():
                rel = quote(f"{base}/cortes/{c['arquivo']}")
            elif c.get("manual") and (live / "fontes" / f"{stem}.mp4").exists():
                rel = quote(f"{base}/fontes/{stem}.mp4")
                momento = max(0.0, c["inicio"] - float((ler_json(live / "fontes" / f"{stem}.json", {}) or {}).get("t0", c["inicio"])) + 1)
            else:
                continue
            eds = [{**e, "thumb": "/thumb/" + quote(f"{base}/cortes/editados/{e['arquivo']}")} for e in editados if e.get("origem") == c["arquivo"]]
            estado = "exportado" if eds else "editando" if (live / "projetos" / f"{stem}.json").exists() else "pronto"
            cortes.append({
                "id": f"{base}/{c['arquivo']}", "nota": c.get("nota"), "manual": bool(c.get("manual")), "estado": estado,
                "momento": c.get("momento_na_live", ""), "texto": c.get("texto", ""),
                "motivo": c.get("motivo", ""), "duracao": round(c["fim"] - c["inicio"]), "arquivo": c["arquivo"],
                "url": f"/video/{rel}", "thumb": f"/thumb/{rel}?t={momento:.1f}", "editados": eds,
                "criado": c.get("criado"), "inicio": c.get("inicio"), "fim": c.get("fim"), "origem": c.get("origem"),
            })
        if cortes:
            lives.append({"plataforma": live.parent.name, "titulo": info.get("titulo", live.name), "streamer": info.get("streamer", ""),
                          "pasta": f"{base}/cortes", "cortes": cortes, "nome": live.name, "origem_live": str(info.get("origem") or "")})
    return lives


def montar_argumentos(d: dict) -> list[str]:
    video = str(d.get("video", "")).strip().strip('"')
    if not (eh_link(video) or Path(video).is_file()):
        raise ValueError("Cole um link válido ou escolha um vídeo deste PC.")
    args = [video, "--qtd", str(max(3, min(int(d.get("qtd") or 5), 10)))]
    dur_min, dur_max = float(d.get("dur_min") or 12), float(d.get("dur_max") or 70)
    if not 5 <= dur_min < dur_max <= 180:
        raise ValueError("A duração mínima precisa ser menor que a máxima, entre 5 e 180 segundos.")
    args += ["--dur-min", str(dur_min), "--dur-max", str(dur_max)]
    inicio = str(d.get("inicio") or "").strip()
    if inicio:
        if not re.fullmatch(r"\d{1,3}(:\d{1,2}){0,2}", inicio):
            raise ValueError("Use o início no formato HH:MM:SS.")
        args += ["--inicio", inicio]
    if d.get("minutos"):
        minutos = float(d["minutos"])
        if minutos <= 0:
            raise ValueError("A quantidade de minutos precisa ser maior que zero.")
        args += ["--minutos", str(minutos)]
    if d.get("webcam") in WEBCAMS:
        args += ["--webcam", WEBCAMS[d["webcam"]]]
    if d.get("modelo") in MODELOS:
        args += ["--modelo", d["modelo"]]
    return args


def escolher_arquivo(audio: bool = False) -> str:
    tipos = "('Áudio','*.wav *.mp3 *.ogg *.m4a *.flac *.aac *.opus')" if audio else "('Vídeos','*.mp4 *.mkv *.mov *.webm *.ts *.flv')"
    codigo = ("import tkinter as t, tkinter.filedialog as f; r=t.Tk(); r.withdraw(); r.attributes('-topmost', True); "
              f"print(f.askopenfilename(title='Escolha o arquivo', filetypes=[{tipos},('Todos','*.*')]))")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip().replace("/", "\\")


def gerar_thumb(alvo: Path, momento: float = 1.5) -> Path | None:
    chave = hashlib.sha1(f"{alvo}:{alvo.stat().st_mtime_ns}:{momento:.1f}".encode()).hexdigest()[:20]
    destino = THUMBS / f"{chave}.jpg"
    if destino.exists():
        return destino
    THUMBS.mkdir(parents=True, exist_ok=True)
    with vagas_thumb:
        if not destino.exists():
            temp = destino.with_suffix(".tmp.jpg")
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{momento:.1f}", "-i", str(alvo), "-frames:v", "1", "-vf", "scale=405:-2",
                            "-q:v", "4", str(temp)], capture_output=True, creationflags=SEM_JANELA)
            if temp.exists():
                temp.replace(destino)
    return destino if destino.exists() else None


def resumo_painel() -> dict:
    lives = listar_lives()
    cortes = [c for l in lives for c in l["cortes"]]
    return {"lives": len(lives), "cortes": len(cortes), "editados": sum(len(c["editados"]) for c in cortes),
            "gerando": trabalho.ativo, "tarefas": fila.listar()}


class Painel(BaseHTTPRequestHandler):
    def log_message(self, *_) -> None:
        pass

    def _json(self, dados, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, alvo: Path, tipo: str) -> None:
        corpo = alvo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(corpo)

    def _permitido(self) -> bool:
        if self.headers.get("Host") in HOSTS:
            return True
        self.send_error(403)
        return False

    def do_GET(self) -> None:
        if not self._permitido():
            return
        partes = urlsplit(self.path)
        caminho, consulta = partes.path, parse_qs(partes.query)
        corte = (consulta.get("corte") or [""])[0]
        try:
            if caminho == "/":
                self._arquivo(BASE / "cortes" / "painel.html", "text/html; charset=utf-8")
            elif caminho.startswith("/static/"):
                alvo = (WEB / unquote(caminho[8:])).resolve()
                if WEB.resolve() in alvo.parents and alvo.is_file():
                    tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
                    self._arquivo(alvo, f"{tipo}; charset=utf-8" if tipo.startswith("text/") or "javascript" in tipo else tipo)
                else:
                    self.send_error(404)
            elif caminho == "/api/estado":
                self._json({"rodando": trabalho.ativo, "codigo": trabalho.codigo, "linhas": list(trabalho.linhas)})
            elif caminho == "/api/lives":
                self._json(listar_lives())
            elif caminho == "/api/resumo":
                self._json(resumo_painel())
            elif caminho == "/api/tarefas":
                self._json(fila.listar())
            elif caminho == "/api/canais":
                self._json(canais.listar())
            elif caminho == "/api/config":
                self._json({**canais.publico(), "dados": str(DADOS)})
            elif caminho == "/api/editor/abrir":
                self._api(lambda: editor.abrir(corte))
            elif caminho == "/api/editor/onda":
                self._api(lambda: {"picos": editor.onda(corte)})
            elif caminho.startswith("/video/"):
                self._video(unquote(caminho[len("/video/"):]))
            elif caminho.startswith("/thumb/"):
                self._thumb(unquote(caminho[len("/thumb/"):]), (consulta.get("t") or ["1.5"])[0])
            elif caminho.startswith("/local/"):
                alvo = vods.caminho_local(caminho[len("/local/"):])
                if alvo:
                    self._enviar(alvo, vods.tipo_navegador(alvo))
                else:
                    self.send_error(404)
            elif caminho.startswith("/grafico/"):
                alvo = (editor.GRAFICOS / unquote(caminho[len("/grafico/"):])).resolve()
                if editor.GRAFICOS.resolve() in alvo.parents and alvo.is_file():
                    self._arquivo(alvo, mimetypes.guess_type(alvo.name)[0] or "application/octet-stream")
                else:
                    self.send_error(404)
            elif caminho.startswith("/som/"):
                alvo = efeitos.arquivo_som(unquote(caminho[len("/som/"):]))
                if alvo:
                    self._enviar(alvo, mimetypes.guess_type(alvo.name)[0] or "audio/wav")
                else:
                    self.send_error(404)
            elif caminho == "/api/sons":
                self._json(sons.listar())
            elif caminho == "/api/vod/recentes":
                self._json(vods.recentes())
            elif caminho in ROTAS_GET:
                self._api(lambda: ROTAS_GET[caminho](consulta))
            else:
                self.send_error(404)
        except ConnectionError:
            pass  # o navegador cancela pedaços de vídeo ao avançar o player

    def _api(self, funcao) -> None:
        try:
            self._json(funcao())
        except ValueError as erro:
            self._json({"erro": str(erro)}, 400)

    def do_POST(self) -> None:
        if not self._permitido():
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.send_error(415)
            return
        caminho = urlsplit(self.path).path
        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            d = json.loads(self.rfile.read(tamanho) or b"{}")
            if not isinstance(d, dict):
                raise ValueError
        except ValueError:
            self._json({"erro": "Pedido inválido."}, 400)
            return
        rota = ROTAS.get(caminho)
        if not rota:
            self.send_error(404)
            return
        try:
            self._json(rota(d))
        except (ValueError, TypeError, KeyError) as erro:
            self._json({"erro": str(erro) or "Pedido inválido."}, 400)
        except Exception as erro:  # falhas de rede das plataformas chegam aqui
            self._json({"erro": str(erro)}, 502)

    def _thumb(self, relativo: str, momento: str = "1.5") -> None:
        raiz = LIVES.resolve()
        alvo = (raiz / relativo).resolve()
        if raiz not in alvo.parents or alvo.suffix.lower() != ".mp4" or not alvo.is_file():
            self.send_error(404)
            return
        try:
            t = max(0.0, min(float(momento), 36000.0))
        except ValueError:
            t = 1.5
        imagem = gerar_thumb(alvo, t)
        if imagem:
            self._arquivo(imagem, "image/jpeg")
        else:
            self.send_error(404)

    def _video(self, relativo: str) -> None:
        raiz = LIVES.resolve()
        alvo = (raiz / relativo).resolve()
        if raiz not in alvo.parents or alvo.suffix.lower() != ".mp4" or not alvo.is_file():
            self.send_error(404)
            return
        self._enviar(alvo, "video/mp4")

    def _enviar(self, alvo: Path, tipo: str) -> None:
        """Entrega vídeo em pedaços, para o player conseguir avançar sem baixar tudo."""
        total = alvo.stat().st_size
        ini, fim = 0, total - 1
        pedido = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        parcial = bool(pedido and (pedido[1] or pedido[2]))
        if parcial:
            if pedido[1]:
                ini = int(pedido[1])
                fim = min(int(pedido[2]), fim) if pedido[2] else fim
            else:
                ini = max(total - int(pedido[2]), 0)
            if ini > fim:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.end_headers()
                return
        self.send_response(206 if parcial else 200)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fim - ini + 1))
        if parcial:
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{total}")
        self.end_headers()
        with alvo.open("rb") as f:
            f.seek(ini)
            resta = fim - ini + 1
            while resta > 0:
                bloco = f.read(min(256 * 1024, resta))
                if not bloco:
                    break
                self.wfile.write(bloco)
                resta -= len(bloco)


def _abrir_pasta(d: dict) -> dict:
    raiz = LIVES.resolve()
    alvo = (raiz / str(d.get("pasta", ""))).resolve()
    if raiz in alvo.parents and alvo.is_dir():
        os.startfile(str(alvo))
        return {"ok": True}
    raise ValueError("Pasta não encontrada.")


def _gerar(d: dict) -> dict:
    if not trabalho.iniciar(montar_argumentos(d)):
        raise ValueError("Já existe um corte em andamento.")
    return {"ok": True}


def _parar(_: dict) -> dict:
    trabalho.parar()
    return {"ok": True}


def _preparar(d: dict) -> dict:
    corte = editor.achar_corte(d.get("corte", "")).id
    return fila.adicionar("fonte", "Preparando fonte original", lambda t: editor.preparar_fonte(corte, t), f"fonte:{corte}").publico()


def _exportar(d: dict) -> dict:
    corte = editor.achar_corte(d.get("corte", "")).id
    projeto = d.get("projeto") or {}
    editor.salvar_projeto(corte, projeto, str(d.get("streamer") or ""))
    chat = _chat_pronto(d.get("chat"))
    return fila.adicionar("exportar", f"Exportando {Path(corte).stem}", lambda t: editor.exportar(corte, projeto, t, chat)).publico()


def _chat_pronto(lista) -> list[dict]:
    """Linhas do chat já quebradas pelo editor, para o vídeo final ficar igual à prévia."""
    saida = []
    for m in (lista if isinstance(lista, list) else [])[:1500]:
        if not isinstance(m, dict) or not isinstance(m.get("l"), list):
            continue
        cor = m.get("c") if isinstance(m.get("c"), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", m["c"]) else "#B98CFF"
        try:
            saida.append({"t": float(m["t"]), "k": max(0, min(int(m.get("k") or 0), 40)), "c": cor,
                          "l": [str(x)[:120] for x in m["l"][:12]]})
        except (TypeError, ValueError, KeyError):
            continue
    return saida


def _corte_vod(d: dict) -> dict:
    titulo = "Preparando trecho do arquivo" if d.get("tipo") == "arquivo" else "Baixando só o trecho escolhido"
    return fila.adicionar("corte", titulo, lambda t: vods.criar_corte(d, t)).publico()


def _abrir_arquivo(d: dict) -> dict:
    caminho = str(d.get("caminho") or "").strip() or escolher_arquivo()
    return vods.abrir_arquivo(caminho) if caminho else {"cancelado": True}


def _grafico(d: dict) -> dict:
    m = re.fullmatch(r"data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)", str(d.get("dados", "")))
    if not m:
        raise ValueError("Use uma imagem PNG, JPG, WEBP ou GIF.")
    bruto = base64.b64decode(m[2])
    if len(bruto) > 12 * 1024 * 1024:
        raise ValueError("A imagem passa de 12 MB.")
    nome = hashlib.sha1(bruto).hexdigest()[:16] + {"jpeg": ".jpg"}.get(m[1], f".{m[1]}")
    editor.GRAFICOS.mkdir(parents=True, exist_ok=True)
    (editor.GRAFICOS / nome).write_bytes(bruto)
    return {"arquivo": nome, "url": f"/grafico/{nome}"}


def _anexar_clip(d: dict) -> dict:
    """Arquivo autorizado do clip (recebido do criador, por exemplo): vira um corte editável."""
    clip = next((c for c in canais.cfg["clips"] if c["id"] == str(d.get("id", ""))), None)
    if not clip:
        raise ValueError("Clip não encontrado.")
    caminho = escolher_arquivo()
    if not caminho:
        return {"cancelado": True}
    info = vods.abrir_arquivo(caminho)

    def trabalho_anexar(t):
        r = vods.criar_corte({"tipo": "arquivo", "id": info["id"], "inicio": 0, "fim": max(1.0, info["duracao"] - 0.05),
                              "titulo": clip.get("titulo", ""), "streamer": clip["login"]}, t)
        canais.anexar_clip(clip["id"], r["corte"])
        return r
    return fila.adicionar("corte", "Importando arquivo do clip", trabalho_anexar).publico()


def _importar_som(d: dict) -> dict:
    caminho = str(d.get("caminho") or "").strip() or escolher_arquivo(True)
    return sons.importar(caminho, str(d.get("categoria") or "musica")) if caminho else {"cancelado": True}


def _quadro(d: dict) -> dict:
    png = editor.quadro(editor.achar_corte(d.get("corte", "")).id, d.get("projeto") or {}, float(d.get("t") or 0), _chat_pronto(d.get("chat")))
    return {"png": "data:image/png;base64," + base64.b64encode(png).decode()}


def _salvar(d: dict) -> dict:
    editor.salvar_projeto(editor.achar_corte(d.get("corte", "")).id, d.get("projeto") or {}, str(d.get("streamer") or ""))
    return {"ok": True}


def _transcrever(d: dict) -> dict:
    corte = editor.achar_corte(d.get("corte", "")).id
    modelo = d.get("modelo") if d.get("modelo") in MODELOS else "medium"
    return fila.adicionar("legenda", "Transcrevendo o trecho", lambda t: editor.transcrever_fonte(corte, modelo, t), f"legenda:{corte}").publico()


def _importar_clip(d: dict) -> dict:
    clip = str(d.get("id", ""))
    return fila.adicionar("clip", "Baixando clip da Twitch", lambda t: canais.importar_clip(clip, t), f"clip:{clip}").publico()


def _canal(d: dict) -> dict:
    canais.adicionar(str(d.get("plataforma", "twitch")), str(d.get("login", "")))
    return {"ok": True}


def _config(d: dict) -> dict:
    canais.configurar(d)
    return canais.publico()


ROTAS = {
    "/api/parar": _parar,
    "/api/abrir-pasta": _abrir_pasta,
    "/api/gerar": _gerar,
    "/api/escolher-arquivo": lambda _: {"caminho": escolher_arquivo()},
    "/api/editor/preparar": _preparar,
    "/api/editor/salvar": _salvar,
    "/api/editor/exportar": _exportar,
    "/api/editor/transcrever": _transcrever,
    "/api/editor/detectar-webcam": lambda d: editor.detectar_webcam(d.get("corte", "")),
    "/api/editor/detectar-rosto": lambda d: editor.detectar_rosto(d.get("corte", ""), d.get("regiao")),
    "/api/corte/excluir": lambda d: editor.excluir_varios(d.get("cortes") if isinstance(d.get("cortes"), list) else [d.get("corte", "")], str(d.get("editado") or "")),
    "/api/corte/restaurar": lambda d: editor.restaurar(d.get("lixeiras") if isinstance(d.get("lixeiras"), list) else []),
    "/api/editor/estilo": lambda d: {"estilos": editor.salvar_estilo(d.get("nome", ""), d.get("estilo"))},
    "/api/editor/layout-streamer": lambda d: {"layout": editor.salvar_layout_streamer(str(d.get("streamer") or ""), d.get("projeto") or {})},
    "/api/editor/template": lambda d: {"templates": editor.salvar_template(d.get("nome", ""), d.get("projeto"))},
    "/api/editor/quadro": _quadro,
    "/api/marca": lambda d: editor.salvar_marca(d),
    "/api/sons/importar": _importar_som,
    "/api/kick/testar": lambda _: canais.testar_kick(),
    "/api/config": _config,
    "/api/twitch/conectar": lambda _: canais.conectar_twitch(),
    "/api/twitch/desconectar": lambda _: (canais.desconectar_twitch(), {"ok": True})[1],
    "/api/twitch/clip": lambda d: canais.criar_clip(str(d.get("login", "")), int(d.get("duracao") or 30), str(d.get("titulo") or "")),
    "/api/twitch/importar-clip": _importar_clip,
    "/api/canais/adicionar": _canal,
    "/api/vod/abrir": lambda d: vods.abrir_link(str(d.get("url", ""))),
    "/api/vod/corte": _corte_vod,
    "/api/arquivo/abrir": _abrir_arquivo,
    "/api/grafico": _grafico,
    "/api/clip/anexar": _anexar_clip,
    "/api/canais/remover": lambda d: (canais.remover(str(d.get("plataforma", "")), str(d.get("login", ""))), {"ok": True})[1],
    "/api/tarefas/cancelar": lambda d: fila.cancelar(str(d.get("id", ""))),
    "/api/tarefas/limpar": lambda _: fila.limpar(),
}
# Módulos independentes registram as próprias rotas: GET recebe a consulta (dict de listas), POST recebe o JSON.
ROTAS_GET: dict = {}
for _modulo in (descobrir, referencias, armazenamento, producao):
    ROTAS.update(_modulo.POST)
    ROTAS_GET.update(_modulo.GET)
ROTAS_GET["/api/producao"] = producao._rota(lambda consulta: producao.listar(listar_lives(), consulta))


class Servidor(ThreadingHTTPServer):
    allow_reuse_address = False  # no Windows, reusar deixaria dois painéis disputando a mesma porta


def main() -> None:
    endereco = f"http://127.0.0.1:{PORTA}"
    abrir = "--sem-navegador" not in sys.argv
    try:
        servidor = Servidor(("127.0.0.1", PORTA), Painel)
    except OSError:  # o painel já está aberto
        print("O painel já está aberto em outra janela. Se a tela aparecer sem estilo, feche a janela antiga e abra de novo.", flush=True)
        if abrir:
            webbrowser.open(endereco)
        return
    canais.iniciar()
    descobrir.iniciar()
    print(f"Painel aberto em {endereco}. Feche esta janela para desligar.", flush=True)
    if abrir:
        webbrowser.open(endereco)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
