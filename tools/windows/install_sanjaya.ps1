<#
  Sanjaya one-click setup for Windows (Choice B in the README).

  Started by install_sanjaya_windows.bat. Safe to run again: every step checks
  what is already in place and skips it.

    1. Find Python 3.9 or newer, or install Python 3.12 for this user (no admin).
    2. Create Sanjaya's private Python environment (.venv) in this folder.
    3. Install the language-model pack (fastembed) and download its model.
    4. Optionally install Ollama and its small model (asked; default yes).
    5. Put a Sanjaya shortcut, with the emblem, on the Desktop and Start menu.
    6. Print what works and what does not, and why.

  Everything is logged to setup_log.txt next to this README.
  Exit codes: 0 = Sanjaya can start, 1 = Python could not be found or installed.

  Written for Windows PowerShell 5.1 (built into Windows 10 and 11): ASCII only,
  no PowerShell 7 syntax.
#>
param(
    [switch]$Yes,          # answer every question with its default (unattended)
    [switch]$NoOllama,     # skip the Ollama question and leave Ollama out
    [switch]$NoShortcut    # do not create Desktop / Start menu shortcuts
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with the progress bar on
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root
$Log = Join-Path $Root 'setup_log.txt'
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$PyPointer = Join-Path $Root '.sanjaya_python.txt'   # read by start_windows.bat
$Icon = Join-Path $Root 'static\favicon.ico'

$PY_VERSION = '3.12.10'          # last 3.12 release with a Windows installer
$PY_MINOR = '3.12'
$LM_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
$OLLAMA_MODEL = 'qwen2.5:1.5b'   # lm_labels.DEFAULT_MODEL
$PORT = 8765

# ------------------------------------------------------------------ output helpers
function Write-Log([string]$text) {
    try { Add-Content -Path $Log -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $text) -Encoding UTF8 } catch {}
}
function Say([string]$text, [string]$color = 'Gray') { Write-Host $text -ForegroundColor $color; Write-Log $text }
function Step([string]$n, [string]$text) { Write-Host ''; Say ("  {0}  {1}" -f $n, $text) 'Yellow' }
function Ok([string]$text)   { Say ("       ok   {0}" -f $text) 'Green' }
function Info([string]$text) { Say ("            {0}" -f $text) 'Gray' }
function Warn([string]$text) { Say ("       !!   {0}" -f $text) 'DarkYellow' }
function Bad([string]$text)  { Say ("       xx   {0}" -f $text) 'Red' }

function Ask([string]$question, [bool]$default = $true) {
    if ($Yes) { return $default }
    $hint = '[Y/n]'; if (-not $default) { $hint = '[y/N]' }
    Write-Host ''
    $a = Read-Host ("       {0} {1}" -f $question, $hint)
    Write-Log ("Q: {0} -> '{1}'" -f $question, $a)
    if ([string]::IsNullOrWhiteSpace($a)) { return $default }
    return ($a.Trim().ToLower().StartsWith('y'))
}

function Run-Quiet([string]$exe, [string[]]$arguments) {
    # Runs a program, sends its output to the log, returns the exit code.
    Write-Log ("RUN {0} {1}" -f $exe, ($arguments -join ' '))
    try {
        $out = & $exe @arguments 2>&1
        $code = $LASTEXITCODE
        foreach ($line in $out) { Write-Log ("    " + $line) }
        return $code
    } catch {
        Write-Log ("    failed to start: " + $_.Exception.Message)
        return 9009
    }
}

function Download([string]$url, [string]$dest) {
    Write-Log "GET $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -TimeoutSec 600
        return (Test-Path $dest)
    } catch {
        Write-Log ("    download failed: " + $_.Exception.Message)
        return $false
    }
}

function Signed-By([string]$file, [string]$publisher) {
    # Installers we download must carry a valid Authenticode signature from the expected publisher.
    try {
        $sig = Get-AuthenticodeSignature -FilePath $file
        $subject = ''
        if ($sig.SignerCertificate) { $subject = $sig.SignerCertificate.Subject }
        Write-Log ("signature: {0} / {1}" -f $sig.Status, $subject)
        return (($sig.Status -eq 'Valid') -and ($subject -like "*$publisher*"))
    } catch { return $false }
}

