$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$HostAddr = $env:INCOURT_SERVER_HOST
if (-not $HostAddr) { $HostAddr = "127.0.0.1" }
$Port = $env:INCOURT_SERVER_PORT
if (-not $Port) { $Port = "8777" }

$Python = Join-Path $Root ".venv-incourt\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
  $Python = "python"
}

& $Python -m uvicorn incourt_listener.streaming_server:app --host $HostAddr --port $Port
