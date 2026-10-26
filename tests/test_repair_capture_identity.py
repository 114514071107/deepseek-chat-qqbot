"""Deterministic PID reuse between CIM enumeration and handle capture, no OS kills."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_repair_startup_ownership import REPO,SHELL

@unittest.skipUnless(os.name=='nt','PowerShell process identity contract')
class CaptureIdentity(unittest.TestCase):
    def test_reused_child_pid_is_rejected_before_any_termination(self):
        with tempfile.TemporaryDirectory(prefix='dsh capture proof ') as temp:
            script=Path(temp)/'probe.ps1'
            source=r'''
$ErrorActionPreference='Stop';$env:PSModulePath=$PSHOME+'\Modules'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('CORE',[ref]$tokens,[ref]$errors)
foreach($name in @('Open-OwnedProcess','Capture-OwnedFamily')){
 $fn=$ast.Find({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
 if(!$fn){throw ('Missing safe identity capture: '+$name)}
 . ([scriptblock]::Create($fn.Extent.Text))
}
$script:disposed=0
function Fake($id,$ticks){
 $p=[PSCustomObject]@{Id=$id;StartTime=[DateTime]::new($ticks,[DateTimeKind]::Utc);Path='synthetic.exe';Handle=1;HasExited=$false}
 $p|Add-Member ScriptMethod Dispose {$script:disposed++}
 $p|Add-Member ScriptMethod Kill {throw 'No termination is permitted in this probe'}
 return $p
}
$script:root=Fake 1000 100000000000000000
$script:replacement=Fake 1001 100000000200000000
function Get-Process {param($Id,$ErrorAction) if($Id -eq 1000){return $script:root};return $script:replacement}
function Test-Worker {param($State)return $true}
function Get-CimInstance {param($ClassName,$Filter)
 if($Filter -like '*ParentProcessId*1000*'){return [PSCustomObject]@{ProcessId=1001;ParentProcessId=1000;CreationDate=[DateTime]::new(100000000100000000,[DateTimeKind]::Utc);ExecutablePath='synthetic.exe'}}
 return [PSCustomObject]@{ProcessId=1001;ParentProcessId=777;CreationDate=$script:replacement.StartTime;ExecutablePath='synthetic.exe'}
}
$state=@{pid=1000;ticks='100000000000000000';exe='synthetic.exe'}
$rejected=$false
try{$handles=@(Capture-OwnedFamily $state);foreach($handle in $handles){$handle.Dispose()}}
catch{if($_.Exception.Message -match 'identity|provenance|changed'){$rejected=$true}else{throw}}
if(!$rejected){throw 'PID reused after enumeration was accepted as an owned child'}
if($script:disposed -lt 1){throw 'Captured handles leaked after rejected ownership'}
Write-Output 'PID replacement rejected; no termination occurred'
'''.replace('CORE',str(REPO/'scripts/start-bot.ps1').replace("'","''"))
            script.write_text(source,encoding='utf-8-sig')
            result=subprocess.run([SHELL,'-NoProfile','-File',str(script)],capture_output=True,encoding='utf-8',errors='replace',timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
