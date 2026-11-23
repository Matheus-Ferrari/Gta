# Instala o Vice Clips neste PC: ambiente Python, pacotes, ffmpeg 8.0.1 e TwitchDownloader.
# Pode rodar de novo a qualquer momento: o que já está instalado é pulado.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path

# Mesma regra de cortes/config.py: D:\Cortes se existe o D:, senão ViceClips na pasta do usuário.
if ($env:CORTES_DADOS) { $dados = $env:CORTES_DADOS }
elseif (Test-Path 'D:\') { $dados = 'D:\Cortes' }
else { $dados = Join-Path $env:USERPROFILE 'ViceClips' }
$tools = Join-Path $dados 'tools'
New-Item -ItemType Directory -Force -Path $tools | Out-Null
Write-Host "Dados e vídeos vão ficar em: $dados" -ForegroundColor Cyan

# 1. Python 3.11 ou mais novo
$py = $null
foreach ($c in @('py -3.13', 'py -3.12', 'py -3.11', 'python')) {
  $partes = $c.Split(' ')
  try {
    $v = & $partes[0] $partes[1..9] -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
    if ($LASTEXITCODE -eq 0 -and [int]$v -ge 311) { $py = $partes; break }
  } catch { }
}
if (-not $py) {
  Write-Host 'Python 3.11+ não encontrado. Instale com:  winget install Python.Python.3.13  e rode instalar.cmd de novo.' -ForegroundColor Yellow
  exit 1
}

# 2. Ambiente virtual e pacotes
$venv = Join-Path $raiz '.venv'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
  Write-Host 'Criando o ambiente Python...'
  & $py[0] $py[1..9] -m venv $venv
}
$vpy = Join-Path $venv 'Scripts\python.exe'
Write-Host 'Instalando os pacotes (a primeira vez demora: o Whisper e as bibliotecas da placa NVIDIA são grandes)...'
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r (Join-Path $raiz 'requirements.txt') --quiet
if ($LASTEXITCODE -ne 0) { Write-Host 'Falha ao instalar os pacotes.' -ForegroundColor Red; exit 1 }

# 3. ffmpeg 8.0.1 (não atualizar: o 9 exige driver NVIDIA 610+)
function Baixar-Zip($url, $destino, $nome) {
  if (Test-Path $destino) { Write-Host "$nome já instalado."; return }
  Write-Host "Baixando $nome..."
  $zip = Join-Path $tools "$nome.zip"
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
  Expand-Archive -Path $zip -DestinationPath $destino -Force
  Remove-Item $zip
}
Baixar-Zip 'https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/ffmpeg-8.0.1-full_build.zip' (Join-Path $tools 'ffmpeg') 'ffmpeg 8.0.1'
Baixar-Zip 'https://github.com/lay295/TwitchDownloader/releases/download/1.56.5/TwitchDownloaderCLI-1.56.5-Windows-x64.zip' (Join-Path $tools 'TwitchDownloader') 'TwitchDownloader 1.56.5'

Write-Host ''
Write-Host 'Pronto. Dê dois cliques em abrir_painel.cmd.' -ForegroundColor Green
Write-Host 'Para ver lives e clipes: Configurações > Twitch (Client ID + conectar a conta).'
