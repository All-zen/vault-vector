# Deixa o vault-vector disponivel sem ritual: Ollama sobe com o Windows, o modelo
# fica quente, e o indice se mantem em dia sozinho.
#
#   powershell -ExecutionPolicy Bypass -File .\instalar-servicos.ps1
#
# Opcoes:
#   -KeepAlive "2h"     quanto tempo o modelo fica na RAM apos o ultimo uso.
#                       "-1" = para sempre (busca sempre instantanea, ~2,2 GB
#                       ocupados). "2h" cobre o expediente e libera a noite.
#                       Padrao: 2h
#   -ReindexAt "07:30"  horario da reindexacao diaria. Padrao: 07:30
#   -Porta 8765         porta do servidor HTTP local (so 127.0.0.1)
#   -Headless           em vez do app de desktop, o servidor sem janela numa
#                       tarefa agendada (o jeito antigo, para quem nao quer GUI)
#   -SemServico         nao sobe servidor nenhum; fica so no modo stdio
#   -Desinstalar        remove o que foi instalado aqui
#
# Idempotente: rodar de novo so atualiza o que mudou.

param(
    [string]$KeepAlive = "2h",
    [string]$ReindexAt = "07:30",
    [int]$Porta = 8765,
    [switch]$Headless,
    [switch]$SemServico,
    [switch]$Desinstalar
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$exe    = Join-Path $root ".venv\Scripts\vault-vector.exe"
$TAREFA_REINDEX = "vault-vector reindex"
$TAREFA_SERVICO = "vault-vector servico"
$servicoExe = Join-Path $root ".venv\Scripts\vault-vector-servico.exe"
$appExe = Join-Path $root ".venv\Scripts\vault-vector-app.exe"

function Passo($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }
function Ok($t)    { Write-Host "  ok   $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  !    $t" -ForegroundColor Yellow }

# ------------------------------------------------------------- desinstalar
if ($Desinstalar) {
    Passo "Removendo tarefas agendadas"
    foreach ($nome in @($TAREFA_REINDEX, $TAREFA_SERVICO)) {
        $t = Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
        if ($t) {
            Unregister-ScheduledTask -TaskName $nome -Confirm:$false
            Ok "removida: $nome"
        } else {
            Write-Host "  -    nao existia: $nome"
        }
    }
    $lnkSvc = Join-Path ([Environment]::GetFolderPath("Startup")) "vault-vector servico.lnk"
    if (Test-Path $lnkSvc) { Remove-Item $lnkSvc -Force; Ok "atalho de inicializacao removido" }
    Get-Process vault-vector-servico -ErrorAction SilentlyContinue | Stop-Process -Force
    if (Test-Path $venvPy) {
        & $venvPy -c "from vault_rag import autostart; autostart.desligar()"
        Ok "app nao abre mais com o Windows"
    }
    Get-Process vault-vector-app -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host ""
    Write-Host "As variaveis OLLAMA_* continuam definidas. Para limpar:" -ForegroundColor Gray
    Write-Host '  [Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE",$null,"User")' -ForegroundColor Gray
    exit 0
}

if (-not (Test-Path $exe)) {
    Write-Host "vault-vector nao instalado. Rode setup.ps1 primeiro." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------ 1/4 Ollama no boot
Passo "1/4  Ollama iniciando com o Windows"

$startup = [Environment]::GetFolderPath("Startup")
$atalho  = Join-Path $startup "Ollama.lnk"
$ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"

if (Test-Path $atalho) {
    Ok "atalho ja existe na pasta Inicializar"
} elseif (Test-Path $ollamaApp) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($atalho)
    $lnk.TargetPath = $ollamaApp
    $lnk.Description = "Ollama (necessario para a busca do vault)"
    $lnk.Save()
    Ok "atalho criado: $atalho"
} else {
    Aviso "nao achei '$ollamaApp'"
    Write-Host "       Se o Ollama ja sobe sozinho (icone na bandeja apos reiniciar),"
    Write-Host "       ignore. Senao, adicione o atalho manualmente em shell:startup."
}

# ------------------------------------------------------- 2/4 modelo quente
Passo "2/4  Tempo que o modelo fica na memoria"

$atual = [Environment]::GetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "User")
if ($atual -eq $KeepAlive) {
    Ok "OLLAMA_KEEP_ALIVE ja esta em $KeepAlive"
} else {
    [Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", $KeepAlive, "User")
    Ok "OLLAMA_KEEP_ALIVE = $KeepAlive (antes: $(if ($atual) { $atual } else { 'padrao 5m' }))"
    Aviso "reinicie o Ollama pela bandeja para valer"
}

# --------------------------------------------------- 3/4 reindexacao diaria
Passo "3/4  Reindexacao diaria as $ReindexAt"

$acaoReindex = New-ScheduledTaskAction -Execute $exe -Argument "index --quiet" -WorkingDirectory $root
$gatilho = New-ScheduledTaskTrigger -Daily -At $ReindexAt
# Nao roda com a maquina na bateria nem atrasa o logon
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)

