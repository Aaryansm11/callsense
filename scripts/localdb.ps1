# Local Postgres for CallSense dev on Windows — no Docker, no system install.
# Uses the `callsense` conda env's Postgres binaries. Data dir: .pgdata (gitignored).
#
#   ./scripts/localdb.ps1 init       # one-time: initialise the data dir
#   ./scripts/localdb.ps1 start      # start the server (port 5432)
#   ./scripts/localdb.ps1 createdb   # create the callsense role + database
#   ./scripts/localdb.ps1 stop       # stop the server
#
# Assumes `conda` is on PATH. If not, activate/use the full path to conda first.

param([ValidateSet("init", "start", "stop", "createdb")] [string]$Action = "start")

$ErrorActionPreference = "Stop"
$EnvName = "callsense"
$Root    = Split-Path -Parent $PSScriptRoot
$Data    = Join-Path $Root ".pgdata"
$Port    = 5432

function Run { param([Parameter(ValueFromRemainingArguments)]$CmdArgs) conda run -n $EnvName @CmdArgs }

switch ($Action) {
  "init" {
    if (Test-Path (Join-Path $Data "PG_VERSION")) { Write-Host "already initialised"; break }
    Run initdb -D $Data -U postgres --auth=trust -E UTF8
  }
  "start" {
    Run pg_ctl -D $Data -o "-p $Port" -l (Join-Path $Data "server.log") start
  }
  "stop" {
    Run pg_ctl -D $Data stop -m fast
  }
  "createdb" {
    Run psql -U postgres -h localhost -p $Port -c "CREATE ROLE callsense LOGIN PASSWORD 'callsense' SUPERUSER;"
    Run psql -U postgres -h localhost -p $Port -c "CREATE DATABASE callsense OWNER callsense;"
  }
}