function Have-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }

# ------------------------------------------------------------------ Python helpers
function Py-Version([string]$exe) {
    # Returns [version] for a working interpreter, or $null. The Microsoft Store
    # "python.exe" alias prints nothing useful and is rejected here.
    if (-not $exe) { return $null }
    try {
        $v = & $exe -c "import sys, sqlite3, ssl; print(*sys.version_info[:3], sep=chr(46))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -match '^\d+\.\d+\.\d+$') { return [version]$v }
    } catch {}
    return $null
}

function Find-Pythons {
    # Every interpreter we can see, as objects with Path and Version.
    $paths = New-Object System.Collections.Generic.List[string]
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            foreach ($line in (& py -0p 2>$null)) {
                if ($line -match '([A-Za-z]:\\.+?python\.exe)') { $paths.Add($matches[1]) }
            }
        } catch {}
    }
    foreach ($name in @('python', 'python3')) {
        foreach ($c in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            if ($c.Source -and ($c.Source -notlike '*\WindowsApps\*')) { $paths.Add($c.Source) }
        }
    }
    foreach ($dir in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python*", "${env:ProgramFiles(x86)}\Python*")) {
        foreach ($exe in @(Get-ChildItem -Path $dir -Filter python.exe -Recurse -Depth 2 -ErrorAction SilentlyContinue)) { $paths.Add($exe.FullName) }
    }
    $seen = @{}
    $found = @()
    foreach ($p in $paths) {
        $key = $p.ToLower()
        if ($seen.ContainsKey($key) -or -not (Test-Path $p)) { continue }
        $seen[$key] = $true
        $v = Py-Version $p
        if ($v) { $found += New-Object psobject -Property @{ Path = $p; Version = $v } }
    }
    return $found
}

function Rank([version]$v) {
    # Best first: 3.12, 3.13, 3.11, 3.10 have wheels for the language-model pack;
    # newer releases come next; 3.9 still runs the core.
    $order = @{ '3.12' = 1; '3.13' = 2; '3.11' = 3; '3.10' = 4; '3.9' = 9 }
    $k = '{0}.{1}' -f $v.Major, $v.Minor
    if ($order.ContainsKey($k)) { return $order[$k] }
    if ($v -ge [version]'3.14') { return 5 }
    return 99
}

function Pick-Python {
    $usable = @(Find-Pythons | Where-Object { $_.Version -ge [version]'3.9' })
    if ($usable.Count -eq 0) { return $null }
    return ($usable | Sort-Object @{ Expression = { Rank $_.Version } }, @{ Expression = { $_.Version }; Descending = $true } | Select-Object -First 1)
}

function Install-Python {
    Info "Installing Python $PY_VERSION for this Windows user (no administrator rights needed)."
    if (Have-Winget) {
        Info 'Using winget, the Windows package manager...'
        $code = Run-Quiet 'winget' @('install', '--id', "Python.Python.$PY_MINOR", '--exact', '--scope', 'user', '--silent',
                                     '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
        $p = Pick-Python
        if ($p -and $p.Version -ge [version]'3.10') { return $p }
        Warn "winget did not finish the install (code $code). Trying the python.org installer instead."
    }
    $arch = 'amd64'
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'arm64' }
    $url = "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-$arch.exe"
    $tmp = Join-Path $env:TEMP "python-$PY_VERSION-$arch.exe"
    Info "Downloading $url"
    if (-not (Download $url $tmp)) { Bad 'Could not download the Python installer (no internet, or blocked by a firewall).'; return $null }
    if (-not (Signed-By $tmp 'Python Software Foundation')) {
        Bad 'The downloaded installer is not signed by the Python Software Foundation. It was not run.'
        Remove-Item $tmp -ErrorAction SilentlyContinue
        return $null
    }
    Info 'Signature checked: Python Software Foundation. Running the installer silently...'
    $proc = Start-Process -FilePath $tmp -Wait -PassThru -ArgumentList @('/quiet', 'InstallAllUsers=0', 'PrependPath=1',
             'Include_launcher=1', 'InstallLauncherAllUsers=0', 'Include_test=0', 'Include_doc=0', 'Shortcuts=0')
    Write-Log ("python installer exit code: " + $proc.ExitCode)
    Remove-Item $tmp -ErrorAction SilentlyContinue
    return (Pick-Python)
}

