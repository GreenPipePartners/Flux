$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $RootDir "web\Flux"
$FieldConfig = Join-Path $WebDir "field\field-config.json"
$FieldProject = Join-Path $RootDir "field\Flux.FieldAgent\Flux.FieldAgent.csproj"
$Processes = @()

function Invoke-WebCommand {
    param([string[]]$Arguments)

    Push-Location $WebDir
    try {
        & uv @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: uv $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Start-FluxService {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )

    Write-Host "[$Name] starting..."
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -PassThru

    $script:Processes += [PSCustomObject]@{
        Name = $Name
        Process = $process
    }
}

function Wait-FluxUrl {
    param(
        [string]$Url,
        [string]$Name,
        [int]$Attempts = 60
    )

    Write-Host -NoNewline "Waiting for $Name at $Url"
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 *> $null
            Write-Host ""
            return
        }
        catch {
            Write-Host -NoNewline "."
            Start-Sleep -Seconds 1
        }
    }

    Write-Host ""
    throw "Timed out waiting for $Name at $Url"
}

function Stop-FluxServices {
    if ($script:Processes.Count -eq 0) {
        return
    }

    Write-Host ""
    Write-Host "Stopping Flux services..."
    foreach ($entry in $script:Processes) {
        $process = $entry.Process
        if ($null -ne $process -and -not $process.HasExited) {
            & taskkill.exe /PID $process.Id /T /F *> $null
        }
    }
}

try {
    Write-Host "Preparing Flux database and FieldAgent config..."
    Invoke-WebCommand @("run", "python", "manage.py", "migrate")
    Invoke-WebCommand @("run", "python", "manage.py", "repair_sequences", "base")
    Invoke-WebCommand @("run", "python", "manage.py", "install_fluxolot_fishtank")
    Invoke-WebCommand @("run", "python", "manage.py", "export_field_config", "--output", "field/field-config.json")

    Write-Host "Starting Flux stack..."
    & (Join-Path $RootDir "scripts\questdb-start.ps1")
    $env:PYTHONPATH = "$WebDir\src;$RootDir"
    Start-FluxService "django" "uv" @("run", "waitress-serve", "--listen=*:8000", "--threads=16", "flux.wsgi:application") $WebDir
    Wait-FluxUrl "http://localhost:8000/" "Django"
    Start-FluxService "field" "dotnet" @("run", "--project", $FieldProject, "--FluxField:ConfigPath=$FieldConfig") $RootDir
    Start-FluxService "serve-monitor" "uv" @("run", "python", "manage.py", "flux_serve_monitor") $WebDir
    Start-FluxService "fluxolot-sampler" "uv" @("run", "python", "manage.py", "flux_sampling_worker", "--profile", "fluxolot-fishtank") $WebDir

    Write-Host ""
    Write-Host "Flux stack is running. Open http://localhost:8000/live/ or http://localhost:8000/sim/."
    Write-Host "Press Ctrl-C to stop all Flux services."
    Write-Host ""

    while ($true) {
        foreach ($entry in $script:Processes) {
            if ($entry.Process.HasExited) {
                $exitCode = $entry.Process.ExitCode
                Write-Host ""
                Write-Host "Flux service '$($entry.Name)' exited with status $exitCode. Shutting down the rest."
                exit $exitCode
            }
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Stop-FluxServices
}
