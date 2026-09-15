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
& $venvPy -m pip install -e . --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Falhou ao instalar as dependencias."
    Write-Host "Rode sem --quiet para ver o erro completo:"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -e ."
    exit 1
}
Write-Host "  ok"

Write-Host "  rodando o autoteste..."
& $venvPy selftest.py
if ($LASTEXITCODE -ne 0) {
    Write-Fail "O autoteste falhou. Nao siga sem resolver isso."
    exit 1
}

# --------------------------------------------------------------- 4/5 Ollama
Write-Step "4/5  Ollama e modelo de embedding"

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($null -eq $ollama) {
    Write-Fail "Ollama nao encontrado."
    Write-Host "Instale em https://ollama.com/download e rode este script de novo."
    Write-Host "O resto ja esta pronto: nada se perde."
    exit 1
}

$modelos = (& ollama list 2>$null) -join "`n"
if ($modelos -notmatch "bge-m3") {
    Write-Host "  baixando bge-m3 (~1.2 GB, demora alguns minutos)..."
    & ollama pull bge-m3
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Falhou ao baixar o modelo. O servico do Ollama esta rodando?"
        exit 1
    }
} else {
    Write-Host "  bge-m3 ja esta baixado"
}

# ------------------------------------------------------------- 5/5 indexacao
Write-Step "5/5  Indexando o vault"
Write-Host "  A primeira vez demora (10 a 20 min para ~500 notas). As proximas"
Write-Host "  levam segundos, porque so o que mudou e reprocessado."
Write-Host ""

& $venvPy -m vault_rag.cli index
if ($LASTEXITCODE -ne 0) {
    Write-Fail "A indexacao falhou. Veja a mensagem acima."
    exit 1
}

# ---------------------------------------------------------------------- fim
Write-Host ""
Write-Host "Pronto." -ForegroundColor Green
Write-Host ""
Write-Host "Testar a busca:"
Write-Host "  .\.venv\Scripts\vault-vector.exe search `"sua pergunta aqui`""
Write-Host ""
Write-Host "Registrar como MCP (Claude Code):"
Write-Host "  claude mcp add vault-vector -- $venvPy -m vault_rag.server"
Write-Host ""
Write-Host "Ou no claude_desktop_config.json:"
Write-Host ('  "command": "' + $venvPy.Replace("\", "\\") + '", "args": ["-m", "vault_rag.server"]')
