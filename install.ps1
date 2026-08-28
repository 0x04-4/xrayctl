$ErrorActionPreference = "Stop"

$sourceRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$installRoot = Join-Path $env:LOCALAPPDATA "xrayctl"
$venvRoot = Join-Path $installRoot "venv"

function Test-Python([string]$path) {
    try {
        & $path -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$python = $null
$pythonArgs = @()
$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3.12 -c "import sys" *> $null
    if ($LASTEXITCODE -eq 0) {
        $python = $launcher.Source
        $pythonArgs = @("-3.12")
    }
}

$candidates = @(
    (Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"),
    (Join-Path $env:ProgramFiles "Python312\python.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Python312\python.exe")
)
if (-not $python) {
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -and (Test-Python $candidate)) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & $winget.Source install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            $winget = $null
        }
    }
    if (-not $winget) {
        $architecture = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "win32" }
        $pythonUri = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-$architecture.exe"
        $pythonInstaller = Join-Path ([IO.Path]::GetTempPath()) "xrayctl-python.exe"
        Invoke-WebRequest -Uri $pythonUri -OutFile $pythonInstaller -UseBasicParsing
        Start-Process -FilePath $pythonInstaller -ArgumentList @("/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=1", "Include_pip=1") -Wait
        Remove-Item -LiteralPath $pythonInstaller -Force
    }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -and (Test-Python $candidate)) {
            $python = $candidate
            break
        }
    }
    if (-not $python) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            & $launcher.Source -3.12 -c "import sys" *> $null
            if ($LASTEXITCODE -eq 0) {
                $python = $launcher.Source
                $pythonArgs = @("-3.12")
            }
        }
    }
}

if (-not $python) {
    throw "python 3.12 was not found"
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
& $python @pythonArgs -m venv $venvRoot
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$venvPythonw = Join-Path $venvRoot "Scripts\pythonw.exe"
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
& $venvPython -m pip install --disable-pip-version-check --no-cache-dir $sourceRoot
& $venvPython -m xrayctl core install --yes

$launcherPath = Join-Path $installRoot "xrayctl.cmd"
$launcherText = "@echo off`r`n`"$venvPython`" -m xrayctl %*`r`n"
[IO.File]::WriteAllText($launcherPath, $launcherText, [Text.Encoding]::ASCII)

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathItems = @($userPath -split ";" | Where-Object { $_ })
if (-not ($pathItems | Where-Object { $_.TrimEnd("\") -ieq $installRoot.TrimEnd("\") })) {
    [Environment]::SetEnvironmentVariable("Path", "$installRoot;$userPath", "User")
}
$env:Path = "$installRoot;$env:Path"

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
$shortcutPath = Join-Path $startMenu "xrayctl.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $venvPythonw
$shortcut.Arguments = "-m xrayctl --tray"
$shortcut.WorkingDirectory = $installRoot
$shortcut.Description = "xrayctl tray"
$shortcut.Save()

& $venvPython -m xrayctl startup on
Start-Process -FilePath $venvPythonw -ArgumentList @("-m", "xrayctl", "--tray") -WindowStyle Hidden

Write-Host "xrayctl installed"
Write-Host "run: xrayctl"
