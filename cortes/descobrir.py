"""Descobrir: lives ao vivo, clipes em alta, criadores favoritos e monitoramento, pela API oficial da Twitch (Helix).

Nada é baixado sozinho. Importar um clipe usa o endpoint oficial /clips/downloads, liberado só ao dono do canal
e aos editores dele; sem permissão o clipe fica como "Só link". O crescimento dos clipes vem de amostras reais
de visualizações guardadas com horário: com uma amostra só, não há métrica.

Ritmo dos pedidos: listas em cache por 2 min, status a cada 90 s, clipes das lives monitoradas a cada 2 min e
reamostragem a cada 10 min. Os cabeçalhos Ratelimit-* da Twitch freiam tudo quando o balde de pontos fica baixo.
"""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import unicodedata
import urllib.parse
import uuid
from datetime import datetime, timezone

from . import canais as canais_mod
from .ao_vivo import analisador, captura
from .canais import ErroApi, canais
from .config import DADOS, gravar_json, ler_json
from .tarefas import fila

PASTA = DADOS / "descobrir"
ARQ_PREFS, ARQ_CRIADORES, ARQ_AMOSTRAS = PASTA / "preferencias.json", PASTA / "criadores.json", PASTA / "amostras.json"
ARQ_MONITOR, ARQ_EVENTOS, ARQ_ESTADO = PASTA / "monitor.json", PASTA / "eventos.json", PASTA / "estado.json"

CATEGORIA_PADRAO = "Grand Theft Auto VI"
CRIADORES_INICIAIS = ("Paulinho o Loko", "Bistecone", "Alanzoka", "Coringa")
PLATAFORMAS = ("twitch", "kick", "youtube", "outra")
INTERVALOS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600, "7d": 7 * 86400}
CACHE_LISTA, MIN_FORCAR = 120, 30  # no máximo um pedido real a cada 2 min por lista; "Atualizar agora" espera 30 s
STATUS_CADA, MONITOR_CADA, AMOSTRA_CADA = 90, 120, 600
DIST_MIN, ESPACO_AMOSTRA, MAX_AMOSTRAS = 600, 120, 24  # crescimento só entre amostras a 10 min ou mais
IDADE_AMOSTRA, MAX_CLIPS_AMOSTRA = 7 * 86400, 3000
MAX_MONITOR, MAX_FILA, MAX_VISTOS, MAX_EVENTOS = 5, 400, 5000, 500
RESERVA_FUNDO, RESERVA_TELA = 100, 10  # pontos do balde da Twitch guardados antes de recuar
RE_RP_TAG = re.compile(r"^(gta)?rp(br|pt|pc)?$|roleplay", re.I)
RE_RP_TITULO = re.compile(r"\b(gta\s?)?rp\b|role\s?-?play", re.I)


