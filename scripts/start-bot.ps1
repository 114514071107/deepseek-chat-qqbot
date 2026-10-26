param(
    [string]$RuntimeRoot = 'D:\dsbot',
    [switch]$WithConsole = ($env:DSH_LAUNCH_WITH_CONSOLE -eq '1'),
    [ValidateRange(1,120)][int]$TimeoutSeconds = 30,
    [ValidateRange(1,65535)][int]$BotPort = 6185,
    [ValidateRange(1,65535)][int]$ConsolePort = 7850,
    [switch]$InternalWorker,
    [switch]$InternalController,
    [ValidateSet('Bot','Console')][string]$Component = 'Bot',
    [string]$WorkerId,
    [ValidateSet('Start','Stop','Restart','Status')][string]$Action = 'Start',
    [switch]$VerifyReady = $true,
    [switch]$DetachOperation,
    [string]$OperationId
)
# Same core for Windows PowerShell 5.1 and PowerShell 7. No elevation/policy changes.
$ErrorActionPreference = 'Stop'
$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')+';'+[IO.Path]::Combine($env:ProgramFiles,'WindowsPowerShell','Modules')
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
function Test-Controller($State) {
    if(!$State -or $State.root -ne $root -or $State.nonce -notmatch '^[0-9a-f]{32}$'){return $false}
    $identity=Get-Identity $State.pid
    if(!$identity -or $identity.ticks -ne $State.ticks -or $identity.exe -ne $State.exe){return $false}
    $process=Get-CimInstance Win32_Process -Filter ('ProcessId='+[int]$State.pid)
    return ($process.CommandLine -like '* -InternalController *' -and $process.CommandLine.Contains($State.nonce) -and $process.CommandLine.Contains('-RuntimeRoot "'+$root+'"'))
}
function Ensure-Controller {
    $path=Join-Path $control 'Controller.json'
    if(Test-Controller (Read-Json $path)){return}
    # Establish from the user entry before component Jobs exist. A Console
    # request cannot create its replacement controller inside its own Job.
    if($env:DSH_RUNTIME_ROOT -or $OperationId){throw 'Independent controller unavailable; use the instance entry to establish it; no action retried'}
    $nonce=[Guid]::NewGuid().ToString('N')
    $arguments='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -InternalController -RuntimeRoot "'+$root+'" -WorkerId '+$nonce
    $process=Start-Process -FilePath $shellExe -ArgumentList $arguments -WorkingDirectory $env:SystemRoot -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(8)
    do{
        $state=Read-Json $path
        if($state -and $state.nonce -eq $nonce -and (Test-Controller $state)){return}
        if($process.HasExited){throw 'Independent controller exited before entry acknowledgment'}
        Start-Sleep -Milliseconds 100
    }while([DateTime]::UtcNow -lt $deadline)
    throw 'Independent controller entry acknowledgment timed out; no business action started'
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
    return ($process.CommandLine -like ('*' + $State.nonce + '*') -and $process.CommandLine -like '* -InternalWorker *' -and
        $process.CommandLine.Contains('-RuntimeRoot "'+$root+'"') -and
        $process.CommandLine -match ('-Component '+[regex]::Escape([string]$State.component)+'(?:\s|$)'))
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
function Open-OwnedProcess($Identity) {
    try { $process=Get-Process -Id $Identity.pid -ErrorAction Stop }
    catch {
        if ($_.FullyQualifiedErrorId -like 'NoProcessFoundForGivenId*') { return $null }
        throw
    }
    try {
        $null=$process.Handle
        if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $Identity.ticks -or $process.Path -ne $Identity.exe) {
            throw 'Process identity changed before stop; refusing operation'
        }
        return $process
    } catch {
        if ($process.HasExited) { $process.Dispose(); return $null }
        $process.Dispose(); throw
    }
}
function Capture-OwnedFamily($State) {
    $held=[Collections.ArrayList]::new()
    function Capture-Children($Parent) {
        foreach($observed in @(Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$Parent.Id))) {
            if($observed.CreationDate.ToUniversalTime().Ticks -lt $Parent.StartTime.ToUniversalTime().Ticks){continue}
            try{$child=Get-Process -Id $observed.ProcessId -ErrorAction Stop}
            catch{if($_.FullyQualifiedErrorId -like 'NoProcessFoundForGivenId*'){continue};throw}
            try{
                $null=$child.Handle
                if($child.HasExited){$child.Dispose();continue}
                $current=Get-CimInstance Win32_Process -Filter ('ProcessId='+[int]$observed.ProcessId)
                # CIM exposes microsecond creation precision. Bind that snapshot
                # and parent relationship to the retained handle immediately,
                # before a bare PID could be reinterpreted as a new process.
                $handleTicks=$child.StartTime.ToUniversalTime().Ticks
                $observedTicks=$observed.CreationDate.ToUniversalTime().Ticks
                if(!$current -or $current.ParentProcessId -ne $Parent.Id -or $current.CreationDate -ne $observed.CreationDate -or
                    [decimal]::Floor([decimal]$handleTicks/10) -ne [decimal]::Floor([decimal]$observedTicks/10) -or
                    !$observed.ExecutablePath -or $child.Path -ne $observed.ExecutablePath){throw 'Child identity/provenance changed during capture; refusing stop'}
                $null=$held.Add($child)
            }catch{
                if($child.HasExited){$child.Dispose();continue}
                $child.Dispose();throw
            }
            Capture-Children $child
        }
    }
    try{
        $parent=Open-OwnedProcess $State
        if($parent){$null=$held.Add($parent);Capture-Children $parent}
        if($parent -and !$parent.HasExited -and !(Test-Worker $State)){throw 'Worker identity changed during capture'}
        return @($held)
    }catch{foreach($handle in $held){$handle.Dispose()};throw}
}
function Stop-Owned($State) {
    if (!(Test-Worker $State)) { throw 'Worker identity is not verified; refusing stop' }
    # Keep the verified process handle open: PID reuse cannot redirect Kill().
    $handles=@()
    try {
    $handles=@(Capture-OwnedFamily $State)
    $owned=@($handles | Where-Object { $_.Id -eq $State.pid })[0]
    if ($owned -and !$owned.HasExited -and !(Test-Worker $State)) { throw 'Worker identity changed before stop' }
    if ($owned -and !$owned.HasExited) {
        try { $owned.Kill() } catch { if (!$owned.HasExited) { throw } }
    }
    if (!$owned -or $owned.WaitForExit(1000)) {
        # Some legacy workers did not retain a Job that actually contained Node.
        # These identities were captured while the worker was still verified.
        foreach($child in $handles | Where-Object { $_.Id -ne $State.pid }) {
            if (!$child.HasExited) {
                try { $child.Kill() } catch { if (!$child.HasExited) { throw } }
            }
        }
    }
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $alive=@($handles | Where-Object { !$_.HasExited })
        $listeners=@([DshLauncherProcess]::ListeningPids([int]$State.port))
        if (!$alive.Count -and !$listeners.Count) { return }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Stop timeout: owned process family or port has not exited; no restart attempted'
    } finally { foreach($handle in $handles) { $handle.Dispose() } }
}

