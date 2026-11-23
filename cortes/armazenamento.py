"""Espaço em disco: gravações ao vivo, clipes baixados e lixeira, com o que dá para parar e apagar pelo painel.

Gravações ficam em DADOS/ao_vivo (uma por "Gravar e clipar"/"Analisar ao vivo"); clipes baixados em DADOS/clipes são só
o arquivo de origem (o corte criado tem a própria cópia); a lixeira guarda cortes excluídos para o Desfazer.
Uma gravação pode continuar sozinha se o painel de uma versão anterior foi fechado no meio: ela aparece como
"gravando sem controle" e pode ser parada aqui.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from .config import DADOS

GRAVACOES = DADOS / "ao_vivo"
CLIPES = DADOS / "clipes"
LIXEIRA = DADOS / "lixeira"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RE_GRAVACAO = re.compile(r"[\w.-]{1,120}\.ts")


def _tamanho(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0


def _gravadores() -> dict[str, list[int]]:
    """Processos do yt-dlp gravando em ao_vivo: nome do arquivo -> pids (inclusive os que ficaram sem painel)."""
    cmd = ["powershell", "-NoProfile", "-Command",
           "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, creationflags=SEM_JANELA)
        dados = json.loads(r.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    achados: dict[str, list[int]] = {}
    pasta = re.escape(str(GRAVACOES))
    for p in dados if isinstance(dados, list) else [dados]:
        linha = str((p or {}).get("CommandLine") or "")
        m = re.search(pasta + r"[\\/]+(" + RE_GRAVACAO.pattern + r")", linha) if "yt_dlp" in linha else None
        if m:
            achados.setdefault(m[1], []).append(int(p["ProcessId"]))
    return achados


def _da_tela() -> set[str]:
    """Os arquivos que este painel está gravando agora (os que a barra de gravação controla)."""
    from .ao_vivo import captura
    return captura.arquivos()


def listar(_=None) -> dict:
    from .ao_vivo import analisador, ler_estado
    ativos, atual = _gravadores(), _da_tela()
    analisando = Path(ler_estado().get("arquivo", "")).name if analisador.rodando() else ""
    gravacoes = []
    for f in sorted(GRAVACOES.glob("*.ts"), key=lambda f: -f.stat().st_mtime) if GRAVACOES.is_dir() else []:
        gravacoes.append({"nome": f.name, "mb": round(f.stat().st_size / 1048576), "modificado": f.stat().st_mtime,
                          "painel": f.name in atual, "gravando": f.name in ativos or f.name in atual, "analisando": f.name == analisando})
    clipes = [f for f in CLIPES.iterdir() if f.is_file()] if CLIPES.is_dir() else []
    lixo = [p for p in LIXEIRA.iterdir()] if LIXEIRA.is_dir() else []
    uso = shutil.disk_usage(DADOS)
    return {"gravacoes": gravacoes, "clipes": {"mb": round(sum(f.stat().st_size for f in clipes) / 1048576), "n": len(clipes)},
            "lixeira": {"mb": round(sum(_tamanho(p) for p in lixo) / 1048576), "n": len(lixo)},
            "livre_gb": round(uso.free / 1e9, 1), "total_gb": round(uso.total / 1e9), "pasta": str(DADOS)}


def _nome(d: dict) -> str:
    nome = str(d.get("nome") or "")
    if not RE_GRAVACAO.fullmatch(nome) or not (GRAVACOES / nome).is_file():
        raise ValueError("Gravação não encontrada. Atualize a lista.")
    return nome


def parar(d: dict) -> dict:
    """Para a gravação: a do painel pela barra; uma que ficou sem painel, encerrando o processo que grava esse arquivo."""
    nome = _nome(d)
    if nome in _da_tela():
        from .ao_vivo import captura
        captura.parar_arquivo(nome)
        return listar()
    pids = _gravadores().get(nome, [])
    if not pids:
        raise ValueError("Essa gravação já está parada.")
    for pid in pids:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, creationflags=SEM_JANELA)
    time.sleep(1)
    return listar()


def excluir(d: dict) -> dict:
    """Apaga de vez a gravação (não vai para a lixeira: é só o vídeo bruto; os cortes feitos dela continuam)."""
    nome = _nome(d)
    if nome in _da_tela() or nome in _gravadores():
        raise ValueError("Essa gravação ainda está gravando. Pare antes de excluir.")
    from .ao_vivo import analisador, captura, ler_estado
    # a análise segue lendo o arquivo por até 2 min depois que a gravação para: encerra antes de apagar
    for a in [analisador, *[g.analise for g in captura.gravacoes.values() if g.analise]]:
        if a.rodando() and Path(ler_estado(a.arq).get("arquivo", "")).name == nome:
            a.parar()
    for tentativa in range(10):
        try:
            (GRAVACOES / nome).unlink()
            break
        except PermissionError:
            if tentativa == 9:
                raise ValueError("O Windows ainda está usando esse arquivo. Espere alguns segundos e tente de novo.") from None
            time.sleep(0.5)
    return listar()


def analisar(d: dict) -> dict:
    """Procura os melhores momentos numa gravação guardada (ou que ainda cresce): voz, gritos, risadas e mudanças de cena."""
    nome = _nome(d)
    if not d.get("autorizado"):
        raise ValueError("Confirme que a gravação é sua ou que você tem autorização para cortá-la.")
    from .ao_vivo import analisador
    if analisador.rodando():
        raise ValueError("Já existe uma análise rodando. Pare a atual na Atividade antes de começar outra.")
    crescendo = nome in _gravadores() or nome in _da_tela()
    analisador.iniciar({"caminho": str(GRAVACOES / nome), "autorizado": True, "janela": 25, "visual": "leve", "seguir": crescendo,
                        "transcrever": bool(d.get("transcrever"))})
    return {"ok": True, "seguindo": crescendo}


def limpar_clipes(_=None) -> dict:
    """Clipes baixados são só a origem: o corte criado de cada um tem a própria cópia."""
    for f in CLIPES.iterdir() if CLIPES.is_dir() else []:
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass  # em uso por uma tarefa agora: fica para a próxima limpeza
    return listar()


def esvaziar_lixeira(_=None) -> dict:
    for p in LIXEIRA.iterdir() if LIXEIRA.is_dir() else []:
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return listar()


GET = {"/api/armazenamento": listar}
POST = {"/api/armazenamento/parar": parar, "/api/armazenamento/excluir": excluir, "/api/armazenamento/analisar": analisar,
        "/api/armazenamento/limpar-clipes": limpar_clipes, "/api/armazenamento/esvaziar-lixeira": esvaziar_lixeira}
