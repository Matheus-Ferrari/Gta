"""Lives ao vivo pelas APIs oficiais: status na Twitch e na Kick, clips, ranking dos canais ao vivo e avisos.

Ranking (nota de 0 a 100 entre os seus canais ao vivo): audiência, crescimento da audiência em ~10 min, mensagens por
minuto no chat e clipes criados nos últimos 30 min. Chat e clipes só existem na Twitch: a API oficial da Kick não entrega
nenhum dos dois, então a nota de um canal da Kick usa só audiência e crescimento (os pesos se redistribuem).
"""
from __future__ import annotations

import json
import math
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
from datetime import datetime, timezone
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
JANELA_HIST = 1800  # amostras de audiência guardadas (30 min)
CRESC_MIN = 480  # crescimento comparado com a amostra mais recente que tenha pelo menos 8 min (~10 min, com o ciclo de 45 s)
CLIPS_CADA, CLIPS_JANELA, CLIPS_RAJADA = 120, 1800, 600  # clipes da Twitch: contados a cada 2 min, dos últimos 30 min; rajada = últimos 10 min
PESOS = {"audiencia": 35, "crescimento": 20, "chat": 25, "clipes": 20}
RECARGA_AVISO = {"online": 0, "chat": 120, "clipes": 900, "subindo": 1200}  # o mesmo aviso para o mesmo canal no máximo a cada N s
SUBIU = 0.25  # aviso de audiência subindo: +25% em ~10 min


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


class Ritmo:
    """Mensagens do chat em baldes de 1 s: mede msgs/min sem guardar cada mensagem."""

    def __init__(self) -> None:
        self.baldes: deque[list] = deque()
        self.desde = time.time()

    def registrar(self, t: float) -> None:
        s = int(t)
        if self.baldes and self.baldes[-1][0] == s:
            self.baldes[-1][1] += 1
            return
        self.baldes.append([s, 1])
        while self.baldes[0][0] < s - 120:
            self.baldes.popleft()

    def por_minuto(self, agora: float) -> int | None:
        if agora - self.desde < 60:  # ainda não tem um minuto inteiro medido
            return None
        return sum(n for s, n in list(self.baldes) if s > agora - 60)


