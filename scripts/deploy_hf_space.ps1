# Deploy CallSense to a Hugging Face Space (Docker, free 2 vCPU / 16GB — runs
# the REAL Whisper+Gemini loop).
#
#   ./scripts/deploy_hf_space.ps1 -Token hf_xxx -DatabaseUrl "postgresql+psycopg://..." -GeminiKey "..."
#
# What it does: create the Space (docker sdk) -> set secrets server-side ->
# push the repo (with HF README frontmatter) to the Space's git remote.
# The token/secrets are sent only to huggingface.co; nothing is committed.

param(
    [Parameter(Mandatory = $true)][string]$Token,
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [Parameter(Mandatory = $true)][string]$GeminiKey,
    [string]$SpaceName = "callsense",
    [switch]$Private
)

$ErrorActionPreference = "Stop"
$git = "C:\Users\Aaryan\AppData\Local\Microsoft\WinGet\Packages\Git.MinGit_Microsoft.Winget.Source_8wekyb3d8bbwe\cmd\git.exe"
$repoRoot = Split-Path -Parent $PSScriptRoot
$headers = @{ Authorization = "Bearer $Token" }

# 1. Who am I?
$me = Invoke-RestMethod -Uri "https://huggingface.co/api/whoami-v2" -Headers $headers
$user = $me.name
Write-Host "HF user: $user"
$spaceId = "$user/$SpaceName"

# 2. Create the Space (idempotent).
$createBody = @{
    type = "space"; name = $SpaceName; sdk = "docker"
    private = [bool]$Private; hardware = "cpu-basic"
} | ConvertTo-Json
try {
    Invoke-RestMethod -Method Post -Uri "https://huggingface.co/api/repos/create" `
        -Headers $headers -Body $createBody -ContentType "application/json" | Out-Null
    Write-Host "space created: https://huggingface.co/spaces/$spaceId"
} catch {
    $code = try { $_.Exception.Response.StatusCode.value__ } catch { 0 }
    if ($code -eq 409) { Write-Host "space already exists - updating" } else { throw }
}

# 3. Secrets (server-side env; never in git).
foreach ($secret in @(
        @{ key = "DATABASE_URL"; value = $DatabaseUrl },
        @{ key = "GEMINI_API_KEY"; value = $GeminiKey })) {
    $body = $secret | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "https://huggingface.co/api/spaces/$spaceId/secrets" `
        -Headers $headers -Body $body -ContentType "application/json" | Out-Null
    Write-Host "secret set: $($secret.key)"
}

# 4. Stage a clean copy with the HF frontmatter README.
$stage = Join-Path $env:TEMP "callsense-space-$(Get-Random)"
New-Item -ItemType Directory -Path $stage | Out-Null
robocopy $repoRoot $stage /E /NFL /NDL /NJH /NJS /NP `
    /XD .git .pgdata node_modules .next .pytest_cache __pycache__ testcalls inbox store `
    /XF .env *.pyc | Out-Null

$frontmatter = @"
---
title: CallSense
emoji: 📞
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

"@
$original = Get-Content (Join-Path $repoRoot "README.md") -Raw
Set-Content (Join-Path $stage "README.md") ($frontmatter + $original) -Encoding utf8

# 5. Push to the Space.
Set-Location $stage
& $git init -q -b main
& $git config user.email "aaryansmaralihalli@gmail.com"
& $git config user.name "Aaryan S. Maralihalli"
& $git add -A
& $git commit -q -m "Deploy CallSense (real-mode: faster-whisper + Gemini)"
& $git push -f "https://${user}:${Token}@huggingface.co/spaces/$spaceId" main
Set-Location $repoRoot
Remove-Item $stage -Recurse -Force

Write-Host ""
Write-Host "Deployed. Build logs + app: https://huggingface.co/spaces/$spaceId"
Write-Host "API base URL for Vercel:  https://$user-$($SpaceName.ToLower()).hf.space"