$existente = Get-ScheduledTask -TaskName $TAREFA_REINDEX -ErrorAction SilentlyContinue
if ($existente) { Unregister-ScheduledTask -TaskName $TAREFA_REINDEX -Confirm:$false }
Register-ScheduledTask -TaskName $TAREFA_REINDEX -Action $acaoReindex -Trigger $gatilho `
    -Settings $opcoes -Description "Mantem o indice do vault-vector em dia" | Out-Null
Ok "tarefa '$TAREFA_REINDEX' registrada"
Write-Host "       StartWhenAvailable: se o PC estiver desligado no horario, roda no proximo boot"

# --------------------------------------------------- 4/4 servico HTTP local
Passo "4/4  Servidor local (porta $Porta)"

$antigo = Get-ScheduledTask -TaskName $TAREFA_SERVICO -ErrorAction SilentlyContinue
if ($antigo) { Unregister-ScheduledTask -TaskName $TAREFA_SERVICO -Confirm:$false }

if ($SemServico) {
    Write-Host "  -    pulado (-SemServico). O MCP continua funcionando em stdio."
} elseif (-not $Headless) {
    # O app de desktop e o servidor: MCP, API e interface no mesmo processo,
    # com o icone da bandeja como sinal de vida. Substitui a tarefa agendada
    # do servidor headless, que disputaria a mesma porta.
    if (-not (Test-Path $appExe)) {
        Aviso "vault-vector-app.exe nao existe - rode setup.ps1 de novo"
    } else {
        Get-Process vault-vector-servico -ErrorAction SilentlyContinue | Stop-Process -Force
        $env:VAULT_RAG_PORT = "$Porta"
        [Environment]::SetEnvironmentVariable("VAULT_RAG_PORT", "$Porta", "User")
        & $venvPy -c "from vault_rag import autostart; autostart.ligar()"
        Ok "o app abre com o Windows, escondido na bandeja"
        if (-not (Get-Process vault-vector-app -ErrorAction SilentlyContinue)) {
            Start-Process -FilePath $appExe -ArgumentList "--escondido" -WorkingDirectory $root
        }
        $subiu = $false
        for ($i = 1; $i -le 20; $i++) {
            Start-Sleep -Seconds 1
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Porta/saude" -TimeoutSec 3 -UseBasicParsing
                if ($r.StatusCode -eq 200) { $subiu = $true; break }
            } catch { }
        }
        if ($subiu) {
            Ok "respondendo em http://127.0.0.1:$Porta (interface e MCP)"
            Write-Host "       Ctrl+Alt+Espaco abre a janela de qualquer programa."
        } else {
            Aviso "o app nao respondeu em 20s. Veja o app.log nesta pasta."
        }
    }
} elseif (-not (Test-Path $servicoExe)) {
    Aviso "vault-vector-servico.exe nao existe - rode setup.ps1 de novo para recria-lo"
} else {
    $acaoSvc = New-ScheduledTaskAction -Execute $servicoExe -WorkingDirectory $root
    # -AtLogOn sem -User vale para TODOS os usuarios da maquina, e isso exige
    # admin. Amarrando ao usuario atual, registra sem elevacao nenhuma.
    $euSou = "$env:USERDOMAIN\$env:USERNAME"
    $gatilhoLogon = New-ScheduledTaskTrigger -AtLogOn -User $euSou
    $gatilhoLogon.Delay = "PT1M"
    # Sobe de novo sozinho se cair, e nunca expira
    $opcoesSvc = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries
    $env:VAULT_RAG_PORT = "$Porta"
    [Environment]::SetEnvironmentVariable("VAULT_RAG_PORT", "$Porta", "User")


    $registrou = $false
    try {
        Register-ScheduledTask -TaskName $TAREFA_SERVICO -Action $acaoSvc -Trigger $gatilhoLogon `
            -Settings $opcoesSvc -User $euSou `
            -Description "vault-vector: um processo HTTP servindo todos os clientes MCP" | Out-Null
        $registrou = $true
        Ok "tarefa '$TAREFA_SERVICO' registrada (1 min apos o logon, reinicia sozinha se cair)"
    } catch {
        Aviso "sem permissao para criar a tarefa agendada: $($_.Exception.Message)"
        Write-Host "       Usando a pasta Inicializar no lugar - funciona sem privilegio,"
        Write-Host "       so nao reinicia sozinho se o processo cair."
        $lnkSvc = Join-Path $startup "vault-vector servico.lnk"
        $ws2 = New-Object -ComObject WScript.Shell
        $l2 = $ws2.CreateShortcut($lnkSvc)
        $l2.TargetPath = $servicoExe
        $l2.WorkingDirectory = $root
        $l2.Description = "vault-vector: servidor MCP local"
        $l2.Save()
        Ok "atalho criado: $lnkSvc"
    }

    if ($registrou) { Start-ScheduledTask -TaskName $TAREFA_SERVICO }
    else { Start-Process -FilePath $servicoExe -WorkingDirectory $root -WindowStyle Hidden }

    # Carregar numpy e a matriz do indice leva alguns segundos; vale esperar
    # de verdade em vez de chutar um sleep fixo.
    $subiu = $false
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Porta/saude" -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { $subiu = $true; break }
        } catch { }
        if ($i % 5 -eq 0) { Write-Host "       esperando... ($($i*2)s)" }
    }
    if ($subiu) {
        Ok "servico respondendo em http://127.0.0.1:$Porta"
    } else {
        Aviso "servico nao respondeu em 40s"
        Write-Host "       O que ele escreveu antes de morrer:"
        Write-Host "         Get-Content .\servico.log -Tail 30"
        Write-Host "       Ou rode em primeiro plano para ver ao vivo:"
        Write-Host "         .\.venv\Scripts\vault-vector.exe serve --http"
    }

    Write-Host ""
    Write-Host "Bloco para o Claude Desktop / .mcp.json:" -ForegroundColor Cyan
    # Sem 2>&1: o PowerShell transformaria stderr em erro terminante.
    & (Join-Path $root ".venv\Scripts\vault-vector.exe") token --port $Porta
}

# ------------------------------------------------------------------- final
Passo "Verificando"
& $exe doctor
$saida = $LASTEXITCODE

Write-Host ""
if ($saida -eq 0) {
    Write-Host "Tudo no lugar." -ForegroundColor Green
} else {
    Write-Host "Veja os itens marcados acima." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "A qualquer momento:" -ForegroundColor Gray
Write-Host "  .\.venv\Scripts\vault-vector.exe doctor        diagnostico completo"
Write-Host "  .\.venv\Scripts\vault-vector-app.exe          abre a janela (ou Ctrl+Alt+Espaco)"
Write-Host "  Get-ScheduledTask 'vault-vector*'              estado das tarefas"
Write-Host "  Get-ScheduledTask 'vault-vector*' | Start-ScheduledTask   sobe o servico na hora"
Write-Host "  .\instalar-servicos.ps1 -Desinstalar        remove as tarefas"
