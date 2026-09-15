# Descobre COMO o bge-reranker-v2-m3 pode ser chamado nesta maquina.
# Nao altera nada. So mede e reporta.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$MODELO = 'qllama/bge-reranker-v2-m3'
$OLLAMA = 'http://127.0.0.1:11434'

function Titulo($t) { Write-Host ''; Write-Host "== $t ==" -ForegroundColor Cyan }

Titulo 'Ollama'
try {
    $v = (Invoke-RestMethod "$OLLAMA/api/version" -TimeoutSec 5).version
    Write-Host "  versao: $v"
} catch { Write-Host '  Ollama nao respondeu. O resto do teste depende dele.' -ForegroundColor Red; exit 1 }

$temModelo = $false
try {
    $tags = (Invoke-RestMethod "$OLLAMA/api/tags" -TimeoutSec 10).models
    $temModelo = [bool]($tags | Where-Object { $_.name -like "*bge-reranker*" })
    Write-Host "  modelo reranker instalado: $temModelo"
} catch { Write-Host '  nao consegui listar os modelos' -ForegroundColor Yellow }

# ---------------------------------------------------------------
# 1. O Ollama ganhou endpoint de rerank? (PR #7219 estava parada)
# ---------------------------------------------------------------
Titulo 'Endpoint nativo de rerank'
$achou = $null
foreach ($rota in '/api/rerank', '/v1/rerank', '/api/reranker') {
    $corpo = @{ model = $MODELO; query = 'capital da Franca'
                documents = @('Paris e a capital da Franca.', 'O gato dorme no sofa.') } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod "$OLLAMA$rota" -Method Post -Body $corpo -ContentType 'application/json' -TimeoutSec 30
        Write-Host "  $rota RESPONDEU:" -ForegroundColor Green
        $r | ConvertTo-Json -Depth 4 | Write-Host
        $achou = $rota; break
    } catch {
        $cod = $_.Exception.Response.StatusCode.value__
        Write-Host "  $rota -> HTTP $cod"
    }
}

# ---------------------------------------------------------------
# 2. /api/embed serve? Se o pooling for 'rank', a dimensao e 1 e o
#    valor E o score. Se vier 1024, e embedding comum e nao serve.
#    Teste com par relevante x par irrelevante, mesmo formato.
# ---------------------------------------------------------------
Titulo 'Via /api/embed (o Ollama classifica este modelo como embedding)'
$SEP = '</s></s>'
$pares = @(
    @{ nome = 'RELEVANTE  '; txt = "capital da Franca$SEP" + 'Paris e a capital e maior cidade da Franca.' },
    @{ nome = 'IRRELEVANTE'; txt = "capital da Franca$SEP" + 'O gato dorme no sofa da sala o dia inteiro.' }
)
$vals = @{}
foreach ($p in $pares) {
    $corpo = @{ model = $MODELO; input = $p.txt } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod "$OLLAMA/api/embed" -Method Post -Body $corpo -ContentType 'application/json' -TimeoutSec 60
        $vetor = $r.embeddings[0]
        $dim = $vetor.Count
        Write-Host ("  {0}  dim={1}  primeiros valores: {2}" -f $p.nome, $dim, (($vetor | Select-Object -First 3) -join ', '))
        $vals[$p.nome.Trim()] = @{ dim = $dim; v0 = $vetor[0] }
    } catch {
        Write-Host ("  {0}  ERRO: {1}" -f $p.nome, $_.Exception.Message) -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------
# 3. O GGUF ja esta no disco. Onde?
# ---------------------------------------------------------------
Titulo 'Blob GGUF baixado (para reaproveitar com llama-server)'
$raiz = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { Join-Path $env:USERPROFILE '.ollama\models' }
$man = Join-Path $raiz 'manifests\registry.ollama.ai\qllama\bge-reranker-v2-m3'
if (Test-Path $man) {
    Get-ChildItem $man -File | ForEach-Object {
        $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
        foreach ($c in $j.layers) {
            if ($c.mediaType -like '*model*') {
                $blob = Join-Path $raiz ('blobs\' + ($c.digest -replace ':', '-'))
                $mb = if (Test-Path $blob) { [math]::Round((Get-Item $blob).Length / 1MB) } else { '?' }
                Write-Host "  tag '$($_.Name)' -> $blob  ($mb MB)"
            }
        }
    }
} else {
    Write-Host "  manifest nao encontrado em $man" -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'llama-server disponivel no PATH? ' -NoNewline
if (Get-Command llama-server -ErrorAction SilentlyContinue) { Write-Host 'SIM' -ForegroundColor Green }
else { Write-Host 'nao' -ForegroundColor Yellow }

# ---------------------------------------------------------------
Titulo 'VEREDITO'
if ($achou) {
    Write-Host "  Rerank nativo funciona em $achou. E a rota mais simples." -ForegroundColor Green
} elseif ($vals['RELEVANTE'] -and $vals['RELEVANTE'].dim -eq 1) {
    $a = $vals['RELEVANTE'].v0; $b = $vals['IRRELEVANTE'].v0
    Write-Host "  /api/embed devolve dimensao 1: o valor E o score do cross-encoder."
    Write-Host ("  relevante={0}  irrelevante={1}" -f $a, $b)
    if ($a -gt $b) { Write-Host '  E separou certo. Da para usar o Ollama direto.' -ForegroundColor Green }
    else { Write-Host '  Mas NAO separou. O formato do par esta errado ou o GGUF nao tem a cabeca de rank.' -ForegroundColor Red }
} elseif ($vals['RELEVANTE']) {
    Write-Host ("  /api/embed devolve dimensao {0}: e embedding comum, nao score." -f $vals['RELEVANTE'].dim) -ForegroundColor Yellow
    Write-Host '  O Ollama nao serve este modelo como reranker. Caminho: llama-server com --reranking --pooling rank,'
    Write-Host '  apontando para o GGUF acima (sem baixar de novo), numa porta separada.'
} else {
    Write-Host '  Nenhuma das rotas respondeu. Ver os erros acima.' -ForegroundColor Red
}
Write-Host ''
