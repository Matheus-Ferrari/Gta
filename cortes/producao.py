"""Produção: tudo o que o Vice Clips já fez e está fazendo, separado por streamer e pela origem de cada corte, com o
porquê de cada um (views e posição do clipe, regra do automático, nota e motivos do momento da gravação).

Também monta o Resumo de uma live (os clipes mais vistos da live inteira e os picos, em blocos de 10 min) e o
Compilado: os melhores clipes da live num vídeo só, 16:9, com os capítulos prontos para a descrição.

Cortes antigos não guardavam a origem: ela é deduzida da pasta (clipe baixado, gravação, VOD ou arquivo), da lista de
clipes já pegos de cada automático e das sugestões da análise da gravação.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from . import editor
from .ao_vivo import (ARQ_ESTADO, PASTA as PASTA_ANALISE, RE_GRAVACAO_NOME, Analisador, analisador, captura, ler_estado,
                      login_gravacao, plataforma_gravacao)
from .config import DADOS, LIVES, ffmpeg, gravar_json, ler_json
from .descobrir import ARQ_AUTO_ANTIGAS, _clip, _clip_kick, _kick_site, _renderizar_no_modelo, _rfc, _rota, _ts, automaticos, baixar_clipe, descobrir
from .tarefas import fila

GRAVACOES = DADOS / "ao_vivo"
COMPILADOS = LIVES / "Compilados"
LIXEIRA = DADOS / "lixeira"
ARQ_PRODUCAO = DADOS / "producao.json"  # cortes marcados para manter
ARQ_INFO = DADOS / "descobrir" / "clipes_info.json"  # views atuais dos clipes que viraram corte
RE_LOGIN = re.compile(r"[a-z0-9_-]{2,25}")
RE_CHAT = re.compile(r"chat [\d.]+x|rindo|pedindo clip|reagindo")
BLOCO = 600  # resumo da live: blocos de 10 min
MAX_COMPILADO, MAX_DUR_COMPILADO = 25, 30 * 60
_trava = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def _guardado(chave: str, validade: float, f, forcar: bool = False):
    agora = time.time()
    if not forcar and chave in _cache and agora - _cache[chave][0] < validade:
        return _cache[chave][1]
    valor = f()
    _cache[chave] = (agora, valor)
    return valor


# ------------------------------------------------------------------ manter (o que o usuário quer guardar)

def _prefs() -> dict:
    return ler_json(ARQ_PRODUCAO, {}) or {}


def manter(d: dict) -> dict:
    """Marca (ou desmarca) cortes para manter: na hora de limpar, dá para excluir só os que não estão marcados."""
    ids = [str(x)[:300] for x in (d.get("cortes") or []) if x][:500]
    with _trava:
        p = _prefs()
        m = p.setdefault("manter", {})
        for i in ids:
            if d.get("manter"):
                m[i] = time.time()
            else:
                m.pop(i, None)
        gravar_json(ARQ_PRODUCAO, p)
    return {"manter": list(m)}


# ------------------------------------------------------------------ views atuais dos clipes que viraram corte

class InfoClipes:
    """Consulta de tempos em tempos as views atuais dos clipes que viraram corte (Twitch em lotes de 100, Kick um por um),
    em segundo plano: a página mostra o que já sabe e atualiza na próxima vez."""

    VALIDADE = 900

    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.cache: dict[str, dict] = ler_json(ARQ_INFO, {}) or {}
        self.ocupado = False

    def pedir(self, alvos: list[tuple[str, str]]) -> None:
        agora = time.time()
        velhos = [(p, i) for p, i in dict.fromkeys(alvos) if agora - (self.cache.get(i) or {}).get("visto", 0) > self.VALIDADE]
        with self.trava:
            if not velhos or self.ocupado:
                return
            self.ocupado = True
        threading.Thread(target=self._buscar, args=(velhos,), daemon=True).start()

    def _guardar(self, cid: str, c: dict | None) -> None:
        if c:
            self.cache[cid] = {"views": c["views"], "titulo": c["titulo"], "autor": c["autor"], "criado": c["criado"], "url": c["url"],
                               "duracao": c["duracao"], "visto": time.time()}
        else:  # apagado na plataforma (ou fora do alcance): guarda o que já se sabia
            self.cache[cid] = {**(self.cache.get(cid) or {}), "visto": time.time(), "sumiu": True}

    def _buscar(self, velhos: list[tuple[str, str]]) -> None:
        try:
            tw = [i for p, i in velhos if p == "twitch"]
            for k in range(0, len(tw), 100):
                lote = tw[k:k + 100]
                try:
                    dados = descobrir._tw("/clips", [("id", x) for x in lote]).get("data") or []
                except Exception:
                    break  # Twitch desconectada ou no limite: tenta na próxima
                achados = {d["id"]: _clip(d) for d in dados}
                for x in lote:
                    self._guardar(x, achados.get(x))
            for _, i in [v for v in velhos if v[0] == "kick"][:40]:
                try:
                    d = _kick_site(f"/clips/{i}").get("clip") or {}
                except ValueError as e:
                    if "não encontrou" in str(e):
                        self._guardar(i, None)
                    continue
                self._guardar(i, _clip_kick(d) if d.get("id") else None)
                time.sleep(0.25)  # devagar com o site da Kick
            with self.trava:
                if len(self.cache) > 3000:
                    for k, _ in sorted(self.cache.items(), key=lambda kv: kv[1].get("visto", 0))[:len(self.cache) - 3000]:
                        del self.cache[k]
                gravar_json(ARQ_INFO, self.cache)
        finally:
            self.ocupado = False


info_clipes = InfoClipes()


# ------------------------------------------------------------------ de onde veio cada corte

def _inferir(l: dict, c: dict, feito_por: dict, sugestoes: dict) -> dict:
    """Origem de um corte antigo (de antes de a origem ser guardada), deduzida da pasta e do que o painel lembra."""
    fonte = str(l.get("origem_live") or "")
    if fonte.startswith("http"):
        return {"tipo": "vod", "link": fonte, "inferido": True}
    p = Path(fonte) if fonte else None
    if p and p.parent.name.lower() == "clipes":
        cid = p.stem
        clipe = {"id": cid, "plataforma": "kick" if l["plataforma"] == "Kick" else "twitch", "titulo": c.get("texto", ""), "canal": l.get("streamer", "")}
        r = feito_por.get(cid)
        if r:
            return {"tipo": "auto", "regra": r["id"], "regra_nome": r["nome"], "intervalo": (r.get("consulta") or {}).get("intervalo"),
                    "minimo": r.get("minimo"), "clipe": clipe, "inferido": True, "regra_excluida": bool(r.get("excluida"))}
        return {"tipo": "clipe", "como": "", "clipe": clipe, "inferido": True}
    if p and p.parent.name.lower() == "ao_vivo":
        o = {"tipo": "gravacao", "como": "", "gravacao": p.name, "pico": c.get("inicio"), "inferido": True}
        ini, fim = c.get("inicio"), c.get("fim")
        s = next((s for s in sugestoes.get(p.name, []) if ini is not None and fim is not None
                  and abs(s["inicio"] - ini) < 2 and abs(s["fim"] - fim) < 3), None)
        texto, login = c.get("texto") or "", login_gravacao(p.name)
        if s:
            o.update(como="analise", nota=s.get("nota"), motivos=s.get("motivos") or [], fala=s.get("fala") or "", pico=s.get("pico"))
        elif texto.startswith("Clip de "):
            o["como"] = "clipar_agora"
        elif login and texto.lower().startswith(login + ": "):
            motivos = [m.strip() for m in texto.split(": ", 1)[1].split(",") if m.strip()]
            o.update(como="chat" if any(RE_CHAT.search(m) for m in motivos) else "analise", motivos=motivos)
        return o
    return {"tipo": "arquivo", "arquivo": p.name if p else "", "inferido": True}


def _mb(l: dict, c: dict) -> float:
    """Quanto o corte ocupa no disco: a fonte (trecho original) mais os Reels exportados dele."""
    live = LIVES / Path(l["pasta"]).parent
    stem = Path(c["arquivo"]).stem
    total = 0
    for f in [live / "fontes" / f"{stem}.mp4", live / "cortes" / c["arquivo"], *[live / "cortes" / "editados" / e["arquivo"] for e in c.get("editados") or []]]:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return round(total / 1048576, 1)


def _analises() -> dict[str, dict]:
    """Estado de cada análise guardada (a geral e a de cada gravação ao vivo), pelo nome do arquivo analisado."""
    em_memoria = {str(analisador.arq): analisador, **{str(g.analise.arq): g.analise for g in list(captura.gravacoes.values()) if g.analise}}
    achadas: dict[str, dict] = {}
    for arq in [ARQ_ESTADO, *sorted(PASTA_ANALISE.glob("analise_*.json"))]:
        e = ler_estado(arq)
        if not e.get("arquivo"):
            continue
        a = em_memoria.get(str(arq))
        item = {"fonte": "global" if arq == ARQ_ESTADO else arq.stem[len("analise_"):], "estado": e.get("estado"), "rodando": bool(a and a.rodando()),
                "processado": e.get("processado", 0), "janelas": e.get("janelas", 0), "janela": e.get("janela", 25), "mensagem": e.get("mensagem", ""),
                "sugestoes": [{**{k: s.get(k) for k in ("pico", "inicio", "fim", "nota", "motivos", "fala", "tipo")}, "indice": i}
                              for i, s in enumerate(e.get("sugestoes") or [])]}
        nome = Path(e["arquivo"]).name
        if nome not in achadas or item["janelas"] > achadas[nome]["janelas"]:
            achadas[nome] = item
    return achadas


def _gravacoes(analises: dict) -> list[dict]:
    vivas = {Path(g.info.get("arquivo", "")).name: g for g in list(captura.gravacoes.values()) if g.info}
    saida = []
    for f in sorted(GRAVACOES.glob("*.ts"), key=lambda f: -f.stat().st_mtime) if GRAVACOES.is_dir() else []:
        st = f.stat()
        m = RE_GRAVACAO_NOME.match(f.name)
        g = vivas.get(f.name)
        est = g.estado() if g else {}
        try:
            comecou = est.get("comecou") or (time.mktime(time.strptime(f"{m['data']} {m['hora']}", "%Y-%m-%d %H%M")) if m else st.st_ctime)
        except ValueError:
            comecou = st.st_ctime
        saida.append({"nome": f.name, "login": login_gravacao(f.name), "plataforma": plataforma_gravacao(f.name), "mb": round(st.st_size / 1048576),
                      "comecou": comecou, "modificado": st.st_mtime, "minutos": round(max(0.0, st.st_mtime - comecou) / 60, 1),
                      "gravando": bool(est.get("rodando")), "estado": est.get("estado") or "guardada", "auto": est.get("auto", 0),
                      "no_painel": bool(g), "analise": analises.get(f.name), "chat": est.get("chat") if est else None})
    return saida


def _streamers_da_regra(r: dict) -> list[str]:
    c = r.get("consulta") or {}
    if c.get("origem") == "canal":
        nome = c.get("canal") if c.get("plataforma") == "kick" else (c.get("nome") or c.get("canal"))
        return [str(nome or "").lower()]
    if c.get("origem") == "criador":
        cri = next((x for x in descobrir.criadores if x["id"] == c.get("criador")), None)
        return [str(k["login"]).lower() for k in (cri or {}).get("contas", []) if k.get("login")]
    return []


def _compilados() -> list[dict]:
    saida = []
    for j in COMPILADOS.glob("*/compilado.json") if COMPILADOS.is_dir() else []:
        mp4 = j.with_suffix(".mp4")
        if not mp4.is_file():
            continue
        rel = f"Compilados/{j.parent.name}/compilado.mp4"
        saida.append({**(ler_json(j, {}) or {}), "nome": j.parent.name, "pasta": f"Compilados/{j.parent.name}", "url": "/video/" + quote(rel),
                      "thumb": "/thumb/" + quote(rel) + "?t=4", "mb": round(mp4.stat().st_size / 1048576)})
    return sorted(saida, key=lambda c: -(c.get("criado") or 0))


def listar(lives: list[dict], consulta=None) -> dict:
    regras = list(automaticos.regras)
    antigas = [{**r, "excluida": True} for r in ler_json(ARQ_AUTO_ANTIGAS, []) or [] if isinstance(r, dict) and r.get("id")]
    feito_por = {cid: r for r in antigas + regras for cid in r.get("feitos") or []}
    analises = _analises()
    sugestoes = {n: a["sugestoes"] for n, a in analises.items()}
    marcados = _prefs().get("manter") or {}
    grupos: dict[str, dict] = {}

    def grupo(chave: str) -> dict:
        return grupos.setdefault(chave, {"chave": chave, "plataformas": set(), "cortes": [], "gravacoes": [], "automaticos": [], "compilados": [], "ultimo": 0})

    pedir = []
    for l in lives:
        for c in l["cortes"]:
            o = c.get("origem") or _inferir(l, c, feito_por, sugestoes)
            streamer = (l.get("streamer") or login_gravacao(o.get("gravacao") or "") or "").strip().lower()
            cid = (o.get("clipe") or {}).get("id")
            if cid:
                pedir.append(((o["clipe"].get("plataforma") or "twitch"), cid))
            g = grupo(streamer)
            g["plataformas"].add(l["plataforma"].lower())
            g["ultimo"] = max(g["ultimo"], c.get("criado") or 0)
            g["cortes"].append({**c, "origem": o, "streamer": streamer, "plataforma": l["plataforma"], "pasta": l["pasta"], "live": l["titulo"],
                                "mb": _mb(l, c), "manter": c["id"] in marcados, "agora": info_clipes.cache.get(cid) if cid else None})
    info_clipes.pedir(pedir)
    for gv in _gravacoes(analises):
        g = grupo(gv["login"])
        g["gravacoes"].append(gv)
        g["ultimo"] = max(g["ultimo"], gv["modificado"])
        if gv["plataforma"]:
            g["plataformas"].add(gv["plataforma"])
    gerais = []
    for r in regras:
        item = {**{k: v for k, v in r.items() if k != "feitos"}, "n_feitos": len(r.get("feitos", [])),
                "historico": r.get("historico") or ([r["ultima"]] if r.get("ultima") else [])}
        alvos = _streamers_da_regra(r)
        for s in alvos:
            g = grupo(s)
            g["automaticos"].append(item)
            g["plataformas"].add("kick" if (r.get("consulta") or {}).get("plataforma") == "kick" else "twitch")
            g["ultimo"] = max(g["ultimo"], (r.get("ultima") or {}).get("quando") or 0)
        if not alvos:
            gerais.append(item)
    for cp in _compilados():
        g = grupo(str(cp.get("canal") or "").lower())
        g["compilados"].append(cp)
        g["ultimo"] = max(g["ultimo"], cp.get("criado") or 0)
    layouts = set(descobrir.modelos().get("streamers") or [])
    saida = []
    for g in grupos.values():
        g["plataformas"] = sorted(p for p in g["plataformas"] if p in ("twitch", "kick"))
        g["tem_layout"] = g["chave"] in layouts
        g["cortes"].sort(key=lambda c: -(c.get("criado") or 0))
        saida.append(g)
    saida.sort(key=lambda g: (g["chave"] == "", -g["ultimo"]))
    return {"streamers": saida, "regras_gerais": gerais, "agora": time.time()}


# ------------------------------------------------------------------ resumo de uma live (Kick ou Twitch)

def _q(consulta: dict, chave: str, padrao: str = "") -> str:
    return str((consulta.get(chave) or [padrao])[0]).strip()


def _canal(consulta: dict) -> tuple[str, str]:
    plat = "kick" if _q(consulta, "plataforma") == "kick" else "twitch"
    canal = _q(consulta, "canal").lower()
    if not RE_LOGIN.fullmatch(canal) or (plat == "twitch" and "-" in canal):
        raise ValueError("Canal inválido.")
    return plat, canal


def _usuario_twitch(canal: str) -> dict:
    u = _guardado(f"twuser:{canal}", 86400, lambda: (descobrir._tw("/users", [("login", canal)]).get("data") or [None])[0])
    if not u:
        raise ValueError("A Twitch não encontrou esse canal.")
    return u


def _lives_kick(canal: str) -> list[dict]:
    r = _kick_site(f"/channels/{canal}/videos")
    lista = r if isinstance(r, list) else (r.get("data") or [])
    saida = []
    for x in lista[:8]:
        try:
            ini = datetime.strptime(str(x.get("start_time") or ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        dur, ao_vivo = float(x.get("duration") or 0) / 1000, bool(x.get("is_live"))
        uid = (x.get("video") or {}).get("uuid") or ""
        thumb = x.get("thumbnail") or {}
        saida.append({"id": str(x.get("id")), "titulo": str(x.get("session_title") or ""), "inicio": ini, "fim": time.time() if ao_vivo or not dur else ini + dur,
                      "duracao": dur, "ao_vivo": ao_vivo, "views": int(x.get("views") or 0), "pico": int(x.get("viewer_count") or 0),
                      "link": f"https://kick.com/{canal}/videos/{uid}" if uid else "", "thumb": str(thumb.get("src") or "") if isinstance(thumb, dict) else ""})
    return saida


def _lives_twitch(canal: str) -> list[dict]:
    from .vods import _duracao_twitch
    u = _usuario_twitch(canal)
    vs = descobrir._tw("/videos", [("user_id", u["id"]), ("type", "archive"), ("first", "8")]).get("data") or []
    no_ar = (descobrir._tw("/streams", [("user_id", u["id"])]).get("data") or [None])[0]
    saida = []
    for v in vs:
        ini, dur = _ts(v.get("created_at", "")), _duracao_twitch(v.get("duration", ""))
        ao_vivo = bool(no_ar and abs(_ts(no_ar.get("started_at", "")) - ini) < 600)
        saida.append({"id": v["id"], "titulo": v.get("title", ""), "inicio": ini, "fim": time.time() if ao_vivo else ini + dur, "duracao": dur,
                      "ao_vivo": ao_vivo, "views": int(v.get("view_count") or 0), "pico": int(no_ar.get("viewer_count") or 0) if ao_vivo else 0,
                      "link": v.get("url", ""), "thumb": str(v.get("thumbnail_url") or "").replace("%{width}", "320").replace("%{height}", "180")})
    return saida


def lives_canal(consulta: dict) -> dict:
    """As últimas lives do canal (Kick: lista pública do canal; Twitch: gravações pela API oficial)."""
    plat, canal = _canal(consulta)
    lives = _guardado(f"lives:{plat}:{canal}", 300, lambda: _lives_kick(canal) if plat == "kick" else _lives_twitch(canal), _q(consulta, "forcar") == "1")
    return {"plataforma": plat, "canal": canal, "lives": lives}


def _clips_kick_live(canal: str, ini: float, fim: float) -> list[dict]:
    """A Kick não filtra clipes por horário: segue a lista do canal (mais recentes e mais vistos) até passar do início da live."""
    agora = time.time()
    if agora - ini > 7 * 86400:
        raise ValueError("A Kick só lista clipes dos últimos 7 dias.")
    tempo = "day" if agora - ini < 86400 - 600 else "week"
    achados: dict[str, dict] = {}
    for ordem, paginas in (("date", 40), ("view", 5)):
        cursor, vistos = None, set()
        for _ in range(paginas):
            r = _kick_site(f"/channels/{canal}/clips", {"sort": ordem, "time": tempo, **({"cursor": cursor} if cursor else {})})
            lote = [_clip_kick(d) for d in r.get("clips") or []]
            if not lote or all(c["id"] in vistos for c in lote):
                break
            for c in lote:
                vistos.add(c["id"])
                if ini - 60 <= _ts(c["criado"]) <= fim + 300:
                    achados[c["id"]] = c
            cursor = r.get("nextCursor")
            if not cursor or (ordem == "date" and min(_ts(c["criado"]) for c in lote) < ini - 60):
                break
            time.sleep(0.15)
    return list(achados.values())


def _clips_twitch_live(canal: str, ini: float, fim: float) -> list[dict]:
    u = _usuario_twitch(canal)
    achados: dict[str, dict] = {}
    cursor = None
    for _ in range(10):
        p = [("broadcaster_id", u["id"]), ("started_at", _rfc(ini - 60)), ("ended_at", _rfc(fim + 300)), ("first", "100")]
        r = descobrir._tw("/clips", p + ([("after", cursor)] if cursor else []))
        for d in r.get("data") or []:
            achados[d["id"]] = _clip(d)
        cursor = (r.get("pagination") or {}).get("cursor")
        if not cursor:
            break
    return list(achados.values())


def resumo_live(consulta: dict) -> dict:
    """Os clipes da live inteira pelo número de views, os picos (blocos de 10 min com mais clipes) e, se a live foi gravada
    aqui, os momentos que a análise achou, no tempo da live."""
    plat, canal = _canal(consulta)
    try:
        ini, fim = float(_q(consulta, "inicio")), float(_q(consulta, "fim"))
    except ValueError:
        raise ValueError("Escolha uma live.") from None
    if not 0 < ini < fim or fim - ini > 48 * 3600:
        raise ValueError("Período da live inválido.")
    clips = _guardado(f"resumo:{plat}:{canal}:{int(ini)}:{int(fim) // 300}", 600,
                      lambda: _clips_kick_live(canal, ini, fim) if plat == "kick" else _clips_twitch_live(canal, ini, fim), _q(consulta, "forcar") == "1")
    lista = sorted((dict(c) for c in clips), key=lambda c: -c["views"])
    n = max(1, math.ceil((fim - ini) / BLOCO))
    blocos = [{"i": k, "inicio": k * BLOCO, "clips": 0, "views": 0, "top": ""} for k in range(n)]
    plat_nome = "Kick" if plat == "kick" else "Twitch"
    for i, c in enumerate(lista, 1):
        off = c.get("vod_offset")
        momento = float(off) if isinstance(off, (int, float)) else max(0.0, _ts(c["criado"]) - ini - c["duracao"])
        c.update(posicao=i, momento=round(momento, 1), plataforma=plat, canal_login=canal)
        b = blocos[min(n - 1, int(momento // BLOCO))]
        b["clips"] += 1
        b["views"] += c["views"]
        b["top"] = b["top"] or c["id"]
        pasta = LIVES / plat_nome / c["id"] / "cortes" / "cortes.json"  # já virou corte? (a pasta do clipe tem o id dele)
        feitos = ler_json(pasta, []) if pasta.is_file() else []
        c["corte"] = f"{plat_nome}/{c['id']}/{feitos[0]['arquivo']}" if feitos else ""
    picos = [b["i"] for b in sorted(blocos, key=lambda b: (-b["clips"], -b["views"])) if b["clips"]][:3]
    nossos = []
    for gv in _gravacoes(_analises()):
        if gv["login"] != canal or not gv.get("analise"):
            continue
        desloc = gv["comecou"] - ini
        if desloc > fim - ini or desloc + gv["minutos"] * 60 < 0:
            continue
        for s in gv["analise"]["sugestoes"]:
            nossos.append({**s, "momento": round(desloc + (s.get("pico") or 0), 1), "gravacao": gv["nome"], "fonte": gv["analise"]["fonte"]})
    return {"plataforma": plat, "canal": canal, "inicio": ini, "fim": fim, "clips": lista[:300], "total": len(lista),
            "views": sum(c["views"] for c in lista), "blocos": blocos, "picos": picos, "nossos": sorted(nossos, key=lambda s: -(s.get("nota") or 0))[:40],
            "atualizado": time.time()}


# ------------------------------------------------------------------ compilado: os melhores clipes num vídeo só

def _num(v, tipo=int, padrao=0):
    try:
        return tipo(v)
    except (TypeError, ValueError):
        return padrao


def compilado(d: dict) -> dict:
    if not d.get("autorizado"):
        raise ValueError("Confirme que você tem autorização para usar estes clipes.")
    plat = "kick" if d.get("plataforma") == "kick" else "twitch"
    canal = str(d.get("canal") or "").strip().lower()
    if not RE_LOGIN.fullmatch(canal):
        raise ValueError("Canal inválido.")
    itens = []
    for x in (d.get("clips") or [])[:MAX_COMPILADO]:
        cid = re.sub(r"[^\w-]", "", str((x or {}).get("id") or ""))[:120] if isinstance(x, dict) else ""
        if cid:
            url = str(x.get("url") or "")
            itens.append({"id": cid, "titulo": str(x.get("titulo") or "")[:120], "views": _num(x.get("views")), "momento": _num(x.get("momento"), float, 0.0),
                          "autor": str(x.get("autor") or "")[:60], "url": url[:300] if url.startswith("https://") else "", "posicao": _num(x.get("posicao"))})
    if len(itens) < 2:
        raise ValueError("Escolha pelo menos 2 clipes para o compilado.")
    ordem = "views" if d.get("ordem") == "views" else "cronologica"
    itens.sort(key=(lambda x: -x["views"]) if ordem == "views" else (lambda x: x["momento"]))
    lv = d.get("live") if isinstance(d.get("live"), dict) else {}
    live = {"titulo": str(lv.get("titulo") or "")[:160], "inicio": _num(lv.get("inicio"), float, 0.0), "link": str(lv.get("link") or "")[:300]}
    meta = {"streamer": canal, "plataforma": plat, "origem": "compilado"}
    return fila.adicionar("compilado", f"Compilado: {len(itens)} clipes de {canal}", lambda t: _montar(t, plat, canal, itens, ordem, live),
                          f"compilado:{canal}:{int(live['inicio'])}:{len(itens)}", meta).publico()


def _hms(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _montar(t, plat: str, canal: str, itens: list[dict], ordem: str, live: dict) -> dict:
    kick, partes, falhas = plat == "kick", [], []
    for i, x in enumerate(itens):
        t.avancar(0.02 + 0.4 * i / len(itens), f"Baixando o clipe {i + 1} de {len(itens)}")
        try:
            arq = baixar_clipe(x["id"], kick, t, 0.02 + 0.4 * i / len(itens))
            s = editor.sondar(arq)
        except (RuntimeError, ValueError, subprocess.CalledProcessError) as e:
            falhas.append(f"{x['titulo'] or x['id']}: {str(e)[:120]}")
            continue
        if s["dur"] >= 1 and s.get("video"):
            partes.append((x, arq, s))
    if len(partes) < 2:
        raise RuntimeError("Menos de 2 clipes baixaram: não dá para montar o compilado. " + " · ".join(falhas[:3]))
    total = sum(s["dur"] for _, _, s in partes)
    if total > MAX_DUR_COMPILADO:
        raise RuntimeError(f"O compilado passaria de {MAX_DUR_COMPILADO // 60} minutos. Escolha menos clipes.")
    data = time.strftime("%Y-%m-%d_%H%M", time.localtime(live["inicio"] or time.time()))
    pasta = COMPILADOS / f"{canal}_{data}"
    k = 2
    while pasta.exists():
        pasta = COMPILADOS / f"{canal}_{data}_{k}"
        k += 1
    pasta.mkdir(parents=True)
    entradas, filtros, juntar, extra = [], [], [], len(partes)
    for j, (_, arq, _) in enumerate(partes):
        entradas += ["-i", str(arq)]
    for j, (_, _, s) in enumerate(partes):
        filtros.append(f"[{j}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{j}]")
        if s.get("audio"):
            filtros.append(f"[{j}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{j}]")
        else:  # clipe sem som: silêncio do mesmo tamanho, para o concat não quebrar
            entradas += ["-f", "lavfi", "-t", f"{s['dur']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            filtros.append(f"[{extra}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a{j}]")
            extra += 1
        juntar.append(f"[v{j}][a{j}]")
    filtros.append("".join(juntar) + f"concat=n={len(partes)}:v=1:a=1[v][a]")
    destino, temp = pasta / "compilado.mp4", pasta / "_compilado.mp4"
    base = [ffmpeg(), "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *entradas, "-filter_complex", ";".join(filtros),
            "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    codecs = {"h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-maxrate", "12M", "-bufsize", "18M"],
              "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]}
    erro = ""
    try:
        for nome, cod in codecs.items():
            proc = subprocess.Popen(base + cod + [str(temp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                    errors="replace", creationflags=editor.SEM_JANELA)
            try:
                for linha in proc.stdout:
                    if linha.startswith("out_time_us=") and linha[12:].strip().isdigit():
                        fr = min(1.0, int(linha[12:]) / 1e6 / max(total, 0.1))
                        t.avancar(0.45 + 0.53 * fr, f"Montando o compilado ({nome}) {round(fr * 100)}%")
            except BaseException:  # cancelado no meio: encerra o ffmpeg e apaga o arquivo pela metade
                proc.kill()
                proc.wait()
                raise
            erro = proc.stderr.read()
            if proc.wait() == 0 and temp.is_file():
                temp.replace(destino)
                break
            temp.unlink(missing_ok=True)
        else:
            linhas = [l for l in erro.splitlines() if l.strip()]
            raise RuntimeError(f"Não consegui montar o compilado: {linhas[-1] if linhas else 'erro desconhecido'}")
    except BaseException:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    capitulos, pos, clipes = [], 0.0, []
    for x, _, s in partes:
        capitulos.append(f"{_hms(pos)} {x['titulo'] or 'Clipe'}{' · ' + format(x['views'], ',').replace(',', '.') + ' views' if x['views'] else ''}")
        clipes.append({**x, "no_video": round(pos, 1), "duracao": round(s["dur"], 1)})
        pos += s["dur"]
    gravar_json(pasta / "compilado.json", {"titulo": f"Melhores momentos de {canal}" + (f" · {live['titulo'][:80]}" if live["titulo"] else ""),
                                           "canal": canal, "plataforma": plat, "live": live, "ordem": ordem, "clipes": clipes, "duracao": round(total, 1),
                                           "capitulos": "\n".join(capitulos), "falhas": falhas, "criado": time.time()})
    return {"compilado": f"Compilados/{pasta.name}", "url": "/video/" + quote(f"Compilados/{pasta.name}/compilado.mp4"),
            "aviso": f"{len(falhas)} clipe(s) não baixaram e ficaram de fora." if falhas else ""}


def excluir_compilado(d: dict) -> dict:
    nome = str(d.get("nome") or "")
    if not re.fullmatch(r"[\w-]{1,120}", nome) or not (COMPILADOS / nome).is_dir():
        raise ValueError("Compilado não encontrado.")
    LIXEIRA.mkdir(parents=True, exist_ok=True)
    shutil.move(str(COMPILADOS / nome), str(LIXEIRA / f"compilado_{nome}_{int(time.time())}"))
    return {"ok": True}


# ------------------------------------------------------------------ ações em lote

def renderizar(d: dict) -> dict:
    """Renderiza cortes prontos no layout salvo do streamer (ou num template salvo), com o título do corte na manchete."""
    ids = [str(x) for x in (d.get("cortes") or []) if x][:30]
    if not ids:
        raise ValueError("Nenhum corte escolhido.")
    modelo = str(d.get("modelo") or "streamer")[:40]
    tarefas = []
    for i in ids:
        a = editor.achar_corte(i)
        titulo, streamer = str(a.corte.get("texto") or ""), str((a.info or {}).get("streamer") or "")
        if modelo == "streamer" and not (editor.regioes_streamer(streamer) or {}).get("layout"):
            raise ValueError(f"{streamer or 'Este streamer'} não tem layout salvo. Abra um corte dele no editor, monte o template e clique em “Salvar para este streamer”.")

        def trabalho(t, c=a.id, ti=titulo, s=streamer):
            r = _renderizar_no_modelo(c, modelo, ti, s, t)
            return {"corte": c, **r}
        tarefas.append(fila.adicionar("exportar", f"Reel: {titulo[:60] or a.stem} ({streamer})", trabalho, f"render:{a.id}",
                                      {"streamer": streamer.lower(), "plataforma": a.plataforma.lower(), "origem": "render"}).publico())
    return {"tarefas": tarefas}


def corte_momento(d: dict) -> dict:
    """Cria o corte de um momento achado pela análise de qualquer gravação (inclusive de antes de o painel ser reaberto)."""
    fonte = str(d.get("fonte") or "")
    if fonte == "global":
        a = analisador
    elif RE_LOGIN.fullmatch(fonte):
        arq = PASTA_ANALISE / f"analise_{fonte}.json"
        g = captura.gravacoes.get(fonte)
        a = g.analise if g and g.analise and g.analise.arq == arq else Analisador(arq, PASTA_ANALISE / f"analise_{fonte}.log")
    else:
        raise ValueError("Análise não encontrada.")
    return a.criar_corte({"indice": d.get("indice"), "streamer": str(d.get("streamer") or "")[:60]}, fila)


GET = {caminho: _rota(f) for caminho, f in {"/api/producao/lives": lives_canal, "/api/producao/resumo": resumo_live}.items()}
POST = {"/api/producao/manter": manter, "/api/producao/compilado": compilado, "/api/producao/compilado/excluir": excluir_compilado,
        "/api/producao/renderizar": renderizar, "/api/producao/corte-momento": corte_momento}
