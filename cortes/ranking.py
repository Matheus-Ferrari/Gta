"""Fecha cada corte em pausas naturais e estima a relevância com os sinais disponíveis."""
from __future__ import annotations

import re

from .sinais import medir_audio, medir_chat

PAUSA = 0.6
SILENCIO = 4.0
CONTEXTO_ANTES = 10  # segundos de contexto antes do lance
CONTEXTO_DEPOIS = 5  # e depois dele, para mostrar a reação
FIM_FRASE = re.compile(r"[.!?…]$")
RISO = re.compile(r"\bk{4,}\b|\b(?:ha){3,}\b|\b(?:he){3,}\b|\brisos?\b|\brisadas?\b", re.IGNORECASE)
REACAO = re.compile(
    r"meu deus|n[aã]o acredito|caralho|puta que|que isso|olha isso|mano do c[eé]u|socorro|nossa senhora|inacredit[aá]vel|"
    r"absurdo|insano|ganhei|ganhamos|perdi tudo|morri|morreu|corre+\b|cuidado|mentira|surreal|ai meu|p[oô]rra|vai vai vai",
    re.IGNORECASE,
)
AGENDA = re.compile(
    r"\b\d{1,2} ?(?:h|horas?)\b|\b(?:às|as) \d{1,2}\b|\bda (?:manh[aã]|tarde|noite)\b|\bamanh[aã]\b|hor[aá]rios?\b|que horas|"
    r"abr(?:o|ir|e) (?:a )?live|cronograma|\bagenda\b|\b(?:segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)\b|"
    r"\binscrev|\bsubs?\b|\bprime\b|\bpix\b|\bdoa[cç][aã]o|link na bio|patroc[ií]n|\bcupom\b|volto j[aá]",
    re.IGNORECASE,
)


def _limites(c: dict, minimo: float, maximo: float) -> tuple[int, int] | None:
    p = c["palavras"]
    if len(p) < 8:
        return None
    pode_iniciar = [i for i in range(len(p))
                    if i == 0 or p[i]["i"] - p[i - 1]["f"] >= PAUSA or FIM_FRASE.search(p[i - 1]["p"])]
    antes_do_pico = [i for i in pode_iniciar if p[i]["i"] <= c["pico"] - CONTEXTO_ANTES]
    ini = antes_do_pico[-1] if antes_do_pico else 0
    for i in range(ini + 1, len(p)):  # não começa o corte antes de um silêncio longo
        if p[i]["i"] > c["pico"]:
            break
        if p[i]["i"] - p[i - 1]["f"] > SILENCIO:
            ini = i

    ultimo = len(p) - 1
    dentro = []
    for i in range(ini, len(p)):  # nem deixa um silêncio longo no meio
        if p[i]["f"] - p[ini]["i"] > maximo or (i > ini and p[i]["i"] - p[i - 1]["f"] > SILENCIO):
            break
        dentro.append(i)
    if not dentro:
        return None
    alvo = max(c["pico"] + CONTEXTO_DEPOIS, p[ini]["i"] + minimo)
    for i in dentro:
        natural = i == ultimo or p[i + 1]["i"] - p[i]["f"] >= PAUSA or FIM_FRASE.search(p[i]["p"])
        if p[i]["f"] >= alvo and natural:
            return ini, i
    fim = dentro[-1]
    return (ini, fim) if p[fim]["f"] - p[ini]["i"] >= minimo else None


def _sem_repetir(cortes: list[dict]) -> list[dict]:
    """Mantém o melhor de cada momento: não repete trecho nem a mesma fala."""
    aceitos: list[dict] = []
    for c in cortes:
        palavras = {p.lower() for p in c["texto"].split() if len(p) > 3}
        repetido = False
        for o in aceitos:
            comum = min(c["fim"], o["fim"]) - max(c["inicio"], o["inicio"])
            outras = {p.lower() for p in o["texto"].split() if len(p) > 3}
            parecido = len(palavras & outras) / max(len(palavras | outras), 1)
            if comum > 0.3 * min(c["fim"] - c["inicio"], o["fim"] - o["inicio"]) or parecido > 0.55:
                repetido = True
                break
        if not repetido:
            aceitos.append(c)
    return aceitos


