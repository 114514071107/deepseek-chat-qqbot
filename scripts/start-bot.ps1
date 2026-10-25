param(
    [string]$RuntimeRoot = 'D:\dsbot',
    [switch]$WithConsole,
    [ValidateRange(1,120)][int]$TimeoutSeconds = 30,
    [ValidateRange(1,65535)][int]$BotPort = 6185,
    [ValidateRange(1,65535)][int]$ConsolePort = 7850,
    [switch]$InternalWorker,
    [ValidateSet('Bot','Console')][string]$Component = 'Bot',
    [string]$WorkerId
)
# Same core for Windows PowerShell 5.1 and PowerShell 7. No elevation/policy changes.
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$root = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\')
$control = Join-Path $root '.launcher'
$logRoot = Join-Path $root 'logs\launcher'
$shellExe = Join-Path $PSHOME $(if ($PSVersionTable.PSVersion.Major -ge 6) { 'pwsh.exe' } else { 'powershell.exe' })

function Save-Json($Path, $Value) {
    $temp = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temp, ($Value | ConvertTo-Json -Depth 8), $utf8)
    if ([IO.File]::Exists($Path)) { [DshLauncherProcess]::ReplaceFile($temp,$Path) }
    else { [IO.File]::Move($temp,$Path) }
}
function Read-Json($Path) {
    if (Test-Path -LiteralPath $Path) {
        try {
            $share=[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
            $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,$share)
            $reader=New-Object IO.StreamReader($stream,$utf8,$true)
            try { $raw=$reader.ReadToEnd() } finally { $reader.Dispose() }
            return $raw | ConvertFrom-Json
        }
        catch { throw 'Protected JSON is unreadable or invalid; fix it locally (values withheld)' }
    }
    return $null
}
function Get-Identity($ProcessId) {
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($process.Path)) { return $null }
        return @{ pid=$process.Id; ticks=$process.StartTime.ToUniversalTime().Ticks.ToString(); exe=$process.Path }
    } catch { return $null }
}
function Test-Worker($State) {
    if ($null -eq $State -or $State.nonce -notmatch '^[0-9a-f]{32}$' -or $State.root -ne $root -or [int]$State.pid -le 0) { return $false }
    $identity = Get-Identity $State.pid
    if (!$identity -or $identity.ticks -ne $State.ticks -or $identity.exe -ne $State.exe) { return $false }
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$State.pid)
    return ($process.CommandLine -like ('*' + $State.nonce + '*') -and $process.CommandLine -like '* -InternalWorker *')
}
function Get-Family($ProcessId) {
    $parentIdentity=Get-Identity $ProcessId
    if (!$parentIdentity) { return @() }
    $result = @([int]$ProcessId)
    foreach ($child in @(Get-CimInstance Win32_Process -Filter ("ParentProcessId = " + [int]$ProcessId))) {
        if ($child.CreationDate.ToUniversalTime().Ticks -ge [long]$parentIdentity.ticks) {
            $result += @(Get-Family $child.ProcessId)
        }
    }
    return $result
}
function Stop-Owned($State) {
    if (Test-Worker $State) {
        # Worker owns a KILL_ON_JOB_CLOSE job. No process-name matching.
        Stop-Process -Id $State.pid -Force -ErrorAction SilentlyContinue
        for ($i=0; $i -lt 20 -and (Test-Worker $State); $i++) { Start-Sleep -Milliseconds 50 }
    }
}
function Throw-ComponentExit($Name, $Observation) {
    $failure = New-Object System.Exception($Name + ' exited; exit code ' + $Observation.exit_code + '; inspect component logs')
    $failure.Data['DshExitCode'] = [int]$Observation.exit_code
    throw $failure
}
function Assert-Component($Name) {
    if ($Name -eq 'Bot') {
        if (!(Test-Path -LiteralPath (Join-Path $root 'venv\Scripts\astrbot.exe') -PathType Leaf)) { throw 'Missing Bot dependency: venv\Scripts\astrbot.exe' }
        $settings = Read-Json (Join-Path $root 'deployment-config\runtime.json')
        if (!$settings -or [string]::IsNullOrWhiteSpace($settings.OwnerPlatformId) -or $settings.OwnerPlatformId -like 'YOUR_*') { throw 'Missing required runtime.json OwnerPlatformId; authentication was not bypassed' }
    } else {
        if (!(Get-Command node.exe -ErrorAction SilentlyContinue)) { throw 'Missing Console dependency: node.exe' }
        if (!(Test-Path -LiteralPath (Join-Path $root 'dsh-console\server.js'))) { throw 'Missing Console server.js' }
        $credentialPath = Join-Path $root 'deployment-config\console-credential.clixml'
        if (!(Test-Path -LiteralPath $credentialPath)) { throw 'Missing Console credential; empty authentication is forbidden' }
        try { $credential = Import-Clixml -LiteralPath $credentialPath }
        catch { throw 'Console credential cannot be decrypted by this Windows account' }
        $token=if ($credential) { $credential.GetNetworkCredential().Password } else { '' }
        if ($token.Length -lt 32 -or $token -match '[\s:]') { throw 'Console credential must contain at least 32 characters without whitespace or colon' }
    }
}
function Get-ComponentCommand($Name) {
    $env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'
    $env:PATH=(Join-Path $root 'venv\Scripts')+';'+$env:PATH+';'+(Join-Path $root 'bin')
    if ($Name -eq 'Bot') {
        # Preserve start-runtime.ps1's protected environment contract while
        # resolving every path against this explicitly selected instance.
        $settings=Read-Json (Join-Path $root 'deployment-config\runtime.json')
        $env:ASTRBOT_ROOT=$root
        $env:DSH_OWNER_PLATFORM_ID=[string]$settings.OwnerPlatformId
        $env:DSH_ASSISTANT_ROOT=if ($settings.AssistantRoot) { [string]$settings.AssistantRoot } else { $null }
        return @{ exe=(Join-Path $root 'venv\Scripts\astrbot.exe'); arguments='run' }
    }
    $credential=Import-Clixml -LiteralPath (Join-Path $root 'deployment-config\console-credential.clixml')
    $env:DSH_CONSOLE_TOKEN=$credential.GetNetworkCredential().Password
    $env:DSH_RUNTIME_ROOT=$root
    $env:HOST='127.0.0.1'; $env:PORT=$ConsolePort.ToString()
    return @{ exe=(Get-Command node.exe).Source; arguments=('"'+(Join-Path $root 'dsh-console\server.js')+'" --port '+$ConsolePort) }
}

