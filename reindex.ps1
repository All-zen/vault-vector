# Reindexa o vault (incremental). Use no Agendador de Tarefas do Windows para
# manter o indice em dia sem pensar nisso.
#
# Agendar (uma vez, num PowerShell comum):
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" `
#          -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\ferramentas\vault-vector\reindex.ps1"
#   $t = New-ScheduledTaskTrigger -Daily -At 7am
#   Register-ScheduledTask -TaskName "vault-vector reindex" -Action $a -Trigger $t

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log  = Join-Path $root "reindex.log"

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  inicio" | Add-Content $log
try {
    & (Join-Path $root ".venv\Scripts\vault-vector.exe") index --quiet 2>&1 | Add-Content $log
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  ok" | Add-Content $log
} catch {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  ERRO: $_" | Add-Content $log
    exit 1
}
