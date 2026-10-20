# Starts the backend (http://localhost:8000) and the dashboard (http://localhost:5173).
# Ctrl+C stops both.
$root = Split-Path $PSScriptRoot -Parent
cmd /c ('node "{0}\check-node.mjs" 2>&1' -f $PSScriptRoot)
if ($LASTEXITCODE -ne 0) { throw "Run scripts\setup.ps1 with a supported Node release first." }

if (-not (Test-Path "$root\dashboard\node_modules\vite\bin\vite.js")) {
    Write-Host "Installing dashboard dependencies..."
    Push-Location "$root\dashboard"; cmd /c "npm install --include=dev"; Pop-Location
}

$backend = Start-Process cmd -ArgumentList '/c', 'uv run uvicorn vibe.api:app --port 8000' `
    -WorkingDirectory "$root\backend" -NoNewWindow -PassThru
$dashboard = Start-Process cmd -ArgumentList '/c', 'npm run dev' `
    -WorkingDirectory "$root\dashboard" -NoNewWindow -PassThru

Write-Host "Backend:   http://localhost:8000"
Write-Host "Dashboard: http://localhost:5173  (Ctrl+C to stop both)"

try {
    while (-not $backend.HasExited -and -not $dashboard.HasExited) { Start-Sleep -Seconds 1 }
}
finally {
    foreach ($p in $backend, $dashboard) {
        if (-not $p.HasExited) { taskkill /PID $p.Id /T /F | Out-Null }
    }
}
