# vibeApping setup — idempotent. Run from any directory:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with the progress bar

$JdkZip          = 'https://aka.ms/download-jdk/microsoft-jdk-17.0.20.1-windows-x64.zip'
$CmdlineToolsZip = 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip'
$AndroidHome     = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$Workspace       = Join-Path $env:USERPROFILE 'vibeapping'
$ReaVersion      = '6.7.0'   # keep in sync with REA in backend/vibe/playstore.py
$JadxJarUrl      = 'https://github.com/1013503897/jadx-headless-mcp/releases/download/v0.7.1/jadx-headless-mcp-0.7.1-all.jar'
# cmake 4.1.2: its ninja honors Windows long paths; the 3.22.1 default's does not (react-native-worklets fails).
$Packages        = @('platform-tools', 'platforms;android-36', 'build-tools;36.0.0', 'cmake;4.1.2')

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "   ok  $msg" -ForegroundColor Green }
function SetUserEnv($name, $value) {
    if ([Environment]::GetEnvironmentVariable($name, 'User') -ne $value) {
        [Environment]::SetEnvironmentVariable($name, $value, 'User')
        Ok "set user env $name=$value"
    }
    Set-Item -Path "env:$name" -Value $value
}
function AddUserPath($dir) {
    $parts = ([Environment]::GetEnvironmentVariable('Path', 'User') -split ';') | Where-Object { $_ }
    if ($parts -notcontains $dir) {
        [Environment]::SetEnvironmentVariable('Path', (@($dir) + $parts) -join ';', 'User')
        Ok "prepended to user PATH: $dir"
    }
    if (($env:Path -split ';') -notcontains $dir) { $env:Path = "$dir;$env:Path" }
}
function Install-Winget($id) {
    winget.exe install --id $id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget install $id failed ($LASTEXITCODE)" }
}

# ---- Windows long paths (react-native-worklets' CMake paths exceed 260 chars) --
Step 'Windows long paths'
$lp = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem').LongPathsEnabled
if ($lp -ne 1) {
    throw "LongPathsEnabled is off. Run once in an ADMIN PowerShell, then re-run setup:`n" +
          "  New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force"
}
Ok 'LongPathsEnabled = 1'

# ---- Node LTS -------------------------------------------------------------
Step 'Node LTS'
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node -or [int]((node -v) -replace '^v(\d+).*', '$1') -lt 20) {
    Install-Winget 'OpenJS.NodeJS.LTS'
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
Ok "node $(node -v), npm $(npm -v)"

# ---- JDK 17 (per-user zip install, no admin prompt) ------------------------
Step 'JDK 17'
$jdkRoot = Join-Path $env:LOCALAPPDATA 'Programs\Java'
$jdk = Get-ChildItem $jdkRoot -Directory -Filter 'jdk-17*' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $jdk) {
    New-Item -ItemType Directory -Force $jdkRoot | Out-Null
    $zip = Join-Path $env:TEMP 'jdk17.zip'
    Write-Host "   downloading $JdkZip"
    Invoke-WebRequest -UseBasicParsing $JdkZip -OutFile $zip
    Expand-Archive $zip -DestinationPath $jdkRoot -Force
    Remove-Item $zip
    $jdk = Get-ChildItem $jdkRoot -Directory -Filter 'jdk-17*' | Select-Object -First 1
    if (-not $jdk) { throw 'JDK 17 not found after extracting zip' }
    Ok 'JDK 17 installed'
}
SetUserEnv 'JAVA_HOME' $jdk.FullName
AddUserPath (Join-Path $jdk.FullName 'bin')
Ok ((Get-Content "$env:JAVA_HOME\release" | Select-String '^JAVA_VERSION=').Line)

# ---- Android SDK ----------------------------------------------------------
Step 'Android SDK'
$sdkmanager = Join-Path $AndroidHome 'cmdline-tools\latest\bin\sdkmanager.bat'
if (-not (Test-Path $sdkmanager)) {
    New-Item -ItemType Directory -Force (Join-Path $AndroidHome 'cmdline-tools') | Out-Null
    $zip = Join-Path $env:TEMP 'cmdline-tools.zip'
    Write-Host "   downloading $CmdlineToolsZip"
    Invoke-WebRequest -UseBasicParsing $CmdlineToolsZip -OutFile $zip
    $tmp = Join-Path $env:TEMP 'cmdline-tools-extract'
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive $zip -DestinationPath $tmp
    Move-Item (Join-Path $tmp 'cmdline-tools') (Join-Path $AndroidHome 'cmdline-tools\latest')
    Remove-Item $zip, $tmp -Recurse -Force
    Ok 'cmdline-tools installed'
}
SetUserEnv 'ANDROID_HOME' $AndroidHome
SetUserEnv 'ANDROID_SDK_ROOT' $AndroidHome
AddUserPath (Join-Path $AndroidHome 'platform-tools')
AddUserPath (Join-Path $AndroidHome 'cmdline-tools\latest\bin')

# Accept the SDK license by writing the hash files sdkmanager looks for (stdin piping to
# sdkmanager.bat is unreliable on Windows, and it exits 0 even when it skips packages).
$licenseDir = Join-Path $AndroidHome 'licenses'
New-Item -ItemType Directory -Force $licenseDir | Out-Null
[System.IO.File]::WriteAllText((Join-Path $licenseDir 'android-sdk-license'),
    "`n24333f8a63b6825ea9c5514f83c2829b004d1fee`nd56f5187479451eabf01fb78af6dfcb131a6481e")
