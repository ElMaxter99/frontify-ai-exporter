<#
 Frontify Exporter: one command, no UI. Windows PowerShell 5+ / PowerShell 7 (also works on macOS/Linux with pwsh).
   .\export.ps1 -Url https://cliente.frontify.com -Token <TOKEN> [-Name CLIENTE_01] [-Concurrency 4]
 Token: -Token, or the FRONTIFY_TOKEN env var, or a .env file next to this script. URL: -Url or FRONTIFY_URL.
 Builds the image, runs the export, writes to .\EXPORTS and removes the container when finished.
 If scripts are blocked:  powershell -ExecutionPolicy Bypass -File .\export.ps1 -Url ... -Token ...
#>
param([string]$Url, [string]$Token, [string]$Name, [int]$Concurrency = 4)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path .env) {
  Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$' -and -not $_.TrimStart().StartsWith('#')) {
      if (-not [Environment]::GetEnvironmentVariable($Matches[1])) { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"').Trim("'")) }
    }
  }
}
if (-not $Url)   { $Url   = $env:FRONTIFY_URL }
if (-not $Token) { $Token = $env:FRONTIFY_TOKEN }
if (-not $Url)   { Write-Error "Missing Frontify URL (-Url or FRONTIFY_URL)"; exit 2 }
if (-not $Token) { Write-Error "Missing token (-Token or FRONTIFY_TOKEN)"; exit 2 }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker is not installed: https://docs.docker.com/get-docker/"; exit 3 }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error "Docker is installed but not running. Start Docker Desktop and retry."; exit 3 }

New-Item -ItemType Directory -Force EXPORTS | Out-Null
$args2 = @("python","-m","src","export","--url",$Url,"--dest","/exports","--concurrency","$Concurrency")
if ($Name) { $args2 += @("--name",$Name) }

# The token travels via the environment, not the command line.
$env:FRONTIFY_TOKEN = $Token
$ErrorActionPreference = "Continue"
docker compose run --rm --build -e FRONTIFY_TOKEN frontify-exporter @args2
$rc = $LASTEXITCODE
docker compose down --remove-orphans *> $null
Write-Host ""
Write-Host "Results: $(Join-Path $PWD 'EXPORTS')   (report: EXPORT_REPORT.json inside the client folder)"
if ($rc -eq 0) { Write-Host "Finished without errors." } else { Write-Host "Finished with errors or failures (exit $rc). See EXPORT_REPORT.json." }
exit $rc