def avaliar(texto: str, palavras: list[dict], pico: float, sinal: float, audio_m: dict | None, chat_m: dict | None) -> tuple[int, str]:
    """Nota de 0 a 100 e o motivo em uma frase. Estima relevância, não garante alcance."""
    a = audio_m or {"acima": 0.0, "subita": 0.0, "ritmo": 0.0, "agudo": 1.0}
    perto = [p for p in palavras if abs(p["i"] - pico) <= 4]
    risada = bool(RISO.search(texto)) or (a["ritmo"] >= 9 and len(perto) <= 12 and a["acima"] >= 3)
    grito = a["acima"] >= 8 and a["agudo"] >= 1.25
    voz = min(max(a["acima"], 0) / 12, 1)
    surpresa = min(max(a["subita"], 0) / 14, 1)
    reacao = 1.0 if risada or grito else 0.0
    fortes = REACAO.findall(texto)
    fala = min((len(fortes) + texto.count("!") * 0.5) / 4, 1)
    agenda = len(AGENDA.findall(texto))
    base = min(sinal * 1.5, 1)

    motivos = []
    if a["acima"] >= 4:
        motivos.append(f"voz {a['acima']:.0f} dB acima do normal")
    if a["subita"] >= 7:
        motivos.append("reação súbita")
    if risada:
        motivos.append("risada")
    if grito:
        motivos.append("grito")
    if chat_m:
        cresc = min(max(chat_m["crescimento"] - 1, 0) / 4, 1)
        repete = min(chat_m["parcela"] / 0.3, 1) if chat_m["vezes"] >= 4 else 0.0
        pontos = (18 * voz + 12 * surpresa + 12 * reacao + 20 * cresc + 12 * repete
                  + 6 * min(chat_m["hype"] / 0.3, 1) + 12 * fala + 8 * base)
        if chat_m["crescimento"] >= 1.8:
            motivos.append(f"chat {chat_m['crescimento']:.1f}x mais ativo")
        if chat_m["vezes"] >= 4:
            motivos.append(f"“{chat_m['repetida'][:18]}” repetido {chat_m['vezes']}x")
    else:  # sem chat há menos evidência, então a nota máxima é menor
        pontos = 0.85 * (26 * voz + 22 * surpresa + 18 * reacao + 22 * fala + 12 * base)
    if fortes:
        motivos.append("fala de reação: " + ", ".join(sorted({f.lower() for f in fortes})[:2]))
    if agenda >= 2:
        pontos *= 1 - min(0.14 * agenda, 0.7)
        motivos.append("nota reduzida por falar de agenda ou horários")
    nota = int(round(max(0, min(100, pontos))))
    frase = "; ".join(motivos) if motivos else "sem sinal forte, só um pico leve de voz"
    return nota, frase[0].upper() + frase[1:] + "."


def finalizar(cands: list[dict], minimo: float = 12, maximo: float = 70, audio=None, mensagens=None) -> list[dict]:
    prontos = []
    for c in cands:
        limites = _limites(c, minimo, maximo)
        if not limites:
            continue
        ini, fim = limites
        palavras = c["palavras"][ini: fim + 1]
        inicio, final = max(0, palavras[0]["i"] - 0.15), palavras[-1]["f"] + 0.35
        texto = " ".join(p["p"] for p in palavras)
        audio_m = medir_audio(audio, c["pico"]) if audio is not None else None
        chat_m = medir_chat(mensagens, c["pico"]) if mensagens else None
        nota, motivo = avaliar(texto, palavras, c["pico"], c["sinal"], audio_m, chat_m)
        prontos.append({"nota": nota, "inicio": round(inicio, 2), "fim": round(final, 2), "pico": c["pico"],
                        "texto": texto, "motivo": motivo, "palavras": palavras})
    return _sem_repetir(sorted(prontos, key=lambda x: x["nota"], reverse=True))
