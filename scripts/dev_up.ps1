# LFHÉ DEV: one-command update + start (PO helper, Windows PowerShell). Run from the repository folder:
#     cd C:\Users\bdatA\lfhe ; git pull ; .\scripts\dev_up.ps1
# It asks for the three secrets with hidden prompts (nothing is written to a file or to Git), applies the
# migrations to DEV, then opens the WORKER window and the WEB window by itself.
$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
function Get-Secret([string]$Prompt) { $s = Read-Host -Prompt $Prompt -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)) }

$repo = (Get-Location).Path
if (-not (Test-Path "$repo\.venv\Scripts\Activate.ps1")) { throw "Run this from C:\Users\bdatA\lfhe (the .venv folder was not found here)." }
if ((git branch --show-current) -ne "cr7-04-m07-attribution-robustness") { throw "Wrong branch. Run: git checkout cr7-04-m07-attribution-robustness ; git pull" }
. "$repo\.venv\Scripts\Activate.ps1"

$ref = "ylkubhuxvcsshfkbvski"
$poolerHost = "aws-0-eu-north-1.pooler.supabase.com"
$cfg = "259621ca-7d76-4d25-a06d-1f7d9314b1be"

Write-Host "1/3  Database migrations (DEV)" -ForegroundColor Cyan
$adm = Get-Secret "Supabase postgres password (hidden)"
$env:LFHE_DEV_DB_URL = "postgresql://postgres.${ref}:$([uri]::EscapeDataString($adm))@${poolerHost}:5432/postgres"
python scripts\apply_migrations.py $env:LFHE_DEV_DB_URL
if ($LASTEXITCODE -ne 0) { Remove-Item Env:LFHE_DEV_DB_URL; throw "Migration failed - nothing was started. Send the output above." }
Remove-Item Env:LFHE_DEV_DB_URL
$adm = $null

# the WEB window must NEVER inherit worker secrets (the web app refuses to start with LFHE_DATABASE_URL present)
Write-Host "2/3  Starting the WEB window" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command","Remove-Item Env:LFHE_DATABASE_URL,Env:LFHE_ANTHROPIC_API_KEY -ErrorAction SilentlyContinue; Set-Location '$repo\apps\web'; `$host.UI.RawUI.WindowTitle='LFHE WEB'; npm.cmd run dev -- -H 127.0.0.1"

Write-Host "3/3  Worker settings" -ForegroundColor Cyan
$wk = Get-Secret "lfhe_worker_login password (hidden)"
$env:LFHE_ENV = "DEV"
$env:LFHE_DATABASE_URL = "postgresql://lfhe_worker_login.${ref}:$([uri]::EscapeDataString($wk))@${poolerHost}:5432/postgres"
$wk = $null
foreach ($m in "M02","M03","M04","M05","M06","M07","M08","M09","M10") { Set-Item -Path "env:LFHE_${m}_MODEL_CONFIGURATION_ID" -Value $cfg }
$env:LFHE_ANTHROPIC_API_KEY = Get-Secret "Anthropic API key (hidden)"
$env:LFHE_CHROMIUM_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $env:LFHE_CHROMIUM_PATH)) { throw "Chrome was not found at $($env:LFHE_CHROMIUM_PATH)." }

Write-Host "     Starting the WORKER window" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command","Set-Location '$repo'; . .\.venv\Scripts\Activate.ps1; `$host.UI.RawUI.WindowTitle='LFHE WORKER'; python -m lfhe_orchestrator.worker"
$env:LFHE_ANTHROPIC_API_KEY = $null; $env:LFHE_DATABASE_URL = $null
Write-Host ""
Write-Host "DONE. Two new windows opened (LFHE WORKER, LFHE WEB). In ~20 seconds open http://127.0.0.1:3000/inbox" -ForegroundColor Green