def _rfc(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(texto: str) -> float:
    try:
        return datetime.fromisoformat(str(texto).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _hms_twitch(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 3600}h{s % 3600 // 60}m{s % 60}s"


def _ts(texto: str) -> float:
    try:
        return datetime.fromisoformat(str(texto).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _slug(nome: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower())


def _q(consulta: dict, nome: str, padrao: str = "") -> str:
    return str((consulta.get(nome) or [padrao])[0]).strip()


def _novo_id() -> str:
    return "c" + uuid.uuid4().hex[:8]


def _gravar_compacto(caminho, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temp = caminho.with_name(caminho.name + ".tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(caminho)


def _motivo_rp(s: dict) -> str:
    tag = next((t for t in s.get("tags") or [] if RE_RP_TAG.search(t)), None)
    if tag:
        return f"tag {tag}"
    return "título" if RE_RP_TITULO.search(s.get("title") or "") else ""


def _live(s: dict, rp: str = "") -> dict:
    return {"user_id": s["user_id"], "login": s.get("user_login", ""), "nome": s.get("user_name", ""), "titulo": s.get("title", ""),
            "espectadores": int(s.get("viewer_count") or 0), "inicio": s.get("started_at", ""), "idioma": s.get("language", ""),
            "tags": s.get("tags") or [], "jogo": s.get("game_name", ""), "rp": rp, "link": f"https://www.twitch.tv/{s.get('user_login', '')}",
            "thumb": (s.get("thumbnail_url") or "").replace("{width}", "640").replace("{height}", "360")}


def _clip(d: dict) -> dict:
    return {"id": d["id"], "url": d.get("url", ""), "canal_id": d.get("broadcaster_id", ""), "canal": d.get("broadcaster_name", ""),
            "autor": d.get("creator_name", ""), "autor_id": d.get("creator_id", ""), "titulo": d.get("title", ""), "views": int(d.get("view_count") or 0),
            "criado": d.get("created_at", ""), "thumb": d.get("thumbnail_url", ""), "duracao": float(d.get("duration") or 0),
            "idioma": d.get("language", ""), "video_id": d.get("video_id", ""), "vod_offset": d.get("vod_offset"),
            "destaque": bool(d.get("is_featured"))}


def _limite() -> dict:
    l = canais_mod.LIMITE
    return {k: l.get(k) for k in ("restante", "limite", "reset", "visto")}


def _espera_limite(reserva: int) -> float:
    l = canais_mod.LIMITE
    if l.get("restante") is not None and l["restante"] < reserva and l.get("reset", 0) > time.time():
        return l["reset"] - time.time()
    return 0.0


class Descobrir:
    def __init__(self) -> None:
        self.trava = threading.RLock()
        self.cache: dict[str, tuple[float, object]] = {}
        self.acompanhadas: dict[str, dict] = {}  # consultas de clipes abertas na tela: continuam sendo amostradas
        self.acordar = threading.Event()
        self.iniciado = False
        self.ultimo = {"status": 0.0, "monitor": 0.0, "amostra": 0.0}
        self.erro_fundo, self.recuo, self.sujo = "", 0.0, False
        self.mon: dict[str, dict] = {}
        p = ler_json(ARQ_PREFS, None)
        self.prefs = p if isinstance(p, dict) else {}
        self.prefs.setdefault("categorias", [{"id": "", "nome": CATEGORIA_PADRAO}, {"id": "", "nome": "Grand Theft Auto V"}])
        if not any(c.get("nome") == CATEGORIA_PADRAO for c in self.prefs["categorias"]):  # quem já usava só GTA V passa a abrir no GTA VI
            self.prefs["categorias"].insert(0, {"id": "", "nome": CATEGORIA_PADRAO})
            self.prefs["atual"] = ""
        for k, v in (("atual", ""), ("rp", False), ("idioma", "")):
            self.prefs.setdefault(k, v)
        c = ler_json(ARQ_CRIADORES, None)  # lista inicial: só nomes, sem conta nem plataforma presumida
        self.criadores = c if isinstance(c, list) else [{"id": _novo_id(), "nome": n, "contas": [], "criado": time.time()} for n in CRIADORES_INICIAIS]
        self.amostras: dict[str, list] = ler_json(ARQ_AMOSTRAS, {}) or {}
        m = ler_json(ARQ_MONITOR, {}) or {}
        self.monitor = {"canais": m.get("canais", []), "vistos": m.get("vistos", []), "fila": m.get("fila", [])}
        self.vistos = dict.fromkeys(self.monitor["vistos"])  # ids já vistos, na ordem em que apareceram
        self.eventos: list[dict] = ler_json(ARQ_EVENTOS, []) or []
        self.status: dict[str, dict] = ler_json(ARQ_ESTADO, {}) or {}
        self.gravacoes: dict[str, dict | None] = {}  # video_id -> início da gravação (para saber o momento real de cada clipe)

    # ------------------------------------------------------ base

    def iniciar(self) -> None:
        if not self.iniciado:
            self.iniciado = True
            if not ARQ_CRIADORES.exists():  # grava a lista inicial para os ids não mudarem entre aberturas
                try:
                    self._salvar("criadores")
                except OSError:
                    pass
            threading.Thread(target=self._laco, daemon=True).start()
            self.acordar.set()

    def _salvar(self, *quais: str) -> None:
        with self.trava:
            if "prefs" in quais:
                gravar_json(ARQ_PREFS, self.prefs)
            if "criadores" in quais:
                gravar_json(ARQ_CRIADORES, self.criadores)
            if "monitor" in quais:
                self.monitor["vistos"] = list(self.vistos)[-MAX_VISTOS:]
                self.vistos = dict.fromkeys(self.monitor["vistos"])
                _gravar_compacto(ARQ_MONITOR, self.monitor)
            if "eventos" in quais:
                del self.eventos[:-MAX_EVENTOS]
                gravar_json(ARQ_EVENTOS, self.eventos)
            if "estado" in quais:
                _gravar_compacto(ARQ_ESTADO, self.status)
            if "amostras" in quais:
                agora = time.time()
                for k in [k for k, v in self.amostras.items() if not v or agora - v[-1][0] > IDADE_AMOSTRA]:
                    del self.amostras[k]
                if len(self.amostras) > MAX_CLIPS_AMOSTRA:
                    for k, _ in sorted(self.amostras.items(), key=lambda kv: kv[1][-1][0])[:len(self.amostras) - MAX_CLIPS_AMOSTRA]:
                        del self.amostras[k]
                _gravar_compacto(ARQ_AMOSTRAS, self.amostras)
                self.sujo = False

    def _tw(self, caminho: str, parametros: list | None = None, reserva: int = RESERVA_TELA) -> dict:
        """GET na Helix com freio: recua quando os pontos do balde ficam abaixo da reserva."""
        espera = _espera_limite(reserva)
        if espera:
            raise ValueError(f"A Twitch está perto do limite de pedidos deste app. Nova tentativa em {int(espera) + 1} s.")
        try:
            return canais._helix("GET", caminho, parametros)
        except ErroApi as e:
            if e.status == 429:
                raise ValueError("A Twitch pediu uma pausa (limite de pedidos). Tente de novo em 1 minuto.") from None
            raise ValueError(str(e)) from None

    def _cache(self, chave: str, ttl: float, buscar, forcar: bool = False):
        agora = time.time()
        item = self.cache.get(chave)
        if item and agora - item[0] < (MIN_FORCAR if forcar else ttl):
            return item
        dados = buscar()
        with self.trava:
            self.cache[chave] = (agora, dados)
            for k in [k for k, (t, _) in self.cache.items() if agora - t > 6 * 3600]:
                del self.cache[k]
        return agora, dados

    def _kick_ok(self) -> bool:
        kk = canais.cfg["kick"]
        return bool(kk.get("client_id") and kk.get("client_secret"))

    def _kick(self, slugs: list[str]) -> list[dict]:
        url = f"{canais_mod.KICK_API}/channels?" + urllib.parse.urlencode([("slug", s) for s in slugs[:50]])
        try:
            return canais._kick_get(url).get("data") or []
        except ErroApi as e:
            raise ValueError(f"Kick: {e}") from None

    def estado(self, _=None) -> dict:
        tw = canais.cfg["twitch"]
        return {"twitch": {"client_id": bool(tw.get("client_id")), "conectado": bool(tw.get("access_token")), "login": tw.get("login", "")},
                "kick": {"configurado": self._kick_ok()}, "limite": _limite(), "agora": time.time(),
                "categorias": self.prefs["categorias"], "atual": self.prefs.get("atual", ""), "rp": self.prefs.get("rp"),
                "idioma": self.prefs.get("idioma", ""), "fundo": {**self.ultimo, "erro": self.erro_fundo, "recuo": self.recuo},
                "ritmo": {"lista": CACHE_LISTA, "status": STATUS_CADA, "monitor": MONITOR_CADA, "amostra": AMOSTRA_CADA, "dist_min": DIST_MIN}}

    # ------------------------------------------------------ categorias e lives

    def _categoria(self, valor: str) -> dict:
        """Aceita id ou nome. O id sempre vem de GET /games."""
        valor = valor.strip()[:100] or CATEGORIA_PADRAO
        for c in self.prefs["categorias"]:
            if c.get("id") and (valor == c["id"] or valor.lower() == c["nome"].lower()):
                return c
        parametros = [("id", valor)] if valor.isdigit() else [("name", valor)]
        _, dados = self._cache(f"jogo:{valor.lower()}", 86400, lambda: self._tw("/games", parametros).get("data") or [])
        if not dados:
            raise ValueError(f"A categoria “{valor}” não existe na Twitch com esse nome exato. Use a busca de categorias.")
        g = dados[0]
        cat = {"id": g["id"], "nome": g["name"], "capa": (g.get("box_art_url") or "").replace("{width}", "52").replace("{height}", "70")}
        with self.trava:
            for c in self.prefs["categorias"]:
                if not c.get("id") and c["nome"].lower() == cat["nome"].lower():
                    c.update(cat)
                    self._salvar("prefs")
        return cat

    def buscar_categorias(self, consulta: dict) -> list[dict]:
        termo = _q(consulta, "q")[:60]
        if len(termo) < 2:
            return []
        _, dados = self._cache(f"buscacat:{termo.lower()}", 600, lambda: self._tw("/search/categories", [("query", termo), ("first", "8")]).get("data") or [])
        return [{"id": g["id"], "nome": g["name"], "capa": g.get("box_art_url", "")} for g in dados]

    def categorias(self, d: dict) -> dict:
        acao = d.get("acao")
        with self.trava:
            if acao == "remover":
                self.prefs["categorias"] = [c for c in self.prefs["categorias"] if c.get("id") != str(d.get("id")) and c["nome"] != str(d.get("id"))]
            elif acao == "salvar":
                cat = self._categoria(str(d.get("id") or d.get("nome") or ""))
                if not any(c.get("id") == cat["id"] for c in self.prefs["categorias"]):
                    self.prefs["categorias"].append(cat)
            else:
                raise ValueError("Ação inválida.")
            self._salvar("prefs")
        return {"categorias": self.prefs["categorias"]}

    def lives(self, consulta: dict) -> dict:
        cat = self._categoria(_q(consulta, "categoria") or self.prefs.get("atual") or CATEGORIA_PADRAO)
        rp, idioma, forcar = _q(consulta, "rp") == "1", _q(consulta, "idioma").lower(), _q(consulta, "forcar") == "1"
        if idioma and not re.fullmatch(r"[a-z]{2}|other", idioma):
            raise ValueError("Idioma inválido.")

        def buscar() -> dict:
            achadas, vistas, cursor = [], 0, None
            for _ in range(3 if rp else 1):  # GTA RP: a Helix não filtra por tag, então olha até 300 lives e filtra aqui
                p = [("game_id", cat["id"]), ("type", "live"), ("first", "100")] + ([("language", idioma)] if idioma else [])
                r = self._tw("/streams", p + ([("after", cursor)] if cursor else []))
                for s in r.get("data") or []:
                    vistas += 1
                    motivo = _motivo_rp(s) if rp else ""
                    if not rp or motivo:
                        achadas.append(_live(s, motivo))
                cursor = (r.get("pagination") or {}).get("cursor")
                if len(achadas) >= 5 or not cursor:
                    break
            return {"lives": achadas[:5], "analisadas": vistas}

        quando, dados = self._cache(f"lives:{cat['id']}:{int(rp)}:{idioma}", CACHE_LISTA, buscar, forcar)
        with self.trava:
            if (self.prefs.get("atual"), self.prefs.get("rp"), self.prefs.get("idioma")) != (cat["id"], rp, idioma):
                self.prefs.update(atual=cat["id"], rp=rp, idioma=idioma)
                self._salvar("prefs")
        favs, mons = self._ids_favoritos(), {m["user_id"] for m in self.monitor["canais"]}
        return {"categoria": cat, "salva": any(c.get("id") == cat["id"] for c in self.prefs["categorias"]), "rp": rp, "idioma": idioma,
                "lives": [{**l, "favorito": l["user_id"] in favs, "monitorado": l["user_id"] in mons} for l in dados["lives"]],
                "analisadas": dados["analisadas"], "atualizado": quando, "proxima": quando + CACHE_LISTA, "agora": time.time(), "limite": _limite()}

    # ------------------------------------------------------ clipes e amostras

    def _buscar_clips(self, alvos: list[tuple], segundos: int, paginas: int, reserva: int = RESERVA_TELA) -> list[dict]:
        agora = time.time()
        achados: dict[str, dict] = {}
        for alvo in alvos:
            cursor = None
            for _ in range(paginas):  # a Twitch devolve do mais visto para o menos visto
                p = [alvo, ("started_at", _rfc(agora - segundos)), ("ended_at", _rfc(agora)), ("first", "100")]
                r = self._tw("/clips", p + ([("after", cursor)] if cursor else []), reserva)
                for d in r.get("data") or []:
                    achados[d["id"]] = _clip(d)
                cursor = (r.get("pagination") or {}).get("cursor")
                if not cursor:
                    break
        self._amostrar(achados.values(), agora)
        return sorted(achados.values(), key=lambda c: -c["views"])

    def _amostrar(self, clips, agora: float) -> None:
        with self.trava:
            for c in clips:
                lista = self.amostras.setdefault(c["id"], [])
                if not lista or agora - lista[-1][0] >= ESPACO_AMOSTRA:
                    lista.append([int(agora), int(c["views"])])
                    del lista[:-MAX_AMOSTRAS]
                    self.sujo = True

    def _crescimento(self, cid: str) -> dict:
        am = self.amostras.get(cid) or []
        if len(am) < 2:
            return {"estado": "aguardando", "texto": "Aguardando segunda amostra", "amostras": len(am)}
        t2, v2 = am[-1]
        base = next(((t, v) for t, v in reversed(am[:-1]) if t2 - t >= DIST_MIN), None)
        if base is None:
            falta = max(1, round((DIST_MIN - (t2 - am[0][0])) / 60))
            return {"estado": "aguardando", "texto": f"Aguardando amostra a 10 min da primeira (faltam ~{falta} min)", "amostras": len(am)}
        t1, v1 = base
        return {"estado": "ok", "por_hora": round((v2 - v1) * 3600 / (t2 - t1), 1), "ganho": v2 - v1, "minutos": round((t2 - t1) / 60),
                "amostras": len(am), "ultima": t2}

    def _carregar_gravacoes(self, ids: list[str]) -> None:
        faltam = list(dict.fromkeys(i for i in ids if i and i not in self.gravacoes))[:300]
        for k in range(0, len(faltam), 100):
            lote = faltam[k:k + 100]
            try:
                achados = {d["id"]: d for d in self._tw("/videos", [("id", i) for i in lote]).get("data") or []}
            except ValueError:
                return
            for i in lote:
                d = achados.get(i)
                self.gravacoes[i] = {"inicio": _ts(d.get("created_at", "")), "titulo": d.get("title", "")} if d else None

    def _momento(self, c: dict) -> dict:
        """Clipe pode ser feito ao vivo ou depois, assistindo à gravação: o momento real vem da gravação + vod_offset."""
        g = self.gravacoes.get(c.get("video_id") or "")
        if not g or c.get("vod_offset") is None:
            return {}
        momento = g["inicio"] + float(c["vod_offset"])
        feito = _ts(c.get("criado", ""))
        return {"momento": momento, "vod_offset": c["vod_offset"], "ao_vivo": bool(feito) and feito - (momento + c["duracao"]) < 600,
                "vod_link": f"https://www.twitch.tv/videos/{c['video_id']}?t={_hms_twitch(c['vod_offset'])}",
                "vod_url": f"https://www.twitch.tv/videos/{c['video_id']}", "vod_titulo": g["titulo"]}

    def _enfeitar(self, clips: list[dict]) -> list[dict]:
        registro = {c["id"]: c for c in canais.cfg["clips"]}
        self._carregar_gravacoes([c.get("video_id") for c in clips[:300]])
        saida = []
        for c in clips:
            r = registro.get(c["id"]) or {}
            saida.append({**c, **self._momento(c), "crescimento": self._crescimento(c["id"]),
                          "registro": {"acesso": r.get("acesso", ""), "importado": r.get("importado", "")} if r else None})
        return saida

    def clips(self, consulta: dict) -> dict:
        intervalo, origem, forcar = _q(consulta, "intervalo", "24h"), _q(consulta, "origem", "categoria"), _q(consulta, "forcar") == "1"
        idioma = _q(consulta, "idioma").lower() if _q(consulta, "origem", "categoria") == "categoria" else ""
        if idioma and not re.fullmatch(r"[a-z]{2}|other", idioma):
            raise ValueError("Idioma inválido.")
        if intervalo not in INTERVALOS:
            raise ValueError("Intervalo inválido. Use 1h, 6h, 24h ou 7d.")
        paginas = 1
        if origem == "criador":
            cri = self._achar(_q(consulta, "criador"))
            contas = [k for k in cri["contas"] if k["plataforma"] == "twitch" and k.get("id")]
            if not contas:
                raise ValueError(f"{cri['nome']} não tem conta da Twitch associada. Em Favoritos, use Buscar IDs.")
            alvos, titulo = [("broadcaster_id", k["id"]) for k in contas[:3]], f"{cri['nome']} ({', '.join(k['login'] for k in contas[:3])})"
        elif origem == "canal":
            canal = _q(consulta, "canal")
            if not canal.isdigit():
                raise ValueError("Canal inválido.")
            alvos, titulo = [("broadcaster_id", canal)], _q(consulta, "nome") or canal
        else:
            cat = self._categoria(_q(consulta, "categoria") or self.prefs.get("atual") or CATEGORIA_PADRAO)
            alvos, titulo, paginas = [("game_id", cat["id"])], f"Categoria {cat['nome']}", 5 if idioma else 2
        chave = f"clips:{'|'.join(f'{a}={b}' for a, b in alvos)}:{intervalo}:{paginas}"
        quando, lista = self._cache(chave, CACHE_LISTA, lambda: self._buscar_clips(alvos, INTERVALOS[intervalo], paginas), forcar)
        with self.trava:
            self.acompanhadas[chave] = {"alvos": alvos, "segundos": INTERVALOS[intervalo], "paginas": paginas, "visto": time.time()}
        total = len(lista)
        if idioma:  # a Twitch não filtra clipes por idioma: o filtro é feito aqui, sobre os mais vistos
            lista = [c for c in lista if (c.get("idioma") or "").lower().startswith(idioma)]
            titulo += f" · idioma {idioma.upper()} ({len(lista)} de {total})"
        return {"clips": self._enfeitar(lista), "titulo": titulo, "intervalo": intervalo, "origem": origem, "limite_paginas": paginas * 100, "idioma": idioma,
                "atualizado": quando, "proxima": quando + CACHE_LISTA, "agora": time.time(), "limite": _limite()}

    # ------------------------------------------------------ criadores favoritos

    def _achar(self, ident) -> dict:
        cri = next((c for c in self.criadores if c["id"] == str(ident or "")), None)
        if not cri:
            raise ValueError("Criador não encontrado.")
        return cri

    def _ids_favoritos(self) -> set[str]:
        return {k["id"] for c in self.criadores for k in c["contas"] if k["plataforma"] == "twitch" and k.get("id")}

    def _chave_status(self, k: dict) -> str:
        return f"{k['plataforma']}:{k.get('id') if k['plataforma'] == 'twitch' else k.get('login')}"

    def criadores_listar(self, _=None) -> dict:
        saida = []
        for c in self.criadores:
            contas = [{**k, "status": self.status.get(self._chave_status(k))} for k in c["contas"]]
            saida.append({**c, "contas": contas, "ao_vivo": any((k["status"] or {}).get("online") for k in contas)})
        return {"criadores": saida, "eventos": self.eventos[::-1][:300], "kick": self._kick_ok(), "atualizado": self.ultimo["status"],
                "monitorados": [m["user_id"] for m in self.monitor["canais"]], "agora": time.time()}

    def criador_salvar(self, d: dict) -> dict:
        nome = re.sub(r"\s+", " ", str(d.get("nome") or "")).strip()[:60]
        if not nome:
            raise ValueError("Informe o nome do criador.")
        with self.trava:
            if any(c["nome"].lower() == nome.lower() and c["id"] != d.get("id") for c in self.criadores):
                raise ValueError("Já existe um criador com esse nome.")
            if d.get("id"):
                cri = self._achar(d["id"])
                cri["nome"] = nome
            else:
                cri = {"id": _novo_id(), "nome": nome, "contas": [], "criado": time.time()}
                self.criadores.append(cri)
            self._salvar("criadores")
        return cri

    def criador_remover(self, d: dict) -> dict:
        with self.trava:
            cri = self._achar(d.get("id"))
            self.criadores.remove(cri)
            self._salvar("criadores")
        return {"ok": True}

    def _usuario_twitch(self, ident: str = "", login: str = "") -> dict:
        if ident and not ident.isdigit() or not ident and not re.fullmatch(r"[a-z0-9_]{2,25}", login):
            raise ValueError("Informe o login da Twitch (só letras, números e _).")
        dados = self._tw("/users", [("id", ident)] if ident else [("login", login)]).get("data") or []
        if not dados:
            raise ValueError(f"A Twitch não encontrou a conta “{login or ident}”.")
        u = dados[0]
        return {"plataforma": "twitch", "id": u["id"], "login": u["login"], "nome": u["display_name"], "foto": u.get("profile_image_url", ""),
                "verificado": True, "fonte": "GET /users"}

    def _resolver_conta(self, d: dict) -> dict:
        plataforma = str(d.get("plataforma") or "").lower()
        if plataforma not in PLATAFORMAS:
            raise ValueError("Plataforma inválida.")
        bruto = str(d.get("login") or "").strip()
        login = re.sub(r"^https?://(www\.)?(twitch\.tv|kick\.com|youtube\.com)/", "", bruto, flags=re.I).strip("/ ").split("/")[0][:60]
        ident = str(d.get("id") or "").strip()[:60]
        if plataforma == "twitch":
            return self._usuario_twitch(ident if ident.isdigit() else "", login.lower().lstrip("@"))
        if plataforma == "kick":
            login = login.lower().lstrip("@")
            if not re.fullmatch(r"[a-z0-9_-]{2,25}", login):
                raise ValueError("Informe o canal da Kick (o nome que aparece em kick.com/nome).")
            if self._kick_ok():
                c = next((c for c in self._kick([login]) if str(c.get("slug", "")).lower() == login), None)
                if not c:
                    raise ValueError(f"A Kick não encontrou o canal “{login}”.")
                return {"plataforma": "kick", "id": str(c.get("broadcaster_user_id", "")), "login": c["slug"], "nome": c["slug"],
                        "verificado": True, "fonte": "Kick GET /channels"}
            return {"plataforma": "kick", "id": "", "login": login, "nome": login, "verificado": False,
                    "nota": "ID não verificado (Kick sem credenciais)"}
        if not (login or ident):
            raise ValueError("Informe o canal ou o ID.")
        return {"plataforma": plataforma, "id": ident, "login": login or ident, "nome": login or ident, "verificado": False,
                "nota": "Sem integração com a API desta plataforma: dados guardados como você digitou."}

    def conta_adicionar(self, d: dict) -> dict:
        conta = self._resolver_conta(d)
        with self.trava:
            cri = self._achar(d.get("criador"))
            if any(k["plataforma"] == conta["plataforma"] and (k.get("id") or k["login"]) == (conta.get("id") or conta["login"]) for k in cri["contas"]):
                raise ValueError("Essa conta já está associada.")
            if len(cri["contas"]) >= 8:
                raise ValueError("Limite de 8 contas por criador.")
            cri["contas"].append(conta)
            self._salvar("criadores")
        self.ultimo["status"] = 0
        self.acordar.set()
        return cri

    def conta_remover(self, d: dict) -> dict:
        with self.trava:
            cri = self._achar(d.get("criador"))
            chave = str(d.get("chave") or "")
            cri["contas"] = [k for k in cri["contas"] if not (k["plataforma"] == d.get("plataforma") and chave in (k.get("id"), k["login"]))]
            self._salvar("criadores")
        return cri

    def buscar_ids(self, d: dict) -> dict:
        """Candidatos oficiais para o usuário confirmar. Nada é associado sozinho."""
        cri = self._achar(d.get("id"))
        nome = cri["nome"]
        base = _slug(nome)
        palavras = [_slug(p) for p in nome.split() if _slug(p)]
        termos = list({t.lower(): t for t in (nome, base, palavras[0] if palavras else "") if len(t) >= 2}.values())[:3]
        logins = list(dict.fromkeys(l for l in (base, "_".join(palavras)) if re.fullmatch(r"[a-z0-9_]{3,25}", l)))  # o nome inteiro, sem presumir
        cand: dict[str, dict] = {}
        avisos = []
        for termo in termos:
            for c in self._tw("/search/channels", [("query", termo), ("first", "8")]).get("data") or []:
                cand.setdefault(f"twitch:{c['id']}", {"plataforma": "twitch", "id": c["id"], "login": c["broadcaster_login"], "nome": c["display_name"],
                                                      "foto": c.get("thumbnail_url", ""), "ao_vivo": bool(c.get("is_live")), "jogo": c.get("game_name", ""),
                                                      "titulo": c.get("title", ""), "idioma": c.get("broadcaster_language", ""),
                                                      "fonte": f"GET /search/channels “{termo}”"})
        if logins:
            for u in self._tw("/users", [("login", l) for l in logins]).get("data") or []:
                c = cand.setdefault(f"twitch:{u['id']}", {"plataforma": "twitch", "id": u["id"], "login": u["login"], "nome": u["display_name"],
                                                          "foto": u.get("profile_image_url", ""), "fonte": "GET /users"})
                c.update(exato=True, descricao=(u.get("description") or "")[:160], desde=u.get("created_at", "")[:10])
        if self._kick_ok():
            slugs = list(dict.fromkeys([base, "-".join(palavras), "_".join(palavras)] + [c["login"] for c in cand.values()]))
            try:
                for c in self._kick([s for s in slugs if re.fullmatch(r"[a-z0-9_-]{2,25}", s)]):
                    s = c.get("stream") or {}
                    cand[f"kick:{c.get('slug')}"] = {"plataforma": "kick", "id": str(c.get("broadcaster_user_id", "")), "login": c.get("slug", ""),
                                                     "nome": c.get("slug", ""), "ao_vivo": bool(s.get("is_live")), "titulo": c.get("stream_title", ""),
                                                     "jogo": (c.get("category") or {}).get("name", ""), "exato": c.get("slug") == base, "fonte": "Kick GET /channels"}
            except ValueError as e:
                avisos.append(str(e))
        else:
            avisos.append("Kick não consultada: informe o Client ID e o Client Secret da Kick em Configurações.")
        avisos.append("YouTube não consultado: sem integração. Adicione a conta à mão, se quiser.")
        ja = {(k["plataforma"], k.get("id") or k["login"]) for k in cri["contas"]}
        tw = [c for c in cand.values() if c["plataforma"] == "twitch"]
        if tw:  # dados oficiais para reconhecer o canal certo: seguidores, parceria, descrição, idade da conta
            for u in self._tw("/users", [("id", c["id"]) for c in tw[:100]]).get("data") or []:
                c = cand.get(f"twitch:{u['id']}")
                if c:
                    c.update(tipo={"partner": "Parceiro da Twitch", "affiliate": "Afiliado"}.get(u.get("broadcaster_type") or "", ""),
                             descricao=(u.get("description") or "")[:200], desde=(u.get("created_at") or "")[:10], foto=u.get("profile_image_url") or c.get("foto", ""))
            for c in tw[:16]:
                try:
                    c["seguidores"] = int(self._tw("/channels/followers", [("broadcaster_id", c["id"]), ("first", "1")]).get("total") or 0)
                except ValueError:
                    c["seguidores"] = None
        lista = sorted(cand.values(), key=lambda c: (-(c.get("seguidores") or 0), not c.get("exato")))
        if tw and max((c.get("seguidores") or 0) for c in tw) < 20000:
            avisos.insert(0, "Nenhum candidato da Twitch passa de 20 mil seguidores. Se o criador é grande, ele provavelmente transmite em outra plataforma (Kick, YouTube): use Adicionar conta.")
        return {"criador": cri["id"], "consultas": termos, "logins": logins, "avisos": avisos,
                "candidatos": [{**c, "associado": (c["plataforma"], c.get("id") or c["login"]) in ja} for c in lista[:12]]}

    def favoritar(self, d: dict) -> dict:
        conta = self._usuario_twitch(str(d.get("user_id") or ""), "")
        with self.trava:
            for c in self.criadores:
                if any(k["plataforma"] == "twitch" and k.get("id") == conta["id"] for k in c["contas"]):
                    return {"criador": c, "novo": False}
            cri = next((c for c in self.criadores if _slug(c["nome"]) == conta["login"] and not any(k["plataforma"] == "twitch" for k in c["contas"])), None)
            if cri is None:
                cri = {"id": _novo_id(), "nome": conta["nome"], "contas": [], "criado": time.time()}
                self.criadores.append(cri)
            cri["contas"].append(conta)
            self._salvar("criadores")
        self.ultimo["status"] = 0
        self.acordar.set()
        return {"criador": cri, "novo": True}

    # ------------------------------------------------------ monitoramento e fila de revisão

    def monitor_adicionar(self, d: dict) -> dict:
        ident, login = str(d.get("user_id") or ""), str(d.get("login") or "").strip().lower()
        login = re.sub(r"^https?://(www\.)?twitch\.tv/", "", login).strip("/@ ").split("/")[0]
        if not ident and any(m["login"] == login for m in self.monitor["canais"]):
            raise ValueError("Esse canal já está sendo monitorado.")
        u = self._usuario_twitch(ident, login)
        with self.trava:
            if any(m["user_id"] == u["id"] for m in self.monitor["canais"]):
                raise ValueError("Esse canal já está sendo monitorado.")
            if len(self.monitor["canais"]) >= MAX_MONITOR:
                raise ValueError(f"O limite é de {MAX_MONITOR} lives monitoradas. Remova uma para adicionar outra.")
            self.monitor["canais"].append({"user_id": u["id"], "login": u["login"], "nome": u["nome"], "foto": u["foto"], "desde": time.time()})
            self._salvar("monitor")
        self.ultimo["status"] = self.ultimo["monitor"] = 0
        self.acordar.set()
        return self.monitor_listar()

    def monitor_remover(self, d: dict) -> dict:
        with self.trava:
            self.monitor["canais"] = [m for m in self.monitor["canais"] if m["user_id"] != str(d.get("user_id"))]
            self.mon.pop(str(d.get("user_id")), None)
            self._salvar("monitor")
        return self.monitor_listar()

    def monitor_listar(self, _=None) -> dict:
        canais_m = [{**m, **self.mon.get(m["user_id"], {}), "status": self.status.get(f"twitch:{m['user_id']}")} for m in self.monitor["canais"]]
        registro = {c["id"]: c for c in canais.cfg["clips"]}
        fila_r = []
        for item in self.monitor["fila"][::-1]:
            r = registro.get(item["id"]) or {}
            estado = "importado" if r.get("importado") else item.get("estado", "pendente")
            fila_r.append({**item, "estado": estado, "crescimento": self._crescimento(item["id"]),
                           "registro": {"acesso": r.get("acesso", ""), "importado": r.get("importado", "")} if r else None})
        conta = {k: sum(1 for i in fila_r if i["estado"] == k) for k in ("pendente", "importado", "descartado")}
        ids = {m["user_id"] for m in self.monitor["canais"]}
        return {"canais": canais_m, "max": MAX_MONITOR, "fila": fila_r, "contagem": conta, "agora": time.time(),
                "eventos": [e for e in self.eventos[::-1] if e.get("conta_id") in ids][:30],
                "proximo": {"status": self.ultimo["status"] + STATUS_CADA, "clips": self.ultimo["monitor"] + MONITOR_CADA},
                "erro": self.erro_fundo, "conectado": bool(canais.cfg["twitch"].get("access_token"))}

    def revisao(self, d: dict) -> dict:
        acao = {"descartar": "descartado", "restaurar": "pendente"}.get(str(d.get("acao")))
        if not acao:
            raise ValueError("Ação inválida.")
        with self.trava:
            item = next((i for i in self.monitor["fila"] if i["id"] == str(d.get("id"))), None)
            if not item:
                raise ValueError("Clipe não está na fila.")
            item["estado"] = acao
            self._salvar("monitor")
        return self.monitor_listar()

    # ------------------------------------------------------ importação (fluxos existentes de canais.py e do painel)

    def registrar_clip(self, d: dict) -> dict:
        """Coloca o clipe no registro de canais.py, que é o que importar_clip e /api/clip/anexar esperam."""
        cid = str(d.get("id") or "").strip()
        if not re.fullmatch(r"[\w-]{3,120}", cid):
            raise ValueError("Clipe inválido.")
        atual = next((c for c in canais.cfg["clips"] if c["id"] == cid), None)
        if atual:
            return atual
        dados = self._tw("/clips", [("id", cid)]).get("data") or []  # dados oficiais: não confia no que veio da tela
        if not dados:
            raise ValueError("A Twitch não encontrou este clipe (pode ter sido apagado).")
        c = dados[0]
        u = (self._tw("/users", [("id", c["broadcaster_id"])]).get("data") or [{}])[0]
        reg = {"id": c["id"], "login": u.get("login") or c.get("broadcaster_name", "").lower(), "id_canal": c["broadcaster_id"], "edit_url": "",
               "criado": time.time(), "estado": "pronto", "titulo": c.get("title", ""), "url": c.get("url", ""), "thumb": c.get("thumbnail_url", ""),
               "duracao": c.get("duration", 0), "importado": "", "origem": "descobrir"}
        with canais.trava:
            atual = next((x for x in canais.cfg["clips"] if x["id"] == cid), None)
            if atual:
                return atual
            canais.cfg["clips"].append(reg)
            canais._salvar()
        return reg

    def importar(self, d: dict) -> dict:
        reg = self.registrar_clip(d)
        if reg.get("importado"):
            return {"corte": reg["importado"], "pronto": True}
        if reg.get("acesso") == "so_link":
            raise ValueError("Só link: a Twitch já recusou o arquivo deste clipe para a sua conta (só o dono do canal e os editores dele baixam). "
                             "Use Abrir link ou Importar arquivo autorizado.")
        cid = reg["id"]
        return fila.adicionar("clip", "Importando clip da Twitch (oficial)", lambda t: canais.importar_clip(cid, t), f"clip:{cid}").publico()

    def editar_clipe(self, d: dict) -> dict:
        """Baixa o arquivo público do clipe (como o player da Twitch faz), vira corte e vai para o editor. Só com autorização confirmada."""
        if not d.get("autorizado"):
            raise ValueError("Confirme que você tem autorização para usar este clipe.")
        cid = re.sub(r"[^\w-]", "", str(d.get("id") or ""))[:120]
        if not cid:
            raise ValueError("Clipe inválido.")
        titulo, canal = str(d.get("titulo") or "")[:200], str(d.get("canal") or "")[:60]

        def trabalho(t):
            import subprocess
            import sys as _sys
            from . import vods
            from .fontes import YTDLP
            pasta = DADOS / "clipes"
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo = pasta / f"{cid}.mp4"
            if not arquivo.is_file():
                t.avancar(0.1, "Baixando o clipe")
                r = subprocess.run([*YTDLP, "-f", "best[ext=mp4]/best", "-o", str(arquivo), f"https://clips.twitch.tv/{cid}"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NO_WINDOW if _sys.platform == "win32" else 0)
                if r.returncode != 0 or not arquivo.is_file():
                    erro = (r.stderr.strip().splitlines() or ["erro desconhecido"])[-1]
                    raise RuntimeError(f"A Twitch não entregou o clipe: {erro[:200]}")
            info = vods.abrir_arquivo(str(arquivo))
            t.avancar(0.4, "Criando o corte")
            return vods.criar_corte({"tipo": "arquivo", "id": info["id"], "inicio": 0, "fim": max(1.0, info["duracao"] - 0.05),
                                     "titulo": titulo, "streamer": canal}, t)
        return fila.adicionar("corte", f"Editando o clipe de {canal or 'Twitch'}", trabalho, f"editar:{cid}").publico()

    # ------------------------------------------------------ trabalho de fundo

    def _laco(self) -> None:
        while True:
            self.acordar.wait(10)
            self.acordar.clear()
            try:
                self._ciclo()
                self.erro_fundo = ""
            except ValueError as e:
                self.erro_fundo = str(e)
            except Exception as e:  # nunca derruba a thread de fundo
                traceback.print_exc()
                self.erro_fundo = f"Falha inesperada: {e}"
            if self.sujo:
                try:
                    self._salvar("amostras")
                except OSError:
                    pass

    def _ciclo(self) -> None:
        if not canais.cfg["twitch"].get("access_token"):
            raise ValueError("Twitch não conectada: o monitoramento espera a conta em Configurações.")
        espera = _espera_limite(RESERVA_FUNDO)
        if espera:
            self.recuo = time.time() + espera
            return
        agora = time.time()
        if agora - self.ultimo["status"] >= STATUS_CADA:
            self.ultimo["status"] = agora
            self._checar_status()
        if agora - self.ultimo["monitor"] >= MONITOR_CADA:
            self.ultimo["monitor"] = agora
            self._checar_monitorados()
        if agora - self.ultimo["amostra"] >= AMOSTRA_CADA:
            self.ultimo["amostra"] = agora
            self._reamostrar()

    def _evento(self, chave: str, plataforma: str, k: dict, criador: str, antes: dict, novo: dict) -> None:
        agora = time.time()
        quando = _ts(novo.get("inicio")) if novo["online"] and novo.get("inicio") else agora
        self.eventos.append({"quando": quando or agora, "detectado": agora, "desde_ultima": antes.get("visto", 0), "tipo": "online" if novo["online"] else "offline",
                             "plataforma": plataforma, "conta_id": k.get("id") or k.get("login"), "login": k.get("login", ""), "nome": k.get("nome", ""),
                             "criador": criador, "titulo": novo.get("titulo") or antes.get("titulo", ""), "jogo": novo.get("jogo") or antes.get("jogo", ""),
                             "inicio_live": antes.get("inicio", "") if not novo["online"] else novo.get("inicio", "")})

    def _checar_status(self) -> None:
        alvos: dict[str, tuple[dict, str]] = {}
        kick: dict[str, tuple[dict, str]] = {}
        for c in self.criadores:
            for k in c["contas"]:
                if k["plataforma"] == "twitch" and k.get("id"):
                    alvos[k["id"]] = (k, c["id"])
                elif k["plataforma"] == "kick" and k.get("login"):
                    kick[k["login"]] = (k, c["id"])
        for m in self.monitor["canais"]:
            alvos.setdefault(m["user_id"], ({"id": m["user_id"], "login": m["login"], "nome": m["nome"]}, ""))
        mudou = False
        if alvos:
            online, ids = {}, list(alvos)
            for i in range(0, len(ids), 100):
                for s in self._tw("/streams", [("user_id", x) for x in ids[i:i + 100]] + [("first", "100")], RESERVA_FUNDO).get("data") or []:
                    online[s["user_id"]] = s
            for uid, (k, criador) in alvos.items():
                s = online.get(uid)
                novo = {"online": bool(s), "visto": time.time()}
                if s:
                    novo.update({k2: v for k2, v in _live(s).items() if k2 in ("titulo", "espectadores", "inicio", "jogo", "thumb", "link")})
                mudou |= self._trocar(f"twitch:{uid}", "twitch", k, criador, novo)
        if kick and self._kick_ok():
            achados = {str(c.get("slug", "")).lower(): c for c in self._kick(list(kick))}
            for login, (k, criador) in kick.items():
                c = achados.get(login)
                if c is None:
                    continue
                s = c.get("stream") or {}
                novo = {"online": bool(s.get("is_live")), "visto": time.time(), "titulo": c.get("stream_title", ""), "espectadores": s.get("viewer_count", 0),
                        "inicio": s.get("start_time", ""), "jogo": (c.get("category") or {}).get("name", ""), "link": f"https://kick.com/{login}"}
                mudou |= self._trocar(f"kick:{login}", "kick", k, criador, novo)
        self._salvar("estado", *(["eventos"] if mudou else []))

    def _trocar(self, chave: str, plataforma: str, k: dict, criador: str, novo: dict) -> bool:
        with self.trava:
            antes = self.status.get(chave)
            self.status[chave] = novo
            if antes is not None and antes.get("online") is not None and antes["online"] != novo["online"]:
                self._evento(chave, plataforma, k, criador, antes, novo)
                return True
        return False

    def _checar_monitorados(self) -> None:
        novos_total = 0
        for m in list(self.monitor["canais"]):
            st = self.status.get(f"twitch:{m['user_id']}") or {}
            e = self.mon.setdefault(m["user_id"], {})
            e.update(online=st.get("online"), ultimo_status=st.get("visto"))
            if not st.get("online") or not st.get("inicio"):
                continue
            try:
                achados, cursor = {}, None
                for _ in range(3):  # clipes criados desde o início desta live
                    p = [("broadcaster_id", m["user_id"]), ("started_at", st["inicio"]), ("first", "100")]
                    r = self._tw("/clips", p + ([("after", cursor)] if cursor else []), RESERVA_FUNDO)
                    for d in r.get("data") or []:
                        achados[d["id"]] = _clip(d)
                    cursor = (r.get("pagination") or {}).get("cursor")
                    if not cursor:
                        break
            except ValueError as erro:
                e.update(erro=str(erro))
                continue
            agora = time.time()
            self._amostrar(achados.values(), agora)
            with self.trava:
                novos = [c for c in achados.values() if c["id"] not in self.vistos]
                for c in sorted(novos, key=lambda c: c["criado"]):
                    self.vistos[c["id"]] = None
                    self.monitor["fila"].append({**c, "login": m["login"], "nome": m["nome"], "encontrado": agora, "estado": "pendente"})
                if len(self.monitor["fila"]) > MAX_FILA:  # sai primeiro o que já foi revisado
                    revisados = [i for i in self.monitor["fila"] if i["estado"] != "pendente"]
                    sobra = len(self.monitor["fila"]) - MAX_FILA
                    fora = {id(i) for i in revisados[:sobra]}
                    self.monitor["fila"] = [i for i in self.monitor["fila"] if id(i) not in fora][-MAX_FILA:]
            novos_total += len(novos)
            e.update(erro="", ultimo_clips=agora, clips_live=len(achados), novos=len(novos), inicio=st["inicio"])
        if novos_total or self.monitor["canais"]:
            self._salvar("monitor")

    def _reamostrar(self) -> None:
        agora = time.time()
        with self.trava:
            for k in [k for k, v in self.acompanhadas.items() if agora - v["visto"] > 6 * 3600]:
                del self.acompanhadas[k]
            fila_a = sorted(self.acompanhadas.items(), key=lambda kv: -kv[1]["visto"])[:4]
        for chave, a in fila_a:
            lista = self._buscar_clips(a["alvos"], a["segundos"], a["paginas"], RESERVA_FUNDO)
            with self.trava:
                self.cache[chave] = (time.time(), lista)


descobrir = Descobrir()

# ------------------------------------------------------ sugestões de criadores por idioma
ARQ_SUGESTOES = PASTA / "sugestoes.json"
SUGESTOES_INICIAIS = {
    "pt": ["Gaules", "Casimiro=casimito", "Alanzoka", "Cellbit", "Coringa", "Vilena", "Japa", "Davy Jones", "Paulinho o Loko=paulinholokobr", "Bistecone", "Facada", "Baiano"],
    "en": ["Kai Cenat", "IShowSpeed", "xQc", "HasanAbi", "Jynxzi", "caseoh", "Jerma985", "Lirik", "summit1g", "Pokimane", "Ludwig", "Shroud", "Tyler1=loltyler1"],
    "es": ["Ibai", "AuronPlay", "ElXokas", "TheGrefg", "Rubius", "IlloJuan", "Spreen", "Westcol", "ElMariana", "Juansguarnizo"],
}
_trava_sug = threading.Lock()


def _resolver(nome: str) -> dict:
    """Acha o canal oficial pelo nome: entre o login exato e a busca da Twitch, fica o de mais seguidores (o mais provável de ser o famoso)."""
    if "=" in nome:  # "Nome=login" quando o login é conhecido
        nome, login = (x.strip() for x in nome.split("=", 1))
        u = (descobrir._tw("/users", [("login", login.lower())]).get("data") or [None])[0]
        if u:
            seg = int(descobrir._tw("/channels/followers", [("broadcaster_id", u["id"]), ("first", "1")]).get("total") or 0)
            return {"id": u["id"], "login": u["login"], "nome": u["display_name"], "foto": u.get("profile_image_url", ""), "seguidores": seg,
                    "busca": nome, "plataforma": "twitch"}
    cand: dict[str, dict] = {}
    slug, palavras = _slug(nome), [_slug(p) for p in nome.split() if _slug(p)]
    logins = [l for l in dict.fromkeys((slug, slug + "br", "_".join(palavras))) if re.fullmatch(r"[a-z0-9_]{3,25}", l)]
    if logins:
        for u in descobrir._tw("/users", [("login", l) for l in logins]).get("data") or []:
            cand[u["id"]] = {"id": u["id"], "login": u["login"], "nome": u["display_name"], "foto": u.get("profile_image_url", "")}
    for termo in dict.fromkeys((nome, slug, palavras[0] if palavras else "")):
        if len(termo) >= 3:
            for c in descobrir._tw("/search/channels", [("query", termo), ("first", "10")]).get("data") or []:
                cand.setdefault(c["id"], {"id": c["id"], "login": c["broadcaster_login"], "nome": c["display_name"], "foto": c.get("thumbnail_url", "")})
    chave = (palavras or [slug])[0][:6]
    perto = [c for c in cand.values() if chave and chave in c["login"]] or list(cand.values())
    melhor = None
    for c in perto[:8]:
        c["seguidores"] = int(descobrir._tw("/channels/followers", [("broadcaster_id", c["id"]), ("first", "1")]).get("total") or 0)
        if not melhor or c["seguidores"] > melhor["seguidores"]:
            melhor = c
    return {**melhor, "busca": nome, "plataforma": "twitch"} if melhor else {"busca": nome, "nao_achado": True}


def _ler_sugestoes() -> dict:
    d = ler_json(ARQ_SUGESTOES, None)
    if not isinstance(d, dict):
        d = {"nomes": {k: list(v) for k, v in SUGESTOES_INICIAIS.items()}, "canais": {}}
    return d


def sugestoes(consulta: dict) -> dict:
    """Criadores sugeridos para o idioma (lista editável) + quem está com mais audiência agora nesse idioma."""
    idioma = _q(consulta, "idioma", "pt").lower() or "en"
    if idioma not in ("pt", "en", "es"):
        idioma = "en"
    with _trava_sug:
        d = _ler_sugestoes()
        nomes = d["nomes"].setdefault(idioma, list(SUGESTOES_INICIAIS.get(idioma, [])))
        faltam = [n for n in nomes if n.lower() not in d["canais"]]
        if faltam:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(4) as ex:
                for n, r in zip(faltam, ex.map(lambda n: _resolver(n) if True else None, faltam)):
                    d["canais"][n.lower()] = r
            gravar_json(ARQ_SUGESTOES, d)
    ids = [d["canais"][n.lower()]["id"] for n in nomes if d["canais"].get(n.lower(), {}).get("id")]
    vivos = {s["user_id"]: s for i in range(0, len(ids), 100) for s in descobrir._tw("/streams", [("user_id", x) for x in ids[i:i + 100]] + [("first", "100")]).get("data") or []}
    lista = []
    for n in nomes:
        c = d["canais"].get(n.lower()) or {"busca": n, "nao_achado": True}
        s = vivos.get(c.get("id", ""))
        lista.append({**c, "busca": n, "ao_vivo": bool(s), "espectadores": int(s["viewer_count"]) if s else 0, "jogo": s.get("game_name", "") if s else ""})
    lista.sort(key=lambda c: (not c["ao_vivo"], -(c.get("seguidores") or 0)))
    quente = descobrir._cache(f"top:{idioma}", CACHE_LISTA, lambda: [
        {"id": s["user_id"], "login": s["user_login"], "nome": s["user_name"], "espectadores": int(s["viewer_count"]), "jogo": s.get("game_name", "")}
        for s in descobrir._tw("/streams", [("language", idioma), ("type", "live"), ("first", "20")]).get("data") or []])[1]
    return {"idioma": idioma, "sugeridos": lista, "em_alta": quente}


def sugestao_editar(d: dict) -> dict:
    idioma, nome = str(d.get("idioma") or "pt").lower(), re.sub(r"\s+", " ", str(d.get("nome") or "")).strip()[:40]
    if idioma not in ("pt", "en", "es") or not nome:
        raise ValueError("Informe o nome do criador.")
    with _trava_sug:
        s = _ler_sugestoes()
        lista = s["nomes"].setdefault(idioma, [])
        if d.get("acao") == "remover":
            s["nomes"][idioma] = [n for n in lista if n.lower() != nome.lower()]
        elif d.get("acao") == "trocar":  # o usuário escolhe o canal certo pelo login
            login = re.sub(r"^https?://(www\.)?twitch\.tv/", "", str(d.get("login") or "").strip().lower()).strip("/@ ")
            u = (descobrir._tw("/users", [("login", login)]).get("data") or [None])[0] if re.fullmatch(r"[a-z0-9_]{3,25}", login) else None
            if not u:
                raise ValueError("A Twitch não encontrou esse login.")
            seg = int(descobrir._tw("/channels/followers", [("broadcaster_id", u["id"]), ("first", "1")]).get("total") or 0)
            s["canais"][nome.lower()] = {"id": u["id"], "login": u["login"], "nome": u["display_name"], "foto": u.get("profile_image_url", ""),
                                         "seguidores": seg, "busca": nome, "plataforma": "twitch", "manual": True}
        elif not any(n.lower() == nome.lower() for n in lista):
            lista.append(nome)
        gravar_json(ARQ_SUGESTOES, s)
    return {"ok": True}


def iniciar() -> None:
    descobrir.iniciar()


def _rota(funcao):
    """GET no painel só trata ValueError: qualquer outra falha vira mensagem clara em vez de derrubar o pedido."""
    def envolta(arg):
        try:
            return funcao(arg)
        except ValueError:
            raise
        except ErroApi as e:
            raise ValueError(str(e)) from None
        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"Falha inesperada: {e}") from None
    return envolta


GET: dict = {caminho: _rota(f) for caminho, f in {
    "/api/descobrir/estado": descobrir.estado,
    "/api/descobrir/lives": descobrir.lives,
    "/api/descobrir/clips": descobrir.clips,
    "/api/descobrir/categorias/buscar": descobrir.buscar_categorias,
    "/api/descobrir/criadores": descobrir.criadores_listar,
    "/api/descobrir/monitor": descobrir.monitor_listar,
    "/api/descobrir/analise": lambda _: {**analisador.estado(), "captura": captura.estado()},
    "/api/descobrir/sugestoes": sugestoes,
}.items()}

POST: dict = {caminho: _rota(f) for caminho, f in {
    "/api/descobrir/categorias": descobrir.categorias,
    "/api/descobrir/criadores/salvar": descobrir.criador_salvar,
    "/api/descobrir/criadores/remover": descobrir.criador_remover,
    "/api/descobrir/criadores/buscar-ids": descobrir.buscar_ids,
    "/api/descobrir/criadores/conta": descobrir.conta_adicionar,
    "/api/descobrir/criadores/conta-remover": descobrir.conta_remover,
    "/api/descobrir/favoritar": descobrir.favoritar,
    "/api/descobrir/monitor/adicionar": descobrir.monitor_adicionar,
    "/api/descobrir/monitor/remover": descobrir.monitor_remover,
    "/api/descobrir/revisao": descobrir.revisao,
    "/api/descobrir/clip/registrar": descobrir.registrar_clip,
    "/api/descobrir/clip/importar": descobrir.importar,
    "/api/descobrir/analise/iniciar": analisador.iniciar,
    "/api/descobrir/analise/parar": lambda _: analisador.parar(),
    "/api/descobrir/analise/corte": lambda d: analisador.criar_corte(d, fila),
    "/api/descobrir/sugestoes/editar": sugestao_editar,
    "/api/descobrir/aovivo/iniciar": captura.iniciar,
    "/api/descobrir/clip/editar": descobrir.editar_clipe,
    "/api/descobrir/aovivo/parar": lambda _: captura.parar(),
}.items()}
