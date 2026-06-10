$ErrorActionPreference = "SilentlyContinue"

$workspace = "C:\AI_Agent"
$streamlit = Join-Path $workspace ".venv\Scripts\streamlit.exe"
$cloudflared = "C:\Users\kosa\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe"

$streamlitPort = Get-NetTCPConnection -LocalPort 8502 -State Listen
if (-not $streamlitPort) {
    Start-Process `
        -FilePath $streamlit `
        -ArgumentList @("run", "main_pdf.py", "--server.port", "8502", "--server.address", "127.0.0.1", "--server.headless", "true") `
        -WorkingDirectory $workspace `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $workspace "streamlit.log") `
        -RedirectStandardError (Join-Path $workspace "streamlit.err")
    Start-Sleep -Seconds 5
}

$namedTunnel = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "cloudflared.*tunnel.*run.*cubici-ai" }

if (-not $namedTunnel) {
    Start-Process `
        -FilePath $cloudflared `
        -ArgumentList @("tunnel", "run", "cubici-ai") `
        -WorkingDirectory $workspace `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $workspace "cloudflared-named.log") `
        -RedirectStandardError (Join-Path $workspace "cloudflared-named.err")
}
