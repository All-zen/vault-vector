# Setup do vault-vector no Windows.
#
#   cd C:\ferramentas\vault-vector
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# Compativel com Windows PowerShell 5.1 (o que vem no Windows) e com o
# PowerShell 7. Sem acentos de proposito: o 5.1 le arquivo UTF-8 sem BOM
# como ANSI e embaralharia os acentos na tela.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

function Write-Step($text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

function Write-Fail($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
}

# --------------------------------------------------------------- 1/5 Python
Write-Step "1/5  Procurando Python"

# Candidatos em ordem de preferencia. 'py -3' e o launcher oficial do Windows.
$candidatos = @(
    @{ exe = "py";      args = @("-3") },
    @{ exe = "python";  args = @() },
    @{ exe = "python3"; args = @() }
)

$python = $null
foreach ($c in $candidatos) {
    $cmd = Get-Command $c.exe -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { continue }

    # O alias da Microsoft Store existe no PATH mas so abre a loja.
    if ($cmd.Source -like "*WindowsApps*") {
        Write-Host "  ignorando o alias da Microsoft Store em $($cmd.Source)" -ForegroundColor DarkGray
        continue
    }

    $probe = @($c.args) + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")
    $versao = & $c.exe $probe 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($versao)) { continue }

    $partes = $versao.Trim().Split(".")
    $maior = [int]$partes[0]
    $menor = [int]$partes[1]
    Write-Host "  encontrado: $($c.exe) $($c.args -join ' ') -> Python $versao"

    if ($maior -eq 3 -and $menor -ge 9) {
        $python = $c
        $pyVersao = $versao.Trim()
        break
    }
    Write-Host "  (muito antigo, preciso de 3.9 ou superior)" -ForegroundColor DarkGray
}

if ($null -eq $python) {
    Write-Fail "Nenhum Python 3.9+ encontrado no PATH."
    Write-Host "Instale em https://www.python.org/downloads/ marcando 'Add Python to PATH'."
    exit 1
}
Write-Host "  usando Python $pyVersao" -ForegroundColor Green

# ------------------------------------------------------------------ 2/5 venv
Write-Step "2/5  Ambiente virtual"

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $argsVenv = @($python.args) + @("-m", "venv", ".venv")
    & $python.exe $argsVenv
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Falhou ao criar o ambiente virtual."
        exit 1
    }
    Write-Host "  criado em .venv"
} else {
    Write-Host "  ja existe, reaproveitando"
}

# --------------------------------------------------------------- 3/5 pacote
Write-Step "3/5  Instalando o pacote"

& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
# [desktop] traz a janela nativa e o icone da bandeja. Sem ele o servidor
# MCP funciona igual, so que sem o app.
& $venvPy -m pip install -e ".[desktop]" --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Falhou ao instalar as dependencias."
    Write-Host "Rode sem --quiet para ver o erro completo:"
    Write-Host '  .\.venv\Scripts\python.exe -m pip install -e ".[desktop]"'
    exit 1
}
Write-Host "  ok"

Write-Host "  rodando o autoteste..."
& $venvPy selftest.py
if ($LASTEXITCODE -ne 0) {
    Write-Fail "O autoteste falhou. Nao siga sem resolver isso."
    exit 1
}

# ------------------------------------------------------------ 4/5 interface
Write-Step "4/5  Compilando a interface"

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($null -eq $npm) {
    Write-Fail "Node.js nao encontrado: a interface e compilada com ele."
    Write-Host "Instale com:  winget install OpenJS.NodeJS.LTS"
    Write-Host "e rode este script de novo. O resto ja esta pronto."
    Write-Host ""
    Write-Host "Sem interface, o servidor MCP funciona igual:"
    Write-Host "  .\.venv\Scripts\vault-vector.exe init"
    exit 1
}
& npm --prefix ui ci --no-audit --no-fund --loglevel=error
if ($LASTEXITCODE -eq 0) { & npm --prefix ui run build --silent }
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Falhou ao compilar a interface. Veja o erro acima."
    exit 1
}
Write-Host "  ok, em vault_rag\static"

# ---------------------------------------------------------------- 5/5 abrir
Write-Step "5/5  Abrindo o app"

$appExe = Join-Path $root ".venv\Scripts\vault-vector-app.exe"
Start-Process -FilePath $appExe -WorkingDirectory $root
Write-Host "  O app abre num passo a passo: escolher a pasta das notas, conferir"
Write-Host "  o Ollama e o modelo, e indexar. Nada de editar arquivo de config."

# ---------------------------------------------------------------------- fim
Write-Host ""
Write-Host "Pronto." -ForegroundColor Green
Write-Host ""
Write-Host "Para o app abrir com o Windows, escondido na bandeja:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\instalar-servicos.ps1"
Write-Host "(ou o interruptor em Ajustes, dentro do app)"
Write-Host ""
Write-Host "Conectar ao Claude: a tela 'Conectar ao Claude' do app traz o comando"
Write-Host "pronto, com o endereco e o token desta maquina."