function Make-Venv([string]$basePy) {
    if (Test-Path $VenvPy) {
        $v = Py-Version $VenvPy
        if ($v) { return $true }
        Warn 'The existing private environment (.venv) is broken; rebuilding it.'
        Remove-Item (Join-Path $Root '.venv') -Recurse -Force -ErrorAction SilentlyContinue
    }
    $code = Run-Quiet $basePy @('-m', 'venv', (Join-Path $Root '.venv'))
    return (($code -eq 0) -and (Test-Path $VenvPy))
}

function Install-LmPack([string]$py) {
    Run-Quiet $py @('-m', 'pip', 'install', '--upgrade', 'pip', '--disable-pip-version-check') | Out-Null
    $code = Run-Quiet $py @('-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check', '-r', (Join-Path $Root 'requirements-lm.txt'))
    return ($code -eq 0)
}

function Fetch-LmModel([string]$py) {
    $script = "from fastembed import TextEmbedding; m=TextEmbedding(model_name='$LM_MODEL', cache_dir='model_cache'); print(len(list(m.embed(['test']))[0]))"
    $code = Run-Quiet $py @('-c', $script)
    return ($code -eq 0)
}

# ------------------------------------------------------------------ Ollama helpers
function Ollama-Exe {
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $p) { return $p }
    return $null
}