function Stop-LegacyConsole($State,$StatePath) {
    if (!$State -or $State.component -ne 'Console' -or $State.root -ne $root -or
        $State.nonce -notmatch '^[0-9a-f]{32}$' -or (Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue)) { throw 'Legacy worker provenance is not verified' }
    $observation=Read-Json (Join-Path $control ($State.nonce+'.json'))
    if (!$observation -or $observation.component -ne 'Console' -or [int]$observation.pid -ne [int]$State.pid) { throw 'Legacy worker observation is missing or inconsistent' }
    $cutoff=(Get-Item -LiteralPath $StatePath).LastWriteTimeUtc.Ticks+20000000
    $node=[IO.Path]::GetFullPath((Get-Command node.exe -ErrorAction Stop).Source)
    $module=Join-Path $root 'dsh-console\server.js'
    $owner=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $verified=@()
    foreach($child in @(Get-CimInstance Win32_Process -Filter ('ParentProcessId='+[int]$State.pid))) {
        $identity=Get-Identity $child.ProcessId
        if (!$identity -or $identity.exe -ne $node -or [long]$identity.ticks -lt [long]$State.ticks -or [long]$identity.ticks -gt $cutoff -or
            $child.CommandLine.IndexOf(('"'+$module+'"'),[StringComparison]::OrdinalIgnoreCase) -lt 0 -or
            $child.CommandLine -notmatch ('--port\s+'+[int]$State.port+'(?:\s|$)')) {
            $details='identity='+[bool]$identity+' exe='+[bool]($identity.exe -eq $node)+' after_worker='+[bool]([long]$identity.ticks -ge [long]$State.ticks)+' before_ready='+[bool]([long]$identity.ticks -le $cutoff)+' module='+[bool]($child.CommandLine.IndexOf(('"'+$module+'"'),[StringComparison]::OrdinalIgnoreCase) -ge 0)+' port='+[bool]($child.CommandLine -match ('--port\s+'+[int]$State.port+'(?:\s|$)'))
            throw ('Legacy child identity/command/start time is not verified: '+$details)
        }
        $account=Invoke-CimMethod -InputObject $child -MethodName GetOwnerSid
        if ($account.ReturnValue -ne 0 -or $account.Sid -ne $owner) { throw 'Legacy child owner is not verified' }
        $verified+=$identity
    }
    $listeners=@([DshLauncherProcess]::ListeningPids([int]$State.port))
    if (!$verified.Count -or @($listeners | Where-Object { @($verified | ForEach-Object {$_.pid}) -notcontains $_ }).Count) { throw 'Legacy listener is not a verified original child' }
    Save-Json (Join-Path $control 'Console-legacy-stop.json') @{root=$root;nonce=$State.nonce;worker_pid=$State.pid;children=$verified;at=[DateTime]::UtcNow.ToString('o')}
    foreach($identity in $verified) {
        $child=Get-Process -Id $identity.pid -ErrorAction Stop
        $null=$child.Handle
        if ($child.StartTime.ToUniversalTime().Ticks.ToString() -ne $identity.ticks -or $child.Path -ne $identity.exe) { throw 'Legacy child identity changed before stop' }
        $child.Kill()
        if (!$child.WaitForExit($TimeoutSeconds*1000)) { throw 'Legacy child stop timeout' }
    }
    if (@([DshLauncherProcess]::ListeningPids([int]$State.port)).Count) { throw 'Legacy port still occupied after verified stop' }
}

