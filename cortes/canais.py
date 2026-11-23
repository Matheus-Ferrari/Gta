"""Lives ao vivo pelas APIs oficiais: status na Twitch e na Kick, clips e sugestões vindas do chat da Twitch."""
from __future__ import annotations

import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, deque
from pathlib import Path

from .config import DADOS, LIVES, gravar_json, ler_json, pasta_da_live
from .sinais import extrair_audio, normalizar_msg

ARQ = DADOS / "config.json"
TWITCH_ID = os.environ.get("VC_TWITCH_ID", "https://id.twitch.tv")
TWITCH_API = os.environ.get("VC_TWITCH_API", "https://api.twitch.tv/helix")
TWITCH_IRC = os.environ.get("VC_TWITCH_IRC", "irc.chat.twitch.tv:6697")
KICK_ID = os.environ.get("VC_KICK_ID", "https://id.kick.com")
KICK_API = os.environ.get("VC_KICK_API", "https://api.kick.com/public/v1")
ESCOPOS = "clips:edit chat:read editor:manage:clips"
INTERVALO = 45
PRAZO_CLIP = 60


LIMITE: dict = {}  # últimos cabeçalhos Ratelimit-* da Helix: pontos restantes e quando o balde enche (epoch em segundos)


def _anotar_limite(url: str, cab) -> None:
    if cab is not None and url.startswith(TWITCH_API) and cab.get("Ratelimit-Remaining") is not None:
        try:
            LIMITE.update(limite=int(cab.get("Ratelimit-Limit") or 0), restante=int(cab["Ratelimit-Remaining"]),
                          reset=int(cab.get("Ratelimit-Reset") or 0), visto=time.time())
        except ValueError:
            pass