[System.IO.File]::WriteAllText((Join-Path $licenseDir 'android-sdk-preview-license'),
    "`n84831b9409646a918e30573bab4c9c91346d8abd")

function PackageDir($pkg) { Join-Path $AndroidHome ($pkg -replace ';', '\') }
$missing = @($Packages | Where-Object { -not (Test-Path (PackageDir $_)) })
if ($missing) {
    Write-Host "   installing: $($missing -join ', ')"
    & $sdkmanager "--sdk_root=$AndroidHome" $missing
    $still = @($Packages | Where-Object { -not (Test-Path (PackageDir $_)) })
    if ($still) { throw "sdkmanager did not install: $($still -join ', ')" }
}
foreach ($p in $Packages) { Ok $p }

# ---- Python 3.12 (backend) ------------------------------------------------
Step 'Python 3.12'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Install-Winget 'astral-sh.uv'; $env:Path += ";$env:USERPROFILE\.local\bin" }
uv python install 3.12 | Out-Null
Ok (uv python find 3.12)

# ---- Coding agents (at least one of Codex CLI / Claude Code, signed in) ----
Step 'Coding agents'
$agents = 0
if (Get-Command codex -ErrorAction SilentlyContinue) {
    $status = (cmd /c 'codex login status 2>&1' | Out-String).Trim()   # cmd does the redirect: PS 5.1 + Stop turns native stderr into errors
    if ($status -match 'Logged in') { Ok "codex: $status"; $agents = 1 } else { Write-Host "   codex is installed but not signed in. Run: codex login" }
} else { Write-Host '   codex not found (optional): npm i -g @openai/codex ; codex login' }
if (Get-Command claude -ErrorAction SilentlyContinue) {
    $status = (cmd /c 'claude auth status 2>&1' | Out-String)
    if ($status -match '"loggedIn":\s*true') { Ok 'claude: signed in'; $agents = 1 } else { Write-Host "   claude is installed but not signed in. Run: claude auth login" }
} else { Write-Host '   claude not found (optional): npm i -g @anthropic-ai/claude-code ; claude auth login' }
if (-not $agents) { Write-Host '   WARNING: no signed-in agent. Install Codex CLI or Claude Code and sign in before creating apps.' -ForegroundColor Yellow }

# ---- Workspace + keystore -------------------------------------------------
Step "Workspace $Workspace"
New-Item -ItemType Directory -Force (Join-Path $Workspace 'apps') | Out-Null
$configPath = Join-Path $Workspace 'config.json'
$jksPath    = Join-Path $Workspace 'vibe.jks'
if (Test-Path $configPath) { $config = Get-Content $configPath -Raw | ConvertFrom-Json }
else {
    $config = [pscustomobject]@{
        keystore = $jksPath
        alias    = 'vibe'
        password = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    }
    $config | ConvertTo-Json | Set-Content $configPath -Encoding utf8
    Ok 'wrote config.json'
}
if (-not (Test-Path $jksPath)) {
    & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -v -keystore $jksPath -alias $config.alias `
        -keyalg RSA -keysize 2048 -validity 10000 -storepass $config.password -keypass $config.password `
        -dname 'CN=vibeApping, OU=dev, O=vibeApping, L=Local, S=Local, C=US' | Out-Null
    Ok 'generated vibe.jks'
}
Ok "config.json + vibe.jks (alias $($config.alias))"

# ---- npm dependencies: template (copied into every app), dashboard, Play Store scraper --
Step 'npm dependencies'
$repo = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $repo 'template')
if (-not (Test-Path 'node_modules\expo')) { Write-Host '   npm ci in template (a few minutes)'; cmd /c 'npm ci --silent 2>&1' | Out-Null }
Pop-Location
Push-Location (Join-Path $repo 'dashboard')
if (-not (Test-Path 'node_modulesite')) { cmd /c 'npm install --silent 2>&1' | Out-Null }
Pop-Location
Push-Location (Join-Path $repo 'backend\playstore')
if (-not (Test-Path 'node_modules\google-play-scraper')) { cmd /c 'npm install --silent 2>&1' | Out-Null }
Pop-Location
Ok 'template, dashboard, google-play-scraper installed'

# ---- REA + JADX: lets the agent study a downloaded APK ("Also study the original app") --
# REA (rea-agents) is fetched by npx on demand; it needs a caller-supplied jadx-headless-mcp jar.
Step 'APK analysis (REA + JADX)'
$toolsDir = Join-Path $Workspace 'tools'
$jadxJar  = Join-Path $toolsDir 'jadx-headless-mcp-0.7.1-all.jar'
if (-not (Test-Path $jadxJar)) {
    New-Item -ItemType Directory -Force $toolsDir | Out-Null
    Write-Host "   downloading $JadxJarUrl"
    Invoke-WebRequest -UseBasicParsing $JadxJarUrl -OutFile $jadxJar
    Ok 'jadx-headless-mcp jar installed'
}
SetUserEnv 'REA_JADX_MCP_JAR' $jadxJar
cmd /c "npx -y rea-agents@$ReaVersion --help >nul 2>&1"   # warm the npx cache so the first APK analysis does not wait on a download
Ok "rea-agents@$ReaVersion + $jadxJar"

# ---- Devices --------------------------------------------------------------
Step 'adb devices'
& (Join-Path $AndroidHome 'platform-tools\adb.exe') devices -l
Write-Host "`nDone. Open a new terminal so JAVA_HOME / ANDROID_HOME / PATH take effect, then run scripts\dev.ps1" -ForegroundColor Cyan