function Ollama-Up {
    try { Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

function Start-Ollama([string]$exe) {
    if (Ollama-Up) { return $true }
    $app = Join-Path (Split-Path $exe) 'ollama app.exe'
    if (Test-Path $app) { Start-Process -FilePath $app | Out-Null }
    else { Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden | Out-Null }
    for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Seconds 1; if (Ollama-Up) { return $true } }
    return $false
}

function Install-Ollama {
    if (Have-Winget) {
        Info 'Using winget...'
        $code = Run-Quiet 'winget' @('install', '--id', 'Ollama.Ollama', '--exact', '--silent',
                                     '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
        $exe = Ollama-Exe
        if ($exe) { return $exe }
        Warn "winget did not finish the install (code $code). Trying the ollama.com installer instead."
    }
    $tmp = Join-Path $env:TEMP 'OllamaSetup.exe'
    Info 'Downloading https://ollama.com/download/OllamaSetup.exe (about 1 GB on recent versions)...'
    if (-not (Download 'https://ollama.com/download/OllamaSetup.exe' $tmp)) { Bad 'Could not download Ollama.'; return $null }
    if (-not (Signed-By $tmp 'Ollama')) {
        Bad 'The downloaded Ollama installer is not signed by Ollama. It was not run.'
        Remove-Item $tmp -ErrorAction SilentlyContinue
        return $null
    }
    $proc = Start-Process -FilePath $tmp -Wait -PassThru -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    Write-Log ("ollama installer exit code: " + $proc.ExitCode)
    Remove-Item $tmp -ErrorAction SilentlyContinue
    return (Ollama-Exe)
}

function Has-OllamaModel([string]$exe) {
    try {
        $list = & $exe list 2>$null
        foreach ($line in $list) { if ($line -like "$OLLAMA_MODEL*") { return $true } }
    } catch {}
    return $false
}

# ------------------------------------------------------------------ shortcut
function Make-Shortcut([string]$folder) {
    if (-not (Test-Path $folder)) { return $false }
    try {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut((Join-Path $folder 'Sanjaya.lnk'))
        $lnk.TargetPath = Join-Path $Root 'start_windows.bat'
        $lnk.WorkingDirectory = $Root
        $lnk.Description = 'Sanjaya - India and world intelligence, on this computer'
        if (Test-Path $Icon) { $lnk.IconLocation = "$Icon,0" }
        $lnk.Save()
        return $true
    } catch { Write-Log ("shortcut failed: " + $_.Exception.Message); return $false }
}

# ================================================================== the run
try { $Host.UI.RawUI.WindowTitle = 'Sanjaya setup' } catch {}
"" | Set-Content -Path $Log -Encoding UTF8
Write-Log ("Sanjaya setup, {0}, Windows {1}, {2}, PowerShell {3}" -f (Get-Date), [Environment]::OSVersion.Version, $env:PROCESSOR_ARCHITECTURE, $PSVersionTable.PSVersion)
Write-Log ("Folder: " + $Root)

Write-Host ''
Write-Host '   S A N J A Y A' -ForegroundColor Yellow
Write-Host '   India and world intelligence, on your own computer' -ForegroundColor Gray
Write-Host '   one-click setup  .  safe to run again  .  log: setup_log.txt' -ForegroundColor DarkGray

$R = [ordered]@{
    python = $false; venv = $false; lmpack = $false; lmmodel = $false
    ollama = 'skipped'; ollamamodel = $false; shortcut = $false
}
$pyNote = ''

# 1 ---------------------------------------------------------------- Python
Step '1/5' 'Python'
$base = Pick-Python
if ($base) {
    Ok ("Python {0} found at {1}" -f $base.Version, $base.Path)
} else {
    Info 'Python 3.9 or newer was not found on this computer.'
    $base = Install-Python
    if ($base) { Ok ("Python {0} installed at {1}" -f $base.Version, $base.Path) }
}
if (-not $base) {
    Bad 'Sanjaya needs Python, and it could not be installed automatically.'
    Info 'Install it by hand from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),'
    Info 'then double-click install_sanjaya_windows.bat again. README section 3, Choice A, has pictures.'
    Info "Details are in $Log"
    exit 1
}
$R.python = $true

# 2 ---------------------------------------------------------------- private environment
Step '2/5' "Sanjaya's private Python environment (.venv)"
if (Make-Venv $base.Path) { $R.venv = $true; Ok 'ready; nothing is installed into your main Python' }
else { Warn 'Could not create .venv. Sanjaya will run with your main Python; the language-model pack is skipped.' }

# 3 ---------------------------------------------------------------- language-model pack
Step '3/5' 'Language-model pack (groups stories by meaning; about 250 MB)'
if ($R.venv) {
    Info 'Installing fastembed (ONNX Runtime, no PyTorch)...'
    $R.lmpack = Install-LmPack $VenvPy
    if (-not $R.lmpack -and $base.Version -lt [version]'3.10') {
        Warn ("fastembed needs a newer Python than {0}. Python {1} can be installed next to it, just for this user." -f $base.Version, $PY_MINOR)
        if (Ask "Install Python $PY_MINOR for Sanjaya's language model?" $true) {
            $newer = Install-Python
            if ($newer -and $newer.Version -ge [version]'3.10') {
                Remove-Item (Join-Path $Root '.venv') -Recurse -Force -ErrorAction SilentlyContinue
                if (Make-Venv $newer.Path) {
                    $base = $newer
                    Ok ("private environment rebuilt with Python {0}" -f $newer.Version)
                    $R.lmpack = Install-LmPack $VenvPy
                } else {
                    Warn 'Could not rebuild .venv with the new Python; going back to the old one.'
                    Make-Venv $base.Path | Out-Null
                }
            }
        } else { $pyNote = 'kept your Python ' + $base.Version }
    }
    if ($R.lmpack) {
        Ok 'fastembed installed'
        Info 'Downloading the multilingual model into model_cache (about 220 MB, once)...'
        $R.lmmodel = Fetch-LmModel $VenvPy
        if ($R.lmmodel) { Ok 'model ready' } else { Warn 'The model did not download now; Sanjaya will fetch it on its first start.' }
    } else { Bad 'The language-model pack did not install. See setup_log.txt for the pip output.' }
} else { Info 'skipped (no private environment)' }

# 4 ---------------------------------------------------------------- Ollama
Step '4/5' 'Ollama (writes Ask answers and story labels; optional)'
$ollama = Ollama-Exe
if ($ollama) { Ok "Ollama found at $ollama"; $R.ollama = 'yes' }
elseif ($NoOllama) { Info 'skipped (-NoOllama)' }
else {
    Info 'Ollama runs a small language model on this computer. Sanjaya uses it to answer'
    Info 'questions in Ask, with a citation on every sentence, and to label story groups.'
    Info "Download: the Ollama app plus the $OLLAMA_MODEL model, about 2 GB in total."
    if (Ask 'Install Ollama now?' $true) {
        $ollama = Install-Ollama
        if ($ollama) { Ok 'Ollama installed'; $R.ollama = 'yes' } else { Bad 'Ollama did not install.'; $R.ollama = 'failed' }
    } else { Info 'Not installed. You can run this setup again at any time to add it.'; $R.ollama = 'declined' }
}
if ($R.ollama -eq 'yes') {
    if (Has-OllamaModel $ollama) { Ok "$OLLAMA_MODEL already downloaded"; $R.ollamamodel = $true }
    elseif (Start-Ollama $ollama) {
        Info "Downloading $OLLAMA_MODEL (about 1 GB)..."
        $code = Run-Quiet $ollama @('pull', $OLLAMA_MODEL)
        $R.ollamamodel = ($code -eq 0)
        if ($R.ollamamodel) { Ok 'model ready' } else { Bad "Could not download $OLLAMA_MODEL. Later, run:  ollama pull $OLLAMA_MODEL" }
    } else { Bad 'Ollama is installed but did not start. Open Ollama from the Start menu, then run this setup again.' }
}

# 5 ---------------------------------------------------------------- shortcut and launcher
Step '5/5' 'Shortcut with the Sanjaya emblem'
$chosen = $base.Path
if ($R.venv) { $chosen = $VenvPy }
Set-Content -Path $PyPointer -Value $chosen -Encoding ASCII
Write-Log ("start_windows.bat will use " + $chosen)
if ($NoShortcut) { Info 'skipped (-NoShortcut)' }
else {
    $desk = Make-Shortcut ([Environment]::GetFolderPath('Desktop'))
    $menu = Make-Shortcut ([Environment]::GetFolderPath('Programs'))
    $R.shortcut = ($desk -or $menu)
    if ($R.shortcut) { Ok 'Sanjaya is on your Desktop and in the Start menu' } else { Warn 'Could not create a shortcut; start Sanjaya with start_windows.bat.' }
}

# ---------------------------------------------------------------- report
function Line([string]$mark, [string]$what, [string]$meaning, [string]$color) {
    Write-Host ("   {0}  {1,-26} {2}" -f $mark, $what, $meaning) -ForegroundColor $color
    Write-Log ("REPORT {0} {1}: {2}" -f $mark, $what, $meaning)
}
Write-Host ''
Write-Host '   ---------------------------------------------------------------------------' -ForegroundColor DarkGray
Write-Host '   What works on this computer' -ForegroundColor Yellow
Write-Host ''
Line '[ok]' ("Python " + $base.Version) 'All panels, feeds, maps, video, keyword search, lean gauges, audit.' 'Green'
if ($R.lmpack) {
    $m = 'Grouping and search by meaning, "% match" in Compare coverage.'
    if (-not $R.lmmodel) { $m += ' Model downloads on first start.' }
    Line '[ok]' 'Language-model pack' $m 'Green'
} else {
    $m = 'Not installed: stories group by keywords only; search by meaning is off.'
    if ($pyNote) { $m += " ($pyNote)" }
    Line '[--]' 'Language-model pack' $m 'DarkYellow'
}
switch ($R.ollama) {
    'yes' {
        if ($R.ollamamodel) { Line '[ok]' 'Ollama' 'Ask writes cited answers. Story labels: System > Language model.' 'Green' }
        else { Line '[--]' 'Ollama' "Installed, model missing: run  ollama pull $OLLAMA_MODEL" 'DarkYellow' }
    }
    default { Line '[--]' 'Ollama' 'Not installed: Ask cannot write answers. The Google AI Mode link still works.' 'DarkYellow' }
}
if ($R.shortcut) { Line '[ok]' 'Shortcut' 'Double-click Sanjaya on the Desktop from now on.' 'Green' }
else { Line '[--]' 'Shortcut' 'Start Sanjaya with start_windows.bat in this folder.' 'DarkYellow' }
Write-Host ''
Write-Host '   No internet? Sanjaya still opens and shows everything it has stored.' -ForegroundColor DarkGray
Write-Host "   Full details: $Log" -ForegroundColor DarkGray
Write-Host '   ---------------------------------------------------------------------------' -ForegroundColor DarkGray
exit 0