def _ts(texto: str) -> float:
    try:
        return datetime.fromisoformat(str(texto).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class Canais:
    def __init__(self) -> None:
        self.trava = threading.RLock()
        self.cfg: dict = ler_json(ARQ, {}) or {}
        self.cfg.setdefault("twitch", {})
        self.cfg.setdefault("kick", {})
        self.cfg.setdefault("canais", [])
        self.cfg.setdefault("clips", [])
        self.estado: dict[str, dict] = {}
        self.avisos: deque[dict] = deque(maxlen=40)
        self.ultimo_aviso: dict[tuple, float] = {}
        self.historico: dict[str, deque] = {}  # "plataforma:login" -> (quando, espectadores) enquanto está ao vivo
        self.ritmos: dict[str, Ritmo] = {}  # login da Twitch -> mensagens do chat
        self.clips_vivo: dict[str, dict] = {}  # login da Twitch -> clipes dos últimos 30 min
        self.ultimo_clips = 0.0
        self.ouvintes: dict = {}  # login da Twitch -> função(t, texto): a gravação ao vivo escuta o chat deste canal
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
                self.cfg["canais"].append({"plataforma": plataforma, "login": login})
                self._salvar()
        threading.Thread(target=self.atualizar, daemon=True).start()

    def remover(self, plataforma: str, login: str) -> None:
        with self.trava:
            self.cfg["canais"] = [c for c in self.cfg["canais"] if not (c["plataforma"] == plataforma and c["login"] == login)]
            self._salvar()
        self.estado.pop(f"{plataforma}:{login}", None)
        self.historico.pop(f"{plataforma}:{login}", None)

    # ------------------------------------------------------ status, histórico de audiência e avisos

    def _avisar(self, tipo: str, plataforma: str, login: str, texto: str) -> None:
        agora = time.time()
        chave = (tipo, plataforma, login)
        if agora - self.ultimo_aviso.get(chave, 0) < RECARGA_AVISO.get(tipo, 600):
            return
        self.ultimo_aviso[chave] = agora
        self.avisos.append({"tipo": tipo, "plataforma": plataforma, "login": login, "quando": agora, "texto": texto})

    def _gravar_estado(self, plataforma: str, login: str, novo: dict) -> None:
        """Guarda o status, a amostra de audiência e avisa quando um canal que estava fora do ar entra ao vivo."""
        chave = f"{plataforma}:{login}"
        antes = self.estado.get(chave) or {}
        self.estado[chave] = novo
        if not novo.get("online"):
            self.historico.pop(chave, None)
            return
        agora = time.time()
        h = self.historico.setdefault(chave, deque())
        h.append((agora, int(novo.get("espectadores") or 0)))
        while h[0][0] < agora - JANELA_HIST:
            h.popleft()
        if antes.get("online") is False:  # só a virada fora do ar -> ao vivo; ao abrir o painel não avisa quem já estava ao vivo
            self._avisar("online", plataforma, login, "entrou ao vivo" + (f" · {novo['jogo']}" if novo.get("jogo") else ""))

    def _crescimento(self, chave: str) -> tuple[float, int, int] | None:
        """Variação da audiência em ~10 min: (fração, antes, agora). None enquanto não há amostra antiga o bastante."""
        h = list(self.historico.get(chave) or ())
        if len(h) < 2:
            return None
        t2, v2 = h[-1]
        base = [(t, v) for t, v in h if t2 - t >= CRESC_MIN]
        if not base:
            return None
        v1 = base[-1][1]
        return (v2 - v1) / max(v1, 1), v1, v2

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
            self._gravar_estado("twitch", l, {"online": False} if not s else {
                "online": True, "titulo": s.get("title", ""), "jogo": s.get("game_name", ""), "espectadores": s.get("viewer_count", 0),
                "inicio": s.get("started_at", ""), "id_canal": s.get("user_id"), "nome": s.get("user_name", l),
                "thumb": s.get("thumbnail_url", "").replace("{width}", "480").replace("{height}", "270")})

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
                self._gravar_estado("kick", l, {"online": bool(s.get("is_live")), "titulo": c.get("stream_title", ""), "jogo": (c.get("category") or {}).get("name", ""),
                                                "espectadores": s.get("viewer_count", 0), "inicio": s.get("start_time", ""), "thumb": s.get("thumbnail", "")})

    def atualizar(self) -> None:
        canais = list(self.cfg["canais"])
        for plataforma, funcao in (("twitch", self._status_twitch), ("kick", self._status_kick)):
            logins = [c["login"] for c in canais if c["plataforma"] == plataforma]
            try:
                funcao(logins)
            except (ErroApi, KeyError) as e:
                for l in logins:
                    self.estado[f"{plataforma}:{l}"] = {"online": None, "erro": str(e)}
        for c in canais:
            chave = f"{c['plataforma']}:{c['login']}"
            g = self._crescimento(chave) if self.estado.get(chave, {}).get("online") else None
            if g and g[0] >= SUBIU and g[2] >= 100:
                self._avisar("subindo", c["plataforma"], c["login"], f"audiência subiu {g[0]:.0%} em ~10 min ({g[1]} → {g[2]})")
        self._ajustar_chats()
        self._contar_clips()
        self._conferir_clips()

    def _contar_clips(self) -> None:
        """Clipes que o público criou nos últimos 30 min de cada canal da Twitch ao vivo (a Kick não tem clipes na API oficial)."""
        agora = time.time()
        if agora - self.ultimo_clips < CLIPS_CADA or not self.cfg["twitch"].get("access_token"):
            return
        self.ultimo_clips = agora
        for c in list(self.cfg["canais"]):
            if c["plataforma"] != "twitch":
                continue
            info = self.estado.get(f"twitch:{c['login']}", {})
            if not info.get("online") or not info.get("id_canal"):
                self.clips_vivo.pop(c["login"], None)
                continue
            desde = max(agora - CLIPS_JANELA, _ts(info.get("inicio", "")))  # só clipes desta live
            try:
                dados = self._helix("GET", "/clips", [("broadcaster_id", info["id_canal"]), ("first", "100"),
                                                      ("started_at", datetime.fromtimestamp(desde, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))]).get("data") or []
            except ErroApi:
                continue
            rajada = sum(1 for d in dados if _ts(d.get("created_at", "")) >= agora - CLIPS_RAJADA)
            self.clips_vivo[c["login"]] = {"total": len(dados), "views": sum(int(d.get("view_count") or 0) for d in dados), "rajada": rajada, "visto": agora}
            if rajada >= 3:
                self._avisar("clipes", "twitch", c["login"], f"{rajada} clipes criados nos últimos 10 min")

    def _laco(self) -> None:
        while True:
            self.atualizar()
            for _ in range(INTERVALO):
                time.sleep(1)
                if any(c.get("estado") == "processando" for c in self.cfg["clips"]) and _ % 5 == 4:
                    self._conferir_clips()

    def _metricas(self, c: dict, agora: float) -> dict:
        """Números do canal ao vivo. None = não medido (ainda medindo, ou a plataforma não entrega)."""
        if not c.get("online"):
            return c
        g = self._crescimento(f"{c['plataforma']}:{c['login']}")
        c["crescimento"] = round(g[0] * 100) if g else None
        c["chat_min"] = c["clipes_30"] = None
        if c["plataforma"] == "twitch":
            r = self.ritmos.get(c["login"])
            c["chat_min"] = r.por_minuto(agora) if r else None
            cl = self.clips_vivo.get(c["login"])
            if cl:
                c["clipes_30"], c["clipes_views"] = cl["total"], cl["views"]
        return c

    def _ranking(self, canais: list[dict]) -> list[dict]:
        """Nota de 0 a 100 entre os canais ao vivo. Cada métrica vale em relação ao maior valor da lista agora;
        métrica que a plataforma não entrega (chat e clipes na Kick) sai da conta e os pesos se redistribuem."""
        vivos = [c for c in canais if c.get("online")]
        maior = {k: max((c.get(k) or 0 for c in vivos), default=0) for k in ("espectadores", "chat_min", "clipes_30")}
        for c in vivos:
            partes = {"audiencia": math.log10((c.get("espectadores") or 0) + 1) / math.log10(maior["espectadores"] + 1) if maior["espectadores"] else 0.0}
            if c.get("crescimento") is not None:
                partes["crescimento"] = min(max(c["crescimento"] / 30, 0.0), 1.0)  # +30% em ~10 min já vale o máximo
            if c.get("chat_min") is not None:
                partes["chat"] = math.log10(c["chat_min"] + 1) / math.log10(maior["chat_min"] + 1) if maior["chat_min"] else 0.0
            if c.get("clipes_30") is not None:
                partes["clipes"] = c["clipes_30"] / maior["clipes_30"] if maior["clipes_30"] else 0.0
            c["nota"] = round(100 * sum(PESOS[k] * v for k, v in partes.items()) / sum(PESOS[k] for k in partes))
            c["nota_com"] = list(partes)
        return sorted(vivos, key=lambda c: (-c["nota"], -(c.get("espectadores") or 0)))[:5]

    def listar(self) -> dict:
        agora = time.time()
        canais = [self._metricas({**c, **self.estado.get(f"{c['plataforma']}:{c['login']}", {"online": None})}, agora) for c in self.cfg["canais"]]
        top = self._ranking(canais)
        eu = self.cfg["twitch"].get("login", "").lower()
        clips = [{**c, "meu_canal": c.get("login", "").lower() == eu} for c in reversed(self.cfg["clips"][-30:])]
        return {"canais": canais, "top": [{"plataforma": c["plataforma"], "login": c["login"]} for c in top], "clips": clips,
                "avisos": list(reversed(self.avisos)), "agora": agora}

    # ------------------------------------------------------ chat da Twitch (somente leitura)

    def _ajustar_chats(self) -> None:
        """Lê o chat de todo canal da Twitch ao vivo da lista: mede msgs/min para o ranking e avisa quando o chat explode."""
        querem = {c["login"] for c in self.cfg["canais"] if c["plataforma"] == "twitch" and self.estado.get(f"twitch:{c['login']}", {}).get("online")}
        querem |= set(self.ouvintes)  # a live que está sendo gravada, mesmo fora da lista
        if not self.cfg["twitch"].get("login"):
            querem = set()
        with self.trava:  # chamado pelo laço e pela gravação: não abre duas leituras do mesmo chat
            for login, parar in list(self.chats.items()):
                if login not in querem:
                    parar.set()
                    del self.chats[login]
                    self.ritmos.pop(login, None)
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
                ritmo = self.ritmos[login] = Ritmo()  # reconectou: recomeça a medir, sem misturar com o buraco da queda
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
                            agora = time.time()
                            ritmo.registrar(agora)
                            texto = linha.split(" :", 1)[-1]
                            ouvinte = self.ouvintes.get(login)
                            if ouvinte:
                                ouvinte(agora, texto)
                            achado = detector.registrar(agora, texto)
                            if achado and any(c["plataforma"] == "twitch" and c["login"] == login for c in self.cfg["canais"]):
                                self._avisar("chat", "twitch", login, achado["motivo"])
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
