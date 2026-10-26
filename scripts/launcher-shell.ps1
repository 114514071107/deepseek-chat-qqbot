param([switch]$SelectOnly,[string]$CoreScript)
# Bootstrap only: always invoked using the existing system Windows PowerShell.
# No instance action occurs until capability selection is complete.
$ErrorActionPreference='Stop'
$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')+';'+[IO.Path]::Combine($env:ProgramFiles,'WindowsPowerShell','Modules')
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$remainingArguments=@($args)
$candidates=[Collections.Generic.List[string]]::new()
foreach($folder in ($env:PATH -split ';')) {
    if($folder.Trim('"')) { try{$candidates.Add([IO.Path]::Combine($folder.Trim('"'),'pwsh.exe'))}catch{} }
}
$candidates.Add([IO.Path]::Combine($env:ProgramFiles,'PowerShell','7','pwsh.exe'))
$candidates.Add([IO.Path]::Combine($env:SystemRoot,'System32','WindowsPowerShell','v1.0','powershell.exe'))
$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$probe=@'
$ErrorActionPreference='Stop'
$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')+';'+[IO.Path]::Combine($env:ProgramFiles,'WindowsPowerShell','Modules')
try {
 Import-Module Microsoft.PowerShell.Management,Microsoft.PowerShell.Utility,CimCmdlets -ErrorAction Stop
 foreach($command in 'Get-Process','Start-Process','Get-CimInstance','Invoke-CimMethod','New-CimInstance','Import-Clixml','ConvertFrom-Json','Add-Type') {
  $null=Get-Command $command -ErrorAction Stop
 }
 Add-Type -TypeDefinition 'public static class DshShellCapabilityProbe { public static int Value=1; }' -ErrorAction Stop
 [Console]::Write($PSVersionTable.PSVersion.ToString())
 exit 0
} catch {exit 91}
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($probe))
$selected=$null;$failures=@()
foreach($candidate in $candidates) {
    if(!$seen.Add($candidate) -or ![IO.File]::Exists($candidate)){continue}
    $process=[Diagnostics.Process]::new()
    try {
        $process.StartInfo=[Diagnostics.ProcessStartInfo]::new($candidate,('-NoLogo -NoProfile -NonInteractive -EncodedCommand '+$encoded))
        $process.StartInfo.UseShellExecute=$false;$process.StartInfo.CreateNoWindow=$true
        $process.StartInfo.RedirectStandardOutput=$true;$process.StartInfo.RedirectStandardError=$true
        $null=$process.Start()
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(!$process.WaitForExit(5000)){
            $process.Kill();$null=$process.WaitForExit(1000)
            $failures+=@{exe=$candidate;stage='preflight_timeout'};continue
        }
        $version=$stdout.Result.Trim()
        if($process.ExitCode -eq 0 -and $version -match '^(5\.1|7\.)'){
            $selected=@{ok=$true;exe=$candidate;version=$version;failures=$failures;stage='preflight_complete';action_started=$false};break
        }
        $failures+=@{exe=$candidate;stage='capability_probe';exit_code=$process.ExitCode}
    }catch{$failures+=@{exe=$candidate;stage='process_creation';error_type=$_.Exception.GetType().Name}}
    finally{$process.Dispose()}
}
if(!$selected){
    @{ok=$false;status='failed';stage='interpreter_preflight';action_started=$false;failures=$failures}|ConvertTo-Json -Compress -Depth 5
    exit 1
}
if($SelectOnly){$selected|ConvertTo-Json -Compress -Depth 5;exit 0}
if(!$CoreScript -or ![IO.File]::Exists($CoreScript)){throw 'Missing launcher core; no action started'}
Write-Output ('Shell selection: PowerShell '+$selected.version+'; capabilities verified; rejected='+$failures.Count)
# Selection is finished. Preserve the one business invocation's exact exit code.
& $selected.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $CoreScript @remainingArguments
exit $LASTEXITCODE
