"""Transforma uma live gravada em cortes verticais com legenda.

Exemplos:
    cortar.cmd "https://www.twitch.tv/videos/123456789" --qtd 10
    cortar.cmd "D:\\Videos\\live.mp4" --qtd 10 --webcam 0.72,0.68,0.26,0.30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from cortes import fontes, ranking, render, sinais, transcricao
from cortes.config import TAXA_AUDIO, pasta_da_live


def _webcam(texto: str) -> tuple[float, float, float, float]:
    partes = tuple(float(x) for x in texto.split(","))
    if len(partes) != 4 or not all(0 <= x <= 1 for x in partes):
        raise argparse.ArgumentTypeError("use x,y,largura,altura em frações de 0 a 1, ex.: 0.72,0.68,0.26,0.30")
    return partes


def _segundos(texto: str) -> float:
    total = 0.0
    for parte in texto.split(":"):
        total = total * 60 + float(parte)
    return total


def _hora(s: float) -> str:
    s = int(s)
    return f"{s // 3600:02d}h{s // 60 % 60:02d}m{s % 60:02d}s"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Cortador de lives local")
    ap.add_argument("video", help="link da live gravada (Twitch, Kick, YouTube) ou arquivo de vídeo")
    ap.add_argument("--qtd", type=int, default=10, help="quantos cortes gerar (padrão 10)")
    ap.add_argument("--dur-min", type=float, default=12, help="duração mínima de cada corte, em segundos")
    ap.add_argument("--dur-max", type=float, default=70, help="duração máxima de cada corte, em segundos")
    ap.add_argument("--inicio", type=_segundos, default=0, help="analisar a partir de HH:MM:SS")
    ap.add_argument("--minutos", type=float, help="analisar só esta quantidade de minutos")
    ap.add_argument("--chat", type=Path, help="chat da live: JSON do TwitchDownloader ou CSV segundos,mensagem")
    ap.add_argument("--webcam", type=_webcam, help="posição da webcam: x,y,largura,altura em frações de 0 a 1")
    ap.add_argument("--modelo", default="medium", help="modelo do Whisper: small, medium ou large-v3")
    ap.add_argument("--so-analisar", action="store_true", help="lista os cortes sem renderizar")
    args = ap.parse_args()

    inicio = time.time()
    link = fontes.eh_link(args.video)
    if link:
        dados = fontes.info(args.video)
        if dados.get("is_live"):
            print("Essa live ainda está no ar. Use o link da gravação quando ela terminar.")
            return 1
        nome = f"{dados.get('extractor_key', 'live')}_{dados['id']}"
        titulo = dados.get("title", nome)
        plataforma = fontes.plataforma(dados)
        streamer = dados.get("uploader") or dados.get("uploader_id") or dados.get("channel") or ""
        print(f"Live: {titulo}")
        entrada_audio = fontes.enderecos(args.video, fontes.FORMATO_AUDIO)[0]
    else:
        arquivo = Path(args.video)
        if not arquivo.is_file():
            print(f"Arquivo não encontrado: {arquivo}")
            return 1
        nome = titulo = arquivo.stem
        plataforma = "Arquivos"
        streamer = ""
        entrada_audio = str(arquivo.resolve())
    if args.inicio or args.minutos:
        nome += f"_{int(args.inicio)}s_{args.minutos or 'fim'}m"

    pasta = pasta_da_live(nome, plataforma)
    (pasta / "live.json").write_text(json.dumps({"titulo": titulo, "plataforma": plataforma, "origem": args.video, "streamer": streamer},
                                                ensure_ascii=False), encoding="utf-8")
    print("1/4 Lendo o áudio")
    caminho_audio = pasta / "audio.pcm"
    sinais.extrair_audio(entrada_audio, caminho_audio, args.inicio, args.minutos * 60 if args.minutos else None)
    audio = sinais.abrir_audio(caminho_audio)
    duracao = len(audio) // TAXA_AUDIO
    if duracao < 30:
        print("Vídeo curto demais para gerar cortes.")
        return 1

    print(f"2/4 Procurando picos em {_hora(duracao)}")
    voz = sinais.sinal_audio(audio)
    chat = mensagens = None
    arquivo_chat = args.chat
    if not arquivo_chat and link and dados.get("extractor_key") == "TwitchVod":
        destino_chat = pasta / "chat.json"
        if fontes.baixar_chat_twitch(dados["id"].lstrip("v"), destino_chat, args.inicio, duracao + sinais.ATRASO_CHAT):
            arquivo_chat = destino_chat
        else:
            print("    aviso: não consegui baixar o chat, vou usar só a voz")
    if arquivo_chat:
        mensagens = [(t - args.inicio, texto) for t, texto in sinais.ler_chat(arquivo_chat) if t >= args.inicio]
        por_minuto = len(mensagens) / (duracao / 60)
        if por_minuto >= sinais.CHAT_MINIMO:
            chat = sinais.sinal_chat(mensagens, duracao)
            print(f"    Chat: {len(mensagens)} mensagens ({por_minuto:.0f} por minuto)")
        else:
            print(f"    Chat fraco ({por_minuto:.1f} mensagens por minuto), vou usar só a voz")
    else:
        print("    Sem chat, vou usar só a voz")
    folga = int(max(35, args.dur_max * 0.6))
    cands = sinais.candidatos(sinais.combinar(voz, chat), qtd=args.qtd * 3, antes=folga, depois=folga, distancia=max(75, folga * 2))

    print(f"3/4 Transcrevendo {len(cands)} trechos com o modelo {args.modelo}")
    transcricao.transcrever(cands, audio, args.modelo, pasta / "transcricoes.json")
    cortes = ranking.finalizar(cands, args.dur_min, args.dur_max, audio, mensagens if chat is not None else None)[: args.qtd]
    if not cortes:
        print("Nenhum trecho com fala suficiente foi encontrado.")
        return 1

    saida = pasta / "cortes"
    saida.mkdir(exist_ok=True)
    print(f"4/4 Gerando {len(cortes)} cortes")
    entradas = fontes.enderecos(args.video, fontes.FORMATO_VIDEO) if link else [entrada_audio]
    for n, c in enumerate(cortes, 1):
        momento = c["inicio"] + args.inicio
        c["momento_na_live"] = _hora(momento)
        c["desloc"] = args.inicio
        c["arquivo"] = f"{n:02d}_nota{c['nota']}_{_hora(momento)}.mp4"
        print(f"  {n:02d}. nota {c['nota']:3d} | {_hora(momento)} | {c['fim'] - c['inicio']:.0f}s | {c['motivo']}")
        if not args.so_analisar:
            if link:
                duracao_corte = c["fim"] - c["inicio"]
                trecho = saida / "_trecho.mkv"
                render.baixar_trecho(entradas, momento, duracao_corte, trecho)
                achado = render.localizar(trecho, audio, c["inicio"], duracao_corte)
                if achado is None:
                    print("    aviso: não consegui conferir o sincronismo deste corte")
                    achado = min(render.MARGEM, momento)
                c["codificador"] = render.renderizar([str(trecho)], c, saida / c["arquivo"], args.webcam,
                                                     achado - c["inicio"])
                trecho.unlink(missing_ok=True)
            else:
                c["codificador"] = render.renderizar(entradas, c, saida / c["arquivo"], args.webcam, args.inicio)

    resumo = [{k: v for k, v in c.items() if k != "palavras"} for c in cortes]
    (saida / "cortes.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Pronto em {time.time() - inicio:.0f}s. Pasta: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
