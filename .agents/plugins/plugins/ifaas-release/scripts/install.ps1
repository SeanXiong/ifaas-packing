$ErrorActionPreference = 'Stop'
$marketplaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'codex command was not found. Install or update Codex CLI first.'
}

& codex plugin marketplace add $marketplaceRoot
if ($LASTEXITCODE -ne 0) { throw 'Failed to register the IFAAS marketplace.' }

& codex plugin add 'ifaas-release@ifaas-tools'
if ($LASTEXITCODE -ne 0) { throw 'Failed to install the ifaas-release plugin.' }

Write-Host 'IFAAS Release installed.'
Write-Host 'Set IFAAS_BUILD_PLATFORM_URL and IFAAS_BUILD_PLATFORM_TOKEN, then start a new Codex task and use $ifaas-release.'
