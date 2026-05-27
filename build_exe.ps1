$ErrorActionPreference = "Stop"

Set-StrictMode -Version Latest

try {
  Get-Process ReviewData -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
} catch {}

foreach ($dir in @("dist", "build")) {
  for ($i = 0; $i -lt 3; $i++) {
    try {
      if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force -ErrorAction Stop
      }
      break
    } catch {
      Start-Sleep -Milliseconds 800
    }
  }
}

$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_PROGRESS_BAR = "off"
$env:PYTHONUTF8 = "1"

$pipLog = Join-Path $PWD "pip_build.log"
if (Test-Path $pipLog) { Remove-Item $pipLog -Force -ErrorAction SilentlyContinue }

function Invoke-Pip([string[]] $Args) {
  $out = & python -m pip @Args 2>&1
  $out | Out-File -FilePath $pipLog -Encoding utf8 -Append
  return $LASTEXITCODE
}

$skipPipVal = $env:REVIEWDATA_SKIP_PIP
if ($null -eq $skipPipVal) { $skipPipVal = "" }
$skipPip = ($skipPipVal.Trim() -eq "1")
if (-not $skipPip) {
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    Invoke-Pip @("install", "--upgrade", "pip", "--no-warn-script-location", "--disable-pip-version-check", "--progress-bar", "off") | Out-Null
    Invoke-Pip @("install", "-r", "requirements.txt", "--no-warn-script-location", "--disable-pip-version-check", "--progress-bar", "off") | Out-Null
    Invoke-Pip @("install", "--upgrade", "pyinstaller", "--no-warn-script-location", "--disable-pip-version-check", "--progress-bar", "off") | Out-Null
  } finally {
    $ErrorActionPreference = $oldEap
  }
} else {
  "REVIEWDATA_SKIP_PIP=1 -> Saltando instalación de dependencias." | Out-File -FilePath $pipLog -Encoding utf8 -Append
}

$pyiVersion = & python -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller no está disponible en este Python. Conecta a internet y reintenta, o ejecuta: python -m pip install pyinstaller"
}

$argsList = @(
  "--noconfirm",
  "--clean",
  "--onedir",
  "--noconsole",
  "--log-level",
  "WARN",
  "--exclude-module",
  "darkdetect.mac_detect",
  "--exclude-module",
  "mx.DateTime",
  "--exclude-module",
  "mx",
  "--name",
  "ReviewData",
  "main.py"
)

$logPath = Join-Path $PWD "pyinstaller_build.log"
if (Test-Path $logPath) { Remove-Item $logPath -Force -ErrorAction SilentlyContinue }

$stdoutPath = Join-Path $PWD "pyinstaller_stdout.log"
$stderrPath = Join-Path $PWD "pyinstaller_stderr.log"
foreach ($p in @($stdoutPath, $stderrPath)) {
  if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue }
}

$pyArgs = @("-m", "PyInstaller") + $argsList
$proc = Start-Process -FilePath "python" -ArgumentList $pyArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

if (Test-Path $stdoutPath) { Get-Content $stdoutPath -Raw | Out-File -FilePath $logPath -Encoding utf8 }
if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw | Out-File -FilePath $logPath -Encoding utf8 -Append }

if ($proc.ExitCode -ne 0) {
  throw "PyInstaller falló con código $($proc.ExitCode). Revisa: $logPath"
}

$exePath = Join-Path $PWD "dist\ReviewData\ReviewData.exe"
if (-not (Test-Path $exePath)) {
  throw "No se generó el ejecutable esperado: $exePath. Revisa: $logPath"
}

Write-Host ""
Write-Host "OK: PyInstaller terminado." -ForegroundColor Green
Write-Host "Salida: $exePath"
