$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$QuestDbVersion = if ($env:QUESTDB_VERSION) { $env:QUESTDB_VERSION } else { "9.3.5" }
$RuntimeDir = if ($env:FLUX_RUNTIME_DIR) { $env:FLUX_RUNTIME_DIR } else { Join-Path $RootDir ".runtime" }
$QuestDbDist = if ($env:FLUX_QUESTDB_DIST) { $env:FLUX_QUESTDB_DIST } else { Join-Path $RuntimeDir "questdb-dist" }
$QuestDbData = if ($env:FLUX_QUESTDB_DATA) { $env:FLUX_QUESTDB_DATA } else { Join-Path $RuntimeDir "questdb-data" }
$QuestDbPort = if ($env:QUESTDB_PORT) { [int]$env:QUESTDB_PORT } else { 8812 }
$QuestDbHttpPort = if ($env:QUESTDB_HTTP_PORT) { [int]$env:QUESTDB_HTTP_PORT } else { 9000 }

function Test-QuestDbPort {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $result = $client.BeginConnect("127.0.0.1", $QuestDbPort, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(1000)) {
            $client.Close()
            return $false
        }
        $client.EndConnect($result)
        $client.Close()
        return $true
    }
    catch {
        return $false
    }
}

if (Test-QuestDbPort) {
    Write-Host "QuestDB already listening on localhost:$QuestDbPort"
    exit 0
}

New-Item -ItemType Directory -Force -Path $RuntimeDir, $QuestDbDist, $QuestDbData *> $null

$QuestDbExe = Join-Path $QuestDbDist "questdb.exe"
if (-not (Test-Path $QuestDbExe)) {
    $Archive = Join-Path $RuntimeDir "questdb-$QuestDbVersion-no-jre-bin.tar.gz"
    $Url = "https://github.com/questdb/questdb/releases/download/$QuestDbVersion/questdb-$QuestDbVersion-no-jre-bin.tar.gz"
    Write-Host "Downloading QuestDB $QuestDbVersion..."
    Invoke-WebRequest -Uri $Url -OutFile $Archive
    tar -xzf $Archive -C $QuestDbDist --strip-components=1
}

if (-not $env:JAVA_HOME) {
    $Java = Get-Command java -ErrorAction SilentlyContinue
    if ($Java) {
        $env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $Java.Source)
    }
}

Write-Host "Starting QuestDB at $QuestDbData (PG wire localhost:$QuestDbPort, HTTP localhost:$QuestDbHttpPort)..."
& $QuestDbExe start -d $QuestDbData
if ($LASTEXITCODE -ne 0) {
    throw "QuestDB failed to start with exit code $LASTEXITCODE"
}

Write-Host -NoNewline "Waiting for QuestDB PG wire on localhost:$QuestDbPort"
for ($attempt = 1; $attempt -le 30; $attempt++) {
    if (Test-QuestDbPort) {
        Write-Host ""
        exit 0
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 1
}

Write-Host ""
throw "Timed out waiting for QuestDB on localhost:$QuestDbPort"
