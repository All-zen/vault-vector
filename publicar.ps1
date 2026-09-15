# Publica o vault-vector no GitHub: cria o repositorio, configura e sobe.
#
# Pre-requisito: GitHub CLI instalado e autenticado.
#   winget install GitHub.cli
#   gh auth login
#
#   powershell -ExecutionPolicy Bypass -File .\publicar.ps1 -Simular
#   powershell -ExecutionPolicy Bypass -File .\publicar.ps1
#
# Opcoes:
#   -Nome        nome do repositorio (padrao: vault-vector)
#   -Privado     cria privado; abra depois com 'gh repo edit --visibility public'
#   -Simular     mostra tudo que faria, sem criar nada

param(
    [string]$Nome = "vault-vector",
    [switch]$Privado,
    [switch]$Simular
)

$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $raiz

function Titulo($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }
function Ok($t)     { Write-Host "  ok    $t" -ForegroundColor Green }
function Erro($t)   { Write-Host "  X     $t" -ForegroundColor Red }
function Nada($t)   { Write-Host "  -     $t" -ForegroundColor DarkGray }

$DESCRICAO = "Busca semantica e escrita nas suas notas markdown, via MCP. Roda local: Ollama + SQLite, nada vai para a nuvem."
$TOPICOS = @("mcp", "rag", "obsidian", "claude", "semantic-search", "local-first",
             "ollama", "sqlite", "embeddings", "python", "knowledge-base")

# ----------------------------------------------------- 1/5 pre-requisitos
Titulo "1/5  Pre-requisitos"

foreach ($cmd in @("git", "gh")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { Ok "$cmd encontrado" }
    else {
        Erro "$cmd nao encontrado"
        if ($cmd -eq "gh") { Write-Host "        winget install GitHub.cli" }
        exit 1
    }
}

$conta = & gh api user --jq .login 2>$null
if ($LASTEXITCODE -ne 0 -or -not $conta) {
    Erro "gh nao esta autenticado"
    Write-Host "        rode: gh auth login"
    exit 1
}
Ok "autenticado como $conta"

# ------------------------------------------------- 2/5 nada pessoal vaza
Titulo "2/5  Verificacao de vazamento"

& python ferramentas/verificar_vazamento.py
if ($LASTEXITCODE -ne 0) {
    Erro "achei dado pessoal no repositorio - NAO vou publicar"
    Write-Host "        corrija os itens acima e rode de novo."
    exit 1
}
Ok "nenhum dado pessoal"

# -------------------------------------------------------- 3/5 os testes
Titulo "3/5  Suite de testes"

& python selftest.py 2>&1 | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) {
    Erro "os testes falharam - corrija antes de publicar"
    exit 1
}
Ok "suite passou"

# ------------------------------------------------------------ 4/5 o git
Titulo "4/5  Repositorio local"

if (-not (Test-Path ".git")) {
    if ($Simular) { Nada "simulacao: rodaria git init" }
    else {
        & git init -b main | Out-Null
        Ok "git init"
    }
} else {
    Ok "ja e um repositorio git"
}

# Antes de commitar: conferir que nada ignorado entrou por engano.
if (-not $Simular) {
    & git add -A
    $arquivos = & git diff --cached --name-only
    $perigosos = $arquivos | Where-Object {
        $_ -match "\.db$|\.token$|^config\.toml$|servico\.log|^perguntas"
    }
    if ($perigosos) {
        Erro "estes arquivos NAO deveriam ir, e entraram no commit:"
        $perigosos | ForEach-Object { Write-Host "        $_" -ForegroundColor Red }
        Write-Host "        confira o .gitignore. Desfazendo o 'git add'."
        & git reset | Out-Null
        exit 1
    }
    Ok "$($arquivos.Count) arquivo(s) no commit, nenhum perigoso"
}

# -------------------------------------------------------- 5/5 o GitHub
Titulo "5/5  GitHub"

$visibilidade = "--public"
if ($Privado) { $visibilidade = "--private" }

if ($Simular) {
    $null = & gh repo view "$conta/$Nome" --json name 2>$null
    if ($LASTEXITCODE -eq 0) {
        Nada "simulacao: $conta/$Nome ja existe - enviaria o conteudo para la"
    } else {
        Nada "simulacao: criaria $conta/$Nome ($visibilidade)"
    }
    Write-Host "        descricao: $DESCRICAO"
    Write-Host "        topicos:   $($TOPICOS -join ', ')"
    Write-Host ""
    Write-Host "  Rode sem -Simular para publicar." -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

& git commit -m "vault-vector: memoria local para o Claude, via MCP" | Out-Null
Ok "commit criado"

$null = & gh repo view "$conta/$Nome" --json name 2>$null
$jaExiste = ($LASTEXITCODE -eq 0)

if ($jaExiste) {
    # Repositorio ja criado pela interface web: so falta o conteudo.
    Ok "$conta/$Nome ja existe - vou apenas enviar"
    $remotos = & git remote 2>$null
    if ($remotos -notcontains "origin") {
        & git remote add origin "https://github.com/$conta/$Nome.git"
        Ok "remote origin apontado"
    }
    & git branch -M main
    & git push -u origin main
    if ($LASTEXITCODE -ne 0) {
        Erro "git push falhou"
        Write-Host "        se o repositorio nao estiver vazio, rode:"
        Write-Host "          git pull --rebase origin main"
        exit 1
    }
    Ok "enviado"
} else {
    & gh repo create $Nome $visibilidade --source=. --push --description $DESCRICAO
    if ($LASTEXITCODE -ne 0) { Erro "gh repo create falhou"; exit 1 }
    Ok "repositorio criado e enviado"
}

foreach ($t in $TOPICOS) { & gh repo edit "$conta/$Nome" --add-topic $t 2>$null | Out-Null }
Ok "$($TOPICOS.Count) topicos adicionados"

# Repositorio de portfolio nao precisa de wiki nem de projects, e desligar
# deixa a pagina mais limpa para quem chega pela primeira vez.
& gh repo edit "$conta/$Nome" --enable-wiki=false --enable-projects=false 2>$null | Out-Null
Ok "wiki e projects desligados"

Write-Host ""
Write-Host "  https://github.com/$conta/$Nome" -ForegroundColor Cyan
Write-Host ""
Write-Host "  O CI comeca a rodar sozinho. Acompanhe em:"
Write-Host "    gh run watch"
Write-Host ""
