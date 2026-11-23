# Atualiza o Vice Clips com a versão mais nova do GitHub, sem reinstalar: o ambiente (.venv) e os vídeos ficam como estão.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = 'https://github.com/Matheus-Ferrari/Gta/archive/refs/heads/main.zip'

if (Test-Path (Join-Path $raiz '.git')) {
  Write-Host 'Puxando a atualização pelo git...'
  git -C $raiz pull --ff-only
  if ($LASTEXITCODE -ne 0) { Write-Host 'O git não conseguiu atualizar (há mudanças locais?).' -ForegroundColor Red; exit 1 }
} else {
  Write-Host 'Baixando a versão nova do GitHub...'
  $tmp = Join-Path $env:TEMP ('viceclips_' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    $zip = Join-Path $tmp 'main.zip'
    Invoke-WebRequest -Uri $repo -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $novo = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
    # Copia por cima só o código; .venv e .git não são tocados.
    robocopy $novo.FullName $raiz /E /XD .venv .git /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'Falha ao copiar os arquivos novos.' }
  } finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
}

$vpy = Join-Path $raiz '.venv\Scripts\python.exe'
if (Test-Path $vpy) {
  Write-Host 'Conferindo os pacotes (rápido quando nada mudou)...'
  & $vpy -m pip install -r (Join-Path $raiz 'requirements.txt') --quiet
} else {
  Write-Host 'Ainda não instalado neste PC: rode instalar.cmd.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Atualizado. Feche a janela preta do painel (se estiver aberta) e abra de novo o abrir_painel.cmd.' -ForegroundColor Green
