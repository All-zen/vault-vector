# Isola em qual camada o servico HTTP esta morrendo: no codigo Python, no
# executavel que o pip gerou, ou na tarefa agendada. Cada etapa e a anterior
# mais uma camada, entao a primeira que falhar e a culpada.
#
#   powershell -ExecutionPolicy Bypass -File .\diagnostico-servico.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$porta   = if ($env:VAULT_RAG_PORT) { $env:VAULT_RAG_PORT } else { 8765 }
$log     = Join-Path $root "servico.log"
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$svcExe  = Join-Path $root ".venv\Scripts\vault-vector-servico.exe"
$TAREFA  = "vault-vector servico"

function Nossos {
    # So processos de dentro desta pasta: nao encosta em python de outro projeto.
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path -like "$root\*" }
}

function Limpar {
    Nossos | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Remove-Item $log -Force -ErrorAction SilentlyContinue
}

function Veredito($rotulo) {
    Start-Sleep -Seconds 10
    $temLog = Test-Path $log
    $status = "recusou"
    try {
        $status = (Invoke-WebRequest "http://127.0.0.1:$porta/saude" -UseBasicParsing -TimeoutSec 3).StatusCode
    } catch { }
    $vivos = @(Nossos).Count
    $cor = if ($status -eq 200) { "Green" } else { "Red" }
    Write-Host ("  {0,-18} porta={1,-9} log={2,-6} processos={3}" -f $rotulo, $status, $temLog, $vivos) -ForegroundColor $cor
    if ($temLog) {
        Get-Content $log -Tail 20 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
    } else {
        Write-Host "      (nenhum servico.log: o processo nao chegou a rodar Python)" -ForegroundColor DarkGray
    }
    Write-Host ""
}

Write-Host ""
Write-Host "Porta $porta - cada etapa adiciona uma camada" -ForegroundColor Cyan
Write-Host ""

# 1) o codigo puro, chamado pelo interpretador sem janela
Limpar
Start-Process -FilePath $pythonw -ArgumentList "-m", "vault_rag.cli", "servico" -WorkingDirectory $root
Veredito "1. pythonw -m"

# 2) o mesmo codigo, mas pelo .exe que o pip gerou
Limpar
if (Test-Path $svcExe) {
    Start-Process -FilePath $svcExe -WorkingDirectory $root
    Veredito "2. .exe na mao"
} else {
    Write-Host "  2. .exe na mao      NAO EXISTE: $svcExe" -ForegroundColor Red
    Write-Host ""
}

# 3) o mesmo .exe, mas disparado pelo Agendador de Tarefas
Limpar
$t = Get-ScheduledTask -TaskName $TAREFA -ErrorAction SilentlyContinue
if ($t) {
    Start-ScheduledTask -TaskName $TAREFA
    Veredito "3. tarefa agendada"
    Write-Host "  Estado da tarefa:" -ForegroundColor Cyan
    Get-ScheduledTask -TaskName $TAREFA | Get-ScheduledTaskInfo |
        Select-Object LastRunTime, LastTaskResult, NumberOfMissedRuns | Format-List
    $t.Actions | Select-Object Execute, Arguments, WorkingDirectory | Format-List
    $t.Principal | Select-Object UserId, LogonType, RunLevel | Format-List
} else {
    Write-Host "  3. tarefa agendada  NAO REGISTRADA" -ForegroundColor Red
}

Write-Host "Leitura:" -ForegroundColor Cyan
Write-Host "  1 falhou           -> o problema e no codigo; o servico.log diz qual"
Write-Host "  1 ok, 2 falhou     -> o .exe do pip nao roda (antivirus e o suspeito)"
Write-Host "  2 ok, 3 falhou     -> e a tarefa: permissao, usuario ou caminho"
Write-Host "  tudo ok            -> resolvido; deixe rodando"
Write-Host ""