try {
    if (!(Test-Path -LiteralPath $root -PathType Container)) { throw 'RuntimeRoot does not exist' }
    New-Item -ItemType Directory -Path $control,$logRoot -Force | Out-Null
    Add-Type -Path (Join-Path $PSScriptRoot 'launcher-process.cs')
    if ($InternalWorker) {
        if ($WorkerId -notmatch '^[0-9a-f]{32}$') { throw 'Invalid worker identity' }
        $observation = Join-Path $control ($WorkerId + '.json')
        $observed = @{ time=[DateTime]::UtcNow.ToString('o'); component=$Component; pid=$PID; phase='creating'; exit_code=$null }
        try {
            [DshLauncherProcess]::OwnChildren()
            Assert-Component $Component
            $command = Get-ComponentCommand $Component
            $prefix = Join-Path $logRoot ($Component + '-' + $WorkerId)
            $child = New-Object DshLauncherProcess+Child($command.exe, $command.arguments, $root, ($prefix+'-stdout.log'), ($prefix+'-stderr.log'))
            $observed.phase='running'; Save-Json $observation $observed
            $code = $child.Wait(); $child.Dispose()
            $observed.phase='exited'; $observed.exit_code=$code; $observed.time=[DateTime]::UtcNow.ToString('o')
            Save-Json $observation $observed
            exit $code
        } catch {
            $observed.phase='worker-failed'; $observed.exit_code=1; $observed.time=[DateTime]::UtcNow.ToString('o')
            Save-Json $observation $observed
            exit 1
        }
    }
    Write-Output ("PowerShell " + $PSVersionTable.PSVersion.ToString())
    Write-Output ("Logs: " + $logRoot)
    $lock = $null; $lockDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while (!$lock) {
        try { $lock = [IO.File]::Open((Join-Path $control 'start.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch [IO.IOException] {
            if ([DateTime]::UtcNow -ge $lockDeadline) { throw 'Another launcher is busy; timed out waiting for instance lock' }
            Start-Sleep -Milliseconds 100
        }
    }
    try {
        $components = @('Bot'); if ($WithConsole) { $components += 'Console' }
        foreach ($name in $components) {
            $port = if ($name -eq 'Bot') { $BotPort } else { $ConsolePort }
            Assert-Component $name
            $statePath = Join-Path $control ($name + '.json')
            $state = Read-Json $statePath
            $existing = (Test-Worker $state)
            if ($existing -and ([int]$state.port -ne $port)) { throw ($name + ' already managed with another port; check instance settings') }
            $listeners = @([DshLauncherProcess]::ListeningPids($port))
            if ($listeners.Count) {
                if ($existing) {
                    $family = @(Get-Family $state.pid)
                    if (@($listeners | Where-Object { $family -notcontains $_ }).Count -eq 0) {
                        Write-Output ($name + ' reuse: owned listener ready; QQ connection not checked')
                        continue
                    }
                }
                throw ($name + ' port conflict: listener is not a verified process of this instance')
            }
            if (!$existing) {
                $nonce = [Guid]::NewGuid().ToString('N')
                $arguments = ' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -InternalWorker -RuntimeRoot "' + $root + '" -Component ' + $name + ' -WorkerId ' + $nonce + ' -ConsolePort ' + $ConsolePort
                $created = Start-Process -FilePath $shellExe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
                $identityDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
                do {
                    $identity = Get-Identity $created.Id
                    if ($identity -or $created.HasExited) { break }
                    Start-Sleep -Milliseconds 50
                } while ([DateTime]::UtcNow -lt $identityDeadline)
                if (!$identity) {
                    $observed = Read-Json (Join-Path $control ($nonce + '.json'))
                    if ($observed -and [int]$observed.pid -eq $created.Id -and $observed.component -eq $name -and $observed.phase -in @('exited','worker-failed')) {
                        Throw-ComponentExit $name $observed
                    }
                    if ($created.HasExited -and $created.ExitCode -ne 0) {
                        Throw-ComponentExit $name @{ exit_code=$created.ExitCode }
                    }
                    throw ($name + ' worker identity unavailable; inspect the nonce observation before any retry')
                }
                $state = @{ pid=$identity.pid; ticks=$identity.ticks; exe=$identity.exe; nonce=$nonce; root=$root; component=$name; port=$port; status='created' }
                Save-Json $statePath $state
                Write-Output ($name + ' created; waiting for owned listener')
            }
            $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
            $ready = $false
            try {
                while ([DateTime]::UtcNow -lt $deadline) {
                    $observed = Read-Json (Join-Path $control ($state.nonce + '.json'))
                    if ($observed -and $observed.phase -in @('exited','worker-failed')) { Throw-ComponentExit $name $observed }
                    if (!(Test-Worker $state)) {
                        $observed = Read-Json (Join-Path $control ($state.nonce + '.json'))
                        if ($observed -and $observed.phase -in @('exited','worker-failed')) { Throw-ComponentExit $name $observed }
                        throw ($name + ' worker disappeared; inspect exit observation and logs')
                    }
                    $listeners = @([DshLauncherProcess]::ListeningPids($port))
                    if ($listeners.Count) {
                        $family = @(Get-Family $state.pid)
                        if (@($listeners | Where-Object { $family -notcontains $_ }).Count) { throw ($name + ' port conflict during startup') }
                        $ready=$true; break
                    }
                    Start-Sleep -Milliseconds 150
                }
                if (!$ready) { throw ($name + ' startup timeout; owned worker will be stopped; inspect logs') }
                $state.status='ready'; Save-Json $statePath $state
                Write-Output ($name + ' ready: owned listener; QQ connection not checked')
            } catch { Stop-Owned $state; throw }
        }
    } finally { if ($lock) { $lock.Dispose() } }
    exit 0
} catch {
    Write-Output ('Launcher failed: ' + $_.Exception.Message)
    Write-Output ('Check protected runtime settings/dependencies and logs: ' + $logRoot)
    $failureCode = 1
    if ($_.Exception.Data.Contains('DshExitCode') -and [int]$_.Exception.Data['DshExitCode'] -ne 0) {
        $failureCode = [int]$_.Exception.Data['DshExitCode']
    }
    exit $failureCode
}
