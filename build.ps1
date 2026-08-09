$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $Root "dist"
$Desktop = Join-Path $env:USERPROFILE "Desktop"
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

# --- Plugin DLL ---
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$outDll = Join-Path $Dist "VatsimConnect.dll"
$ref = Join-Path $env:LOCALAPPDATA "vPilot\RossCarlson.Vatsim.Vpilot.Plugins.dll"
& $csc /nologo /target:library "/out:$outDll" "/reference:$ref" /reference:System.Net.Http.dll /reference:System.Web.Extensions.dll (Join-Path $Root "plugin\Plugin.cs") (Join-Path $Root "plugin\Properties\AssemblyInfo.cs")
if ($LASTEXITCODE -ne 0) { throw "plugin compile failed" }

$Plugins = Join-Path $env:LOCALAPPDATA "vPilot\Plugins"
if (Test-Path $Plugins) {
    Copy-Item $outDll (Join-Path $Plugins "VatsimConnect.dll") -Force
}
Copy-Item $outDll (Join-Path $Root "windows\VatsimConnect.dll") -Force

# --- Windows app EXE ---
$Win = Join-Path $Root "windows"
Push-Location $Win
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name VatsimConnect --icon icon.ico --onefile --add-data "VatsimConnect.dll;." main.py
if ($LASTEXITCODE -ne 0) { throw "app build failed" }
$built = Join-Path $Win "dist\VatsimConnect.exe"
Copy-Item $built (Join-Path $Dist "VatsimConnect.exe") -Force

# --- One-click Setup EXE (embeds app + plugin) ---
& ".\.venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name VatsimConnect-Setup --icon icon.ico --onefile `
  --add-data "dist\VatsimConnect.exe;." `
  --add-data "VatsimConnect.dll;." `
  --add-data "icon.ico;." `
  installer.py
if ($LASTEXITCODE -ne 0) { throw "setup build failed" }
$setup = Join-Path $Win "dist\VatsimConnect-Setup.exe"
Copy-Item $setup (Join-Path $Dist "VatsimConnect-Setup.exe") -Force
Copy-Item $setup (Join-Path $Desktop "VatsimConnect-Setup.exe") -Force
Pop-Location

# --- Android (optional / unchanged) ---
$Sdk = ($env:LOCALAPPDATA + "\Android\Sdk") -replace "\\", "/"
Set-Content -Path (Join-Path $Root "android\local.properties") -Value ("sdk.dir=" + $Sdk)
$env:JAVA_HOME = "C:\Program Files (x86)\Eclipse Adoptium\jdk-17"
if (-not (Test-Path $env:JAVA_HOME)) {
    $jdk = Get-ChildItem "C:\Program Files*\Eclipse Adoptium\jdk-17*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($jdk) { $env:JAVA_HOME = $jdk.FullName }
}
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
Push-Location (Join-Path $Root "android")
.\gradlew.bat assembleRelease bundleRelease
Copy-Item ".\app\build\outputs\apk\release\app-release.apk" (Join-Path $Dist "VatsimConnect.apk") -Force
Copy-Item ".\app\build\outputs\apk\release\app-release.apk" (Join-Path $Desktop "VatsimConnect.apk") -Force
Copy-Item ".\app\build\outputs\bundle\release\app-release.aab" (Join-Path $Dist "VatsimConnect.aab") -Force
Pop-Location

Write-Host ""
Write-Host "Published:"
Get-ChildItem $Dist | Format-Table Name, Length, LastWriteTime -AutoSize
Write-Host "Desktop installer:"
Get-Item (Join-Path $Desktop "VatsimConnect-Setup.exe") | Format-Table Name, Length, LastWriteTime -AutoSize