class ErroApi(Exception):
    def __init__(self, status: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status = status


def _pedir(url: str, metodo: str = "GET", cabecalhos: dict | None = None, dados: dict | None = None) -> tuple[int, dict]:
    corpo = urllib.parse.urlencode(dados).encode() if dados is not None else None
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers={"User-Agent": "ViceClips/1.0", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as r:
            _anotar_limite(url, r.headers)
            texto = r.read().decode("utf-8", "replace")
            return r.status, json.loads(texto) if texto.strip() else {}
    except urllib.error.HTTPError as e:
        _anotar_limite(url, e.headers)
        texto = e.read().decode("utf-8", "replace")
        try:
            info = json.loads(texto)
        except ValueError:
            info = {}
        raise ErroApi(e.code, str(info.get("message") or info.get("error") or f"Erro {e.code}")) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroApi(0, f"Sem conexão com a plataforma ({e})") from None


class DetectorChat:
    """Avisa quando o chat acelera ou repete a mesma reação. Quem decide criar o clip é você."""

    def __init__(self, janela: int = 15, recarga: int = 90) -> None:
        self.janela, self.recarga = janela, recarga
        self.msgs: deque[tuple[float, str]] = deque()
        self.ultimo = -1e9

    def registrar(self, t: float, texto: str) -> dict | None:
        self.msgs.append((t, normalizar_msg(texto)))
        while self.msgs and self.msgs[0][0] < t - 300:
            self.msgs.popleft()
        limite = t - self.janela
        recentes = [m for q, m in self.msgs if q > limite]
        antes = len(self.msgs) - len(recentes)
        tempo_antes = limite - self.msgs[0][0]
        if tempo_antes < 60 or t - self.ultimo < self.recarga or len(recentes) < 10:
            return None
        normal = max(antes / tempo_antes * self.janela, 1.0)
        ritmo = len(recentes) / normal
        top, vezes = Counter(recentes).most_common(1)[0]
        repetiu = vezes >= 8 and vezes / len(recentes) >= 0.3 and ritmo >= 1.5
        if ritmo < 3 and not repetiu:
            return None
        self.ultimo = t
        motivo = f"Chat {ritmo:.1f}x mais rápido"
        return {"motivo": motivo + (f", “{top[:18]}” repetido {vezes}x" if vezes >= 5 else ""), "ritmo": round(ritmo, 1)}


class Canais:
    def __init__(self) -> None:
        self.trava = threading.RLock()
        self.cfg: dict = ler_json(ARQ, {}) or {}
        self.cfg.setdefault("twitch", {})
        self.cfg.setdefault("kick", {})
        self.cfg.setdefault("canais", [])
        self.cfg.setdefault("clips", [])
        self.estado: dict[str, dict] = {}
        self.sugestoes: deque[dict] = deque(maxlen=20)
        self.login_tw: dict = {}
        self.chats: dict[str, threading.Event] = {}
        self.iniciado = False

    def iniciar(self) -> None:
        if not self.iniciado:
            self.iniciado = True
            threading.Thread(target=self._laco, daemon=True).start()

    def _salvar(self) -> None:
        with self.trava:
            gravar_json(ARQ, self.cfg)

    # ------------------------------------------------------ configuração

    def publico(self) -> dict:
        tw, kk = self.cfg["twitch"], self.cfg["kick"]
        return {
            "twitch": {"client_id": tw.get("client_id", ""), "conectado": bool(tw.get("refresh_token")), "login": tw.get("login", ""),
                       "pendente": {k: self.login_tw.get(k) for k in ("codigo", "url", "erro")} if self.login_tw else None},
            "kick": {"client_id": kk.get("client_id", ""), "tem_segredo": bool(kk.get("client_secret")), "conectado": bool(kk.get("token"))},
        }

    def configurar(self, d: dict) -> None:
        with self.trava:
            if "twitch_client_id" in d:
                novo = str(d["twitch_client_id"]).strip()[:64]
                if novo != self.cfg["twitch"].get("client_id"):
                    self.cfg["twitch"] = {"client_id": novo}
            if "kick_client_id" in d:
                self.cfg["kick"]["client_id"] = str(d["kick_client_id"]).strip()[:128]
                self.cfg["kick"].pop("token", None)
            if d.get("kick_client_secret"):
                self.cfg["kick"]["client_secret"] = str(d["kick_client_secret"]).strip()[:256]
                self.cfg["kick"].pop("token", None)
            self._salvar()

    # ------------------------------------------------------ login Twitch (Device Code Flow)

    def conectar_twitch(self) -> dict:
        cid = self.cfg["twitch"].get("client_id")
        if not cid:
            raise ValueError("Informe o Client ID da Twitch em Configurações.")
        try:
            _, r = _pedir(f"{TWITCH_ID}/oauth2/device", "POST", dados={"client_id": cid, "scopes": ESCOPOS})
        except ErroApi as e:
            if e.status in (400, 401, 403, 404):
                raise ValueError("A Twitch recusou este Client ID. Confira se copiou certo e se o aplicativo é do tipo Público.") from None
            raise ValueError(str(e)) from None
        self.login_tw = {"codigo": r["user_code"], "url": r["verification_uri"], "erro": None}
        threading.Thread(target=self._aguardar_login, args=(cid, r["device_code"], int(r.get("interval", 5)), int(r.get("expires_in", 1800))),
                         daemon=True).start()
        return self.login_tw

    def _aguardar_login(self, cid: str, device: str, intervalo: int, validade: int) -> None:
        fim = time.time() + validade
        while time.time() < fim:
            time.sleep(intervalo)
            try:
                _, r = _pedir(f"{TWITCH_ID}/oauth2/token", "POST", dados={
                    "client_id": cid, "scopes": ESCOPOS, "device_code": device,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            except ErroApi as e:
                if e.status == 400 and ("pending" in str(e).lower() or "slow_down" in str(e).lower()):
                    continue
                self.login_tw = {**self.login_tw, "erro": str(e)}
                return
            with self.trava:
                self.cfg["twitch"].update(access_token=r["access_token"], refresh_token=r["refresh_token"])
            try:
                eu = self._helix("GET", "/users")["data"][0]
                with self.trava:
                    self.cfg["twitch"].update(login=eu["login"], user_id=eu["id"])
                self._salvar()
                self.login_tw = {}
            except (ErroApi, IndexError, KeyError) as e:
                self.login_tw = {**self.login_tw, "erro": f"Conta conectada, mas não consegui ler o perfil: {e}"}
            return
        self.login_tw = {**self.login_tw, "erro": "O código expirou. Tente conectar de novo."}

    def desconectar_twitch(self) -> None:
        with self.trava:
            self.cfg["twitch"] = {"client_id": self.cfg["twitch"].get("client_id", "")}
            self.login_tw = {}
            self._salvar()

    def _renovar(self) -> None:
        tw = self.cfg["twitch"]
        _, r = _pedir(f"{TWITCH_ID}/oauth2/token", "POST", dados={
            "client_id": tw["client_id"], "grant_type": "refresh_token", "refresh_token": tw["refresh_token"]})
        with self.trava:  # o refresh token só vale uma vez: guarda o novo imediatamente
            tw.update(access_token=r["access_token"], refresh_token=r.get("refresh_token", tw["refresh_token"]))
            self._salvar()

    def _helix(self, metodo: str, caminho: str, parametros: list[tuple[str, str]] | None = None, repetir: bool = True) -> dict:
        tw = self.cfg["twitch"]
        if not tw.get("access_token"):
            raise ErroApi(401, "Conecte sua conta da Twitch em Configurações.")
        url = TWITCH_API + caminho + ("?" + urllib.parse.urlencode(parametros) if parametros else "")
        usado = tw["access_token"]
        try:
            return _pedir(url, metodo, {"Client-Id": tw["client_id"], "Authorization": f"Bearer {usado}"})[1]
        except ErroApi as e:
            if e.status == 401 and repetir and tw.get("refresh_token"):
                with self.trava:  # pedidos paralelos com o token vencido não podem gastar o mesmo refresh token
                    if self.cfg["twitch"].get("access_token") == usado:
                        try:
                            self._renovar()
                        except ErroApi:
                            self.desconectar_twitch()
                            raise ErroApi(401, "A conexão com a Twitch expirou. Conecte a conta de novo.") from None
                return self._helix(metodo, caminho, parametros, False)
            raise

    # ------------------------------------------------------ canais

    def adicionar(self, plataforma: str, login: str) -> None:
        plataforma = plataforma if plataforma in ("twitch", "kick") else "twitch"
        login = re.sub(r"^https?://(www\.)?(twitch\.tv|kick\.com)/", "", login.strip().lower()).strip("/@ ").split("/")[0]
        if not re.fullmatch(r"[a-z0-9_-]{2,25}" if plataforma == "kick" else r"[a-z0-9_]{2,40}", login):
            raise ValueError("Nome de canal inválido.")
        with self.trava:
            if not any(c["plataforma"] == plataforma and c["login"] == login for c in self.cfg["canais"]):
                self.cfg["canais"].append({"plataforma": plataforma, "login": login, "chat": False})
                self._salvar()
        threading.Thread(target=self.atualizar, daemon=True).start()

    def remover(self, plataforma: str, login: str) -> None:
        with self.trava:
            self.cfg["canais"] = [c for c in self.cfg["canais"] if not (c["plataforma"] == plataforma and c["login"] == login)]
            self._salvar()
        self.estado.pop(f"{plataforma}:{login}", None)

    def vigiar_chat(self, login: str, ativo: bool) -> None:
        with self.trava:
            for c in self.cfg["canais"]:
                if c["plataforma"] == "twitch" and c["login"] == login:
                    c["chat"] = bool(ativo)
            self._salvar()

    def _status_twitch(self, logins: list[str]) -> None:
        if not logins:
            return
        if not self.cfg["twitch"].get("access_token"):
            for l in logins:
                self.estado[f"twitch:{l}"] = {"online": None, "erro": "Conecte a conta da Twitch para ver o status."}
            return
        online = {}
        for i in range(0, len(logins), 100):
            parametros = [("user_login", l) for l in logins[i:i + 100]] + [("first", "100")]
            for s in self._helix("GET", "/streams", parametros).get("data", []):
                online[s["user_login"].lower()] = s
        for l in logins:
            s = online.get(l)
            self.estado[f"twitch:{l}"] = {"online": False} if not s else {
                "online": True, "titulo": s.get("title", ""), "jogo": s.get("game_name", ""), "espectadores": s.get("viewer_count", 0),
                "inicio": s.get("started_at", ""), "id_canal": s.get("user_id"), "nome": s.get("user_name", l),
                "thumb": s.get("thumbnail_url", "").replace("{width}", "480").replace("{height}", "270")}

    def _token_kick(self, renovar: bool = False) -> str:
        """O token de aplicativo não tem refresh: quando vence, pede outro com as mesmas credenciais."""
        kk = self.cfg["kick"]
        if not renovar and kk.get("token") and kk.get("expira", 0) > time.time() + 60:
            return kk["token"]
        try:
            _, r = _pedir(f"{KICK_ID}/oauth/token", "POST", dados={"grant_type": "client_credentials", "client_id": kk["client_id"],
                                                                    "client_secret": kk["client_secret"]})
        except ErroApi as e:
            if e.status in (400, 401, 403):
                raise ErroApi(e.status, "A Kick recusou o Client ID ou o Client Secret. Confira os dois em Configurações.") from None
            raise
        with self.trava:
            kk.update(token=r["access_token"], expira=time.time() + int(r.get("expires_in", 3600)))
            self._salvar()
        return kk["token"]

    def _kick_get(self, url: str) -> dict:
        for renovar in (False, True):
            try:
                return _pedir(url, cabecalhos={"Authorization": f"Bearer {self._token_kick(renovar)}"})[1]
            except ErroApi as e:
                if e.status != 401 or renovar:
                    raise
        return {}

    def testar_kick(self) -> dict:
        kk = self.cfg["kick"]
        if not (kk.get("client_id") and kk.get("client_secret")):
            raise ValueError("Preencha o Client ID e o Client Secret da Kick.")
        try:
            self._token_kick(True)
            self._kick_get(f"{KICK_API}/channels?slug=kick")
        except ErroApi as e:
            raise ValueError(str(e)) from None
        threading.Thread(target=self.atualizar, daemon=True).start()
        return {"ok": True, "mensagem": "Conexão com a Kick funcionando."}

    def _status_kick(self, logins: list[str]) -> None:
        if not logins:
            return
        kk = self.cfg["kick"]
        if not (kk.get("client_id") and kk.get("client_secret")):
            for l in logins:
                self.estado[f"kick:{l}"] = {"online": None, "erro": "Informe as credenciais da Kick para ver o status."}
            return
        achados = {}
        for i in range(0, len(logins), 50):
            url = f"{KICK_API}/channels?" + urllib.parse.urlencode([("slug", l) for l in logins[i:i + 50]])
            for c in self._kick_get(url).get("data", []):
                achados[str(c.get("slug", "")).lower()] = c
        for l in logins:
            c = achados.get(l)
            s = (c or {}).get("stream") or {}
            if c is None:
                self.estado[f"kick:{l}"] = {"online": None, "erro": "Canal não encontrado na Kick."}
            else:
                self.estado[f"kick:{l}"] = {"online": bool(s.get("is_live")), "titulo": c.get("stream_title", ""), "jogo": (c.get("category") or {}).get("name", ""),
                                            "espectadores": s.get("viewer_count", 0), "inicio": s.get("start_time", ""), "thumb": s.get("thumbnail", "")}

    def atualizar(self) -> None:
        canais = list(self.cfg["canais"])
        for plataforma, funcao in (("twitch", self._status_twitch), ("kick", self._status_kick)):
            logins = [c["login"] for c in canais if c["plataforma"] == plataforma]
            try:
                funcao(logins)
            except (ErroApi, KeyError) as e:
                for l in logins:
                    self.estado[f"{plataforma}:{l}"] = {"online": None, "erro": str(e)}
        self._ajustar_chats()
        self._conferir_clips()

    def _laco(self) -> None:
        while True:
            self.atualizar()
            for _ in range(INTERVALO):
                time.sleep(1)
                if any(c.get("estado") == "processando" for c in self.cfg["clips"]) and _ % 5 == 4:
                    self._conferir_clips()

    def listar(self) -> dict:
        canais = []
        for c in self.cfg["canais"]:
            canais.append({**c, **self.estado.get(f"{c['plataforma']}:{c['login']}", {"online": None})})
        eu = self.cfg["twitch"].get("login", "").lower()
        clips = [{**c, "meu_canal": c.get("login", "").lower() == eu} for c in reversed(self.cfg["clips"][-30:])]
        return {"canais": canais, "clips": clips, "sugestoes": list(reversed(self.sugestoes))}

    # ------------------------------------------------------ chat da Twitch (somente leitura)

    def _ajustar_chats(self) -> None:
        querem = {c["login"] for c in self.cfg["canais"] if c["plataforma"] == "twitch" and c.get("chat")
                  and self.estado.get(f"twitch:{c['login']}", {}).get("online")}
        if not self.cfg["twitch"].get("login"):
            querem = set()
        for login, parar in list(self.chats.items()):
            if login not in querem:
                parar.set()
                del self.chats[login]
        for login in querem - set(self.chats):
            parar = threading.Event()
            self.chats[login] = parar
            threading.Thread(target=self._ler_chat, args=(login, parar), daemon=True).start()

    def _ler_chat(self, login: str, parar: threading.Event) -> None:
        detector = DetectorChat()
        host, _, porta = TWITCH_IRC.partition(":")
        while not parar.is_set():
            try:
                bruto = socket.create_connection((host, int(porta or 6697)), timeout=30)
                s = ssl.create_default_context().wrap_socket(bruto, server_hostname=host) if int(porta or 6697) == 6697 else bruto
                tw = self.cfg["twitch"]
                s.sendall(f"PASS oauth:{tw['access_token']}\r\nNICK {tw['login'].lower()}\r\nJOIN #{login}\r\n".encode())
                resto = ""
                while not parar.is_set():
                    try:
                        dados = s.recv(8192)
                    except socket.timeout:
                        continue
                    if not dados:
                        break
                    resto += dados.decode("utf-8", "replace")
                    *linhas, resto = resto.split("\r\n")
                    for linha in linhas:
                        if linha.startswith("PING"):
                            s.sendall(linha.replace("PING", "PONG", 1).encode() + b"\r\n")
                        elif "Login authentication failed" in linha:
                            self._renovar()
                            raise OSError("token renovado")
                        elif " PRIVMSG " in linha:
                            achado = detector.registrar(time.time(), linha.split(" :", 1)[-1])
                            if achado:
                                self.sugestoes.append({"plataforma": "twitch", "login": login, "quando": time.time(), **achado})
                s.close()
            except (OSError, ErroApi, KeyError):
                parar.wait(15)

    def video_twitch(self, video_id: str) -> dict | None:
        """Dados oficiais de uma gravação (título, duração, miniatura). Precisa da conta conectada."""
        if not self.cfg["twitch"].get("access_token"):
            return None
        dados = self._helix("GET", "/videos", [("id", str(video_id))]).get("data") or []
        return dados[0] if dados else None

    # ------------------------------------------------------ clips

    def criar_clip(self, login: str, duracao: int = 30, titulo: str = "") -> dict:
        info = self.estado.get(f"twitch:{login}", {})
        if not info.get("online") or not info.get("id_canal"):
            raise ValueError("O canal precisa estar ao vivo para criar um clip.")
        parametros = [("broadcaster_id", info["id_canal"]), ("duration", str(max(5, min(int(duracao), 60))))]
        if titulo.strip():
            parametros.append(("title", titulo.strip()[:140]))
        try:
            d = self._helix("POST", "/clips", parametros)["data"][0]
        except ErroApi as e:
            motivos = {403: "Este canal não permite clips para sua conta (restrito a seguidores/inscritos, clips desativados ou conta com restrição).",
                       404: "O canal não está ao vivo.", 401: str(e)}
            raise ValueError(motivos.get(e.status, str(e))) from None
        clip = {"id": d["id"], "login": login, "id_canal": info["id_canal"], "edit_url": d.get("edit_url", ""), "criado": time.time(), "estado": "processando",
                "titulo": titulo.strip() or info.get("titulo", ""), "url": "", "thumb": "", "duracao": 0, "importado": ""}
        with self.trava:
            self.cfg["clips"].append(clip)
            self._salvar()
        return clip

    def _conferir_clips(self) -> None:
        pendentes = [c for c in self.cfg["clips"] if c["estado"] == "processando"]
        if not pendentes or not self.cfg["twitch"].get("access_token"):
            return
        try:
            achados = {d["id"]: d for d in self._helix("GET", "/clips", [("id", c["id"]) for c in pendentes[:100]]).get("data", [])}
        except ErroApi:
            return
        with self.trava:
            for c in pendentes:
                d = achados.get(c["id"])
                if d:
                    c.update(estado="pronto", url=d.get("url", ""), thumb=d.get("thumbnail_url", ""), duracao=d.get("duration", 0), titulo=d.get("title") or c["titulo"])
                elif time.time() - c["criado"] > PRAZO_CLIP:
                    c["estado"] = "falhou"
            self._salvar()

    def importar_clip(self, clip_id: str, tarefa=None) -> dict:
        """Só baixa pelo endpoint oficial, liberado à própria conta do canal e aos editores dele."""
        clip = next((c for c in self.cfg["clips"] if c["id"] == clip_id), None)
        if not clip:
            raise ValueError("Clip não encontrado.")
        tw = self.cfg["twitch"]
        try:
            r = self._helix("GET", "/clips/downloads", [("editor_id", tw.get("user_id", "")), ("broadcaster_id", clip["id_canal"]), ("clip_id", clip_id)])
        except ErroApi as e:
            if e.status in (401, 403):
                with self.trava:
                    clip["acesso"] = "so_link"
                    self._salvar()
                raise ValueError(f"Sem permissão para o arquivo: a Twitch só entrega o arquivo do clip ao dono do canal ({clip['login']}) "
                                 "e aos editores dele. O clip continua disponível pelo link. Se o criador te enviar o arquivo, "
                                 "use Importar arquivo autorizado.") from None
            raise ValueError(str(e)) from None
        link = ((r.get("data") or [{}])[0]).get("landscape_download_url")
        if not link:
            raise ValueError("A Twitch não devolveu um arquivo para este clip.")
        pasta = pasta_da_live(f"Clip_{clip['login']}_{clip_id}", "Twitch")
        (pasta / "cortes").mkdir(exist_ok=True)
        arquivo = pasta / "cortes" / "clip.mp4"
        if tarefa:
            tarefa.avancar(0.2, "Baixando o clip")
        with urllib.request.urlopen(urllib.request.Request(link, headers={"User-Agent": "ViceClips/1.0"}), timeout=60) as resp, arquivo.open("wb") as f:
            while bloco := resp.read(1 << 20):
                f.write(bloco)
        extrair_audio(str(arquivo), pasta / "audio.pcm")
        duracao = float(clip.get("duracao") or 30)
        gravar_json(pasta / "live.json", {"titulo": clip["titulo"] or f"Clip de {clip['login']}", "plataforma": "Twitch", "origem": str(arquivo), "streamer": clip["login"]})
        gravar_json(pasta / "cortes" / "cortes.json", [{"nota": 0, "inicio": 0, "fim": duracao, "pico": 0, "texto": clip["titulo"], "motivo": "Clip criado na Twitch.",
                                                         "arquivo": "clip.mp4", "momento_na_live": "00h00m00s", "desloc": 0}])
        with self.trava:
            clip["importado"] = f"Twitch/{pasta.name}/clip.mp4"
            clip["acesso"] = "arquivo"
            self._salvar()
        return {"corte": clip["importado"]}

    def anexar_clip(self, clip_id: str, corte_id: str) -> None:
        """Liga um arquivo autorizado (recebido do criador, por exemplo) ao clip criado na Twitch."""
        with self.trava:
            for c in self.cfg["clips"]:
                if c["id"] == clip_id:
                    c.update(importado=corte_id, acesso="arquivo")
            self._salvar()


canais = Canais()