function Confirm-Ready($Name,$State) {
    if (!(Test-Worker $State)) { return $false }
    $family=@(Get-Family $State.pid); $listeners=@([DshLauncherProcess]::ListeningPids([int]$State.port))
    if (!$listeners.Count -or @($listeners | Where-Object { $family -notcontains $_ }).Count) { return $false }
    if ($Name -eq 'Bot') {
        $live=Read-Json (Join-Path $root 'dsh_data\admin_v2\live.json')
        $build=Join-Path $root 'data\plugins\astrbot_plugin_dsh_soul\build_info.py'
        if (!(Test-Path -LiteralPath $build)) { return $false }
        $expected=[regex]::Match([IO.File]::ReadAllText($build),'BUILD_VERSION = "([^"]+)"').Groups[1].Value
        if (!$live.qq_connection -or [int]$live.qq_connection.configured -le 0 -or $live.qq_connection.status -ne 'ready' -or [int]$live.qq_connection.ready -ne [int]$live.qq_connection.configured) { return $false }
        $age=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000-[double]$live.at
        return ($live -and !$live.stopped -and $family -contains [int]$live.pid -and $expected -and $live.version -eq $expected -and
            $age -ge -1 -and $age -lt 5 -and [double]$live.at -gt 0)
    }
    try {
        $credential=Import-Clixml -LiteralPath (Join-Path $root 'deployment-config\console-credential.clixml')
        $auth='Basic '+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('dsh:'+$credential.GetNetworkCredential().Password))
        $base='http://127.0.0.1:'+$State.port
        $health=Invoke-RestMethod -Uri ($base+'/api/health') -Headers @{Authorization=$auth} -TimeoutSec 2
        $source=[IO.File]::ReadAllText((Join-Path $root 'dsh-console\server.js'))
        $expected=[regex]::Match($source,'const API_VER = "([^"]+)"').Groups[1].Value
        if (!$expected -or $health.api_ver -ne $expected -or $health.frontend_ver -ne $expected -or $family -notcontains [int]$health.pid) { return $false }
        try { Invoke-WebRequest -UseBasicParsing -Uri ($base+'/api/health') -TimeoutSec 2 | Out-Null; return $false }
        catch { return ([int]$_.Exception.Response.StatusCode -eq 401) }
    } catch { return $false }
}
function Publish-Operation($Status,$Message,$Running=$null,$Name='',$Readiness='') {
    if(!$Name){$Name=if($activeComponent){$activeComponent}else{$Component}}
    $value=@{ok=($Status -eq 'succeeded');status=$Status;component=$Name;action=$Action;running=$Running;time=[DateTime]::UtcNow.ToString('o');error=$Message}
    if($Readiness){$value.readiness=$Readiness}
    if($null -ne $componentResults -and $Status -notin @('pending','running')){$null=$componentResults.Add($value)}
    if ($OperationId) { $value.id=$OperationId; Save-Json (Join-Path $control ('operations\'+$OperationId+'.json')) $value }
    Write-Output ($value | ConvertTo-Json -Compress -Depth 6)
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
    $env:DSH_LAUNCH_SHELL=$shellExe
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
    if($InternalController){
        if($WorkerId -notmatch '^[0-9a-f]{32}$'){throw 'Invalid controller identity'}
        $controllerLock=$null
        try{
            try{$controllerLock=[IO.File]::Open((Join-Path $control 'controller.lock'),'OpenOrCreate','ReadWrite','None')}catch [IO.IOException]{exit 0}
            $identity=Get-Identity $PID
            Save-Json (Join-Path $control 'Controller.json') @{root=$root;nonce=$WorkerId;pid=$PID;ticks=$identity.ticks;exe=$identity.exe;stage='ready';version='startup-controller-1'}
            $idleSince=[DateTime]::UtcNow
            while(Test-Path -LiteralPath $control){
                $requestDir=Join-Path $control 'operations'
                $requests=if(Test-Path -LiteralPath $requestDir){@(Get-ChildItem -LiteralPath $requestDir -Filter '*-request.json' -File)}else{@()}
                foreach($file in $requests){
                    $request=Read-Json $file.FullName
                    if(!$request -or $request.id -notmatch '^[0-9a-f]{32}$' -or $request.component -notin @('Bot','Console') -or $request.action -notin @('Start','Stop','Restart') -or $request.root -ne $root){throw 'Invalid independent controller request'}
                    $claimed=$file.FullName+'.claimed'
                    [IO.File]::Move($file.FullName,$claimed)
                    $operationPath=Join-Path $requestDir ($request.id+'.json')
                    if(!$request.deadline -or [double]$request.deadline -lt [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000){
                        Save-Json $operationPath @{id=$request.id;component=$request.component;action=$request.action;status='failed';ok=$false;time=[DateTime]::UtcNow.ToString('o');stage='expired_before_action';action_started=$false;error='Request expired before controller acknowledgment; no action executed'}
                        continue
                    }
                    Save-Json $operationPath @{id=$request.id;component=$request.component;action=$request.action;status='running';ok=$false;time=[DateTime]::UtcNow.ToString('o');stage='controller_acknowledged'}
                    $bootstrap=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
                    $choiceText=& $bootstrap -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'launcher-shell.ps1') -SelectOnly
                    $choiceCode=$LASTEXITCODE
                    $choice=$null
                    try{$choice=($choiceText|Select-Object -Last 1)|ConvertFrom-Json}catch{}
                    if($choiceCode -ne 0 -or !$choice.ok){
                        Save-Json $operationPath @{id=$request.id;component=$request.component;action=$request.action;status='failed';ok=$false;time=[DateTime]::UtcNow.ToString('o');stage='interpreter_preflight';action_started=$false;error='Controller interpreter preflight failed; no action executed'}
                        continue
                    }
                    Save-Json (Join-Path $requestDir ($request.id+'-selection.json')) $choice
                    $arguments='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -RuntimeRoot "'+$root+'" -Component '+$request.component+' -Action '+$request.action+' -OperationId '+$request.id+' -BotPort '+[int]$request.bot_port+' -ConsolePort '+[int]$request.console_port+' -TimeoutSeconds '+[int]$request.timeout+' -VerifyReady'
                    try{
                        $operation=Start-Process -FilePath $choice.exe -ArgumentList $arguments -WorkingDirectory $env:SystemRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $requestDir ($request.id+'-controller.log')) -RedirectStandardError (Join-Path $requestDir ($request.id+'-controller-error.log'))
                    }catch{
                        Save-Json $operationPath @{id=$request.id;component=$request.component;action=$request.action;status='failed';ok=$false;time=[DateTime]::UtcNow.ToString('o');stage='action_process_creation';action_started=$false;error=('Action process creation failed: '+$_.Exception.GetType().Name)}
                        continue
                    }
                    $finished=$operation.WaitForExit(([int]$request.timeout*3+15)*1000)
                    $result=Read-Json $operationPath
                    if(!$finished -or $result.status -in @('pending','running')){
                        Save-Json $operationPath @{id=$request.id;component=$request.component;action=$request.action;status=if($finished){'failed'}else{'unknown'};ok=$false;time=[DateTime]::UtcNow.ToString('o');stage='controller_result';error=if($finished){'Action process exited without a final result'}else{'Action result deadline exceeded; not retried'}}
                    }
                    if(!$finished){throw 'Action process still unresolved; controller will not start another action'}
                    $operation.Dispose()
                }
                $hasWorker=(Test-Worker (Read-Json (Join-Path $control 'Bot.json'))) -or (Test-Worker (Read-Json (Join-Path $control 'Console.json')))
                if($hasWorker -or $requests.Count){$idleSince=[DateTime]::UtcNow}
                elseif(([DateTime]::UtcNow-$idleSince).TotalSeconds -gt 12){break}
                Start-Sleep -Milliseconds 200
            }
        }finally{if($controllerLock){$controllerLock.Dispose()}}
        exit 0
    }
    if ($OperationId -and !$DetachOperation) { Publish-Operation 'running' 'Controller started; checking instance lock' }
    if ($OperationId -and $OperationId -notmatch '^[0-9a-f]{32}$') { throw 'Invalid operation identity' }
    if ($DetachOperation) {
        if (!$OperationId) { throw 'Operation identity required' }
        if(!(Test-Controller (Read-Json (Join-Path $control 'Controller.json')))){throw 'Independent controller unavailable; no operation started'}
        Save-Json (Join-Path $control ('operations\'+$OperationId+'-request.json')) @{id=$OperationId;root=$root;component=$Component;action=$Action;bot_port=$BotPort;console_port=$ConsolePort;timeout=$TimeoutSeconds;deadline=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000+4)}
        $deadline=[DateTime]::UtcNow.AddSeconds(4)
        do{
            $record=Read-Json (Join-Path $control ('operations\'+$OperationId+'.json'))
            if($record.status -ne 'pending'){break}
            Start-Sleep -Milliseconds 100
        }while([DateTime]::UtcNow -lt $deadline)
        if(!$record -or $record.status -eq 'pending'){
            $unconfirmed=[Exception]::new('Controller did not acknowledge; result unknown, do not retry')
            $unconfirmed.Data['ResultUnknown']=$true;throw $unconfirmed
        }
        Write-Output (@{ok=$false;accepted=$true;status='pending';id=$OperationId} | ConvertTo-Json -Compress)
        exit 0
    }
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
            $observed.error_type=$_.Exception.GetType().Name
            $observed.error_message=$_.Exception.Message
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
        if($Action -in @('Start','Restart') -and !$OperationId){Ensure-Controller}
        $components = @('Bot'); if ($WithConsole) { $components += 'Console' }
        if ($PSBoundParameters.ContainsKey('Component')) { $components=@($Component) }
        $componentResults=[Collections.ArrayList]::new();$overallExitCode=0
        if ($OperationId) { Publish-Operation 'running' '' }
        foreach ($name in $components) {
            $activeComponent=$name
            try {
            $createdThisAction = $false
            $port = if ($name -eq 'Bot') { $BotPort } else { $ConsolePort }
            if ($Action -in @('Start','Restart')) { Assert-Component $name }
            $statePath = Join-Path $control ($name + '.json')
            $state = Read-Json $statePath
            if ($state -and $state.component -ne $name) { throw 'State component mismatch; refusing operation' }
            $existing = (Test-Worker $state)
            if ($state -and !$existing -and (Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue)) { throw 'Stored PID exists but ownership is unknown (port conflict or stale identity); refusing operation' }
            if ($existing -and ([int]$state.port -ne $port)) { throw ($name + ' already managed with another port; check instance settings') }
            $listeners = @([DshLauncherProcess]::ListeningPids($port))
            if ($Action -eq 'Status') {
                $ready=$existing -and (Confirm-Ready $name $state)
                if ($ready) { Publish-Operation 'succeeded' '' $true $name 'ready' }
                elseif (!$existing -and !$listeners.Count) { Publish-Operation 'succeeded' '' $false $name 'not_running' }
                elseif ($existing) { Publish-Operation 'not_ready' 'Owned process exists but loaded application/QQ readiness is not confirmed' $false $name 'not_ready';$overallExitCode=1 }
                else { Publish-Operation 'unknown' 'Listener ownership is unverified' $null $name 'unknown';$overallExitCode=1 }
                continue
            }
            if ($Action -in @('Stop','Restart')) {
                if ($existing) { Stop-Owned $state }
                elseif ($listeners.Count) {
                    if ($name -eq 'Console' -and $state) { Stop-LegacyConsole $state $statePath }
                    else { throw 'Port is occupied without verified ownership; refusing stop' }
                }
                if ($Action -eq 'Stop') { Publish-Operation 'succeeded' '' $false $name 'not_running';continue }
                $existing=$false; $listeners=@()
            }
            if ($listeners.Count) {
                if ($existing) {
                    $family = @(Get-Family $state.pid)
                    if (@($listeners | Where-Object { $family -notcontains $_ }).Count -eq 0) {
                        if (Confirm-Ready $name $state) {
                            Write-Output ($name + ' reuse: verified ready; QQ client delivery not checked')
                            Publish-Operation 'succeeded' '' $true $name 'ready'
                            continue
                        }
                    } else {
                        throw ($name + ' port conflict: listener is not a verified process of this instance')
                    }
                } else {
                    throw ($name + ' port conflict: listener is not a verified process of this instance')
                }
            }
            if (!$existing) {
                $nonce = [Guid]::NewGuid().ToString('N')
                $arguments = ' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -InternalWorker -RuntimeRoot "' + $root + '" -Component ' + $name + ' -WorkerId ' + $nonce + ' -ConsolePort ' + $ConsolePort
                $created = Start-Process -FilePath $shellExe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
                $createdThisAction = $true
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
                        if (Confirm-Ready $name $state) { $ready=$true; break }
                    }
                    Start-Sleep -Milliseconds 150
                }
                if (!$ready) {
                    $effect = if ($createdThisAction) { 'new owned worker will be stopped' } else { 'existing instance preserved; readiness is unconfirmed' }
                    throw ($name + ' startup timeout; ' + $effect + '; inspect logs')
                }
                $state.status='ready'; Save-Json $statePath $state
                Write-Output ($name + ' ready: identity, loaded version, heartbeat and transport evidence verified; QQ client delivery not checked')
                Publish-Operation 'succeeded' '' $true $name 'ready'
            } catch {
                $startupFailure=$_
                if ($createdThisAction -and (Test-Worker $state)) {
                    try { Stop-Owned $state } catch { Write-Output ('Owned startup cleanup failed: '+$_.Exception.Message) }
                }
                throw $startupFailure
            }
            } catch {
                $componentFailure=$_
                if($createdThisAction -and $state -and (Test-Worker $state)){
                    try{Stop-Owned $state}catch{Write-Output ('Owned creation cleanup failed: '+$_.Exception.Message)}
                }
                $code=1
                if($componentFailure.Exception.Data.Contains('DshExitCode') -and [int]$componentFailure.Exception.Data['DshExitCode'] -ne 0){$code=[int]$componentFailure.Exception.Data['DshExitCode']}
                if(!$overallExitCode){$overallExitCode=$code}
                Write-Output ('Launcher failed for '+$name+': '+$componentFailure.Exception.Message)
                Publish-Operation 'failed' $componentFailure.Exception.Message $null $name 'unknown'
            }
        }
        if(!$OperationId -and $Action -ne 'Status' -and !(Test-Worker (Read-Json (Join-Path $control 'Bot.json'))) -and !(Test-Worker (Read-Json (Join-Path $control 'Console.json')))){
            $controller=Read-Json (Join-Path $control 'Controller.json')
            if(Test-Controller $controller){$process=Open-OwnedProcess $controller;if($process){try{if(!$process.HasExited){$process.Kill();$null=$process.WaitForExit(3000)}}finally{$process.Dispose()}}}
        }
    } finally { if ($lock) { $lock.Dispose() } }
    if($components.Count -gt 1){
        $ok=@($componentResults|Where-Object{$_.ok}).Count
        $status=if($ok -eq $components.Count){'succeeded'}elseif($ok -gt 0){'partial'}elseif(@($componentResults|Where-Object{$_.status -eq 'failed'}).Count){'failed'}else{'unknown'}
        $summary=@{ok=($status -eq 'succeeded');status=$status;component='All';action=$Action;results=@($componentResults);time=[DateTime]::UtcNow.ToString('o')}
        if($OperationId){$summary.id=$OperationId;Save-Json (Join-Path $control ('operations\'+$OperationId+'.json')) $summary}
        Write-Output ($summary|ConvertTo-Json -Compress -Depth 8)
    }
    exit $overallExitCode
} catch {
    Write-Output ('Launcher failed: ' + $_.Exception.Message)
    Write-Output ('Check protected runtime settings/dependencies and logs: ' + $logRoot)
    $failureCode = 1
    if ($_.Exception.Data.Contains('DshExitCode') -and [int]$_.Exception.Data['DshExitCode'] -ne 0) {
        $failureCode = [int]$_.Exception.Data['DshExitCode']
    }
    if (!$InternalWorker -and (!$OperationId -or $OperationId -match '^[0-9a-f]{32}$')) {
        $failureStatus=if($_.Exception.Data.Contains('ResultUnknown')){'unknown'}else{'failed'}
        Publish-Operation $failureStatus $_.Exception.Message
    }
    exit $failureCode
}
