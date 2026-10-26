"""A pre-fix worker can leave its exact Node child alive. Never use real services."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

REPO=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt','Windows process ownership')
class LegacyConsoleStop(unittest.TestCase):
    def test_verified_legacy_orphan_is_stopped_without_targeting_port_owner_alone(self):
        with tempfile.TemporaryDirectory(prefix='dsh-legacy-orphan-') as tmp:
            root=Path(tmp);(root/'deployment-config').mkdir();(root/'dsh-console').mkdir()
            core=(REPO/'scripts/start-bot.ps1').read_bytes();launcher=root/'start-bot.ps1'
            launcher.write_bytes(core.replace(b'[DshLauncherProcess]::OwnChildren()',b'# synthetic legacy worker without Job'))
            shutil.copyfile(REPO/'scripts/launcher-process.cs',root/'launcher-process.cs')
            (root/'dsh-console/server.js').write_text("require('node:net').createServer().listen(Number(process.env.PORT),'127.0.0.1');setTimeout(()=>process.exit(0),30000);",encoding='utf-8')
            with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
            shell=shutil.which('pwsh.exe');cfg=str(root/'deployment-config/console-credential.clixml').replace("'","''")
            credential="$s=New-Object Security.SecureString;foreach($c in 'synthetic-orphan-token-0123456789012345'.ToCharArray()){$s.AppendChar($c)};New-Object PSCredential('dsh',$s)|Export-Clixml -LiteralPath '"+cfg+"'"
            subprocess.run([shell,'-NoProfile','-Command',credential],check=True,capture_output=True)
            args=[shell,'-NoProfile','-NonInteractive','-File',str(launcher),'-RuntimeRoot',tmp,'-Component','Console','-ConsolePort',str(port),'-TimeoutSeconds','5']
            def ps(code):return subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',code],capture_output=True,encoding='utf-8',timeout=10)
            state=None;child=None
            try:
                started=subprocess.run(args,capture_output=True,encoding='utf-8',timeout=15);self.assertEqual(started.returncode,0,started.stdout+started.stderr)
                state=json.loads((root/'.launcher/Console.json').read_text(encoding='utf-8-sig'))
                child=json.loads(ps('$p=Get-CimInstance Win32_Process -Filter "ParentProcessId='+str(state['pid'])+'";@{pid=$p.ProcessId;ticks=(Get-Process -Id $p.ProcessId).StartTime.ToUniversalTime().Ticks.ToString()}|ConvertTo-Json -Compress').stdout)
                # Stop only this just-created fixture worker after exact ticks check.
                ps('$p=Get-Process -Id '+str(state['pid'])+';if($p.StartTime.ToUniversalTime().Ticks.ToString() -eq "'+state['ticks']+'"){$p.Kill();$p.WaitForExit(3000)|Out-Null}')
                launcher.write_bytes(core)
                with socket.create_connection(('127.0.0.1',port),timeout=2):pass
                record=root/'.launcher/Console.json';saved=record.read_bytes();metadata=record.stat()
                record.write_text(json.dumps({**state,'nonce':'a'*32}),encoding='utf-8')
                denied=subprocess.run([*args,'-Action','Stop'],capture_output=True,encoding='utf-8',timeout=15)
                self.assertNotEqual(denied.returncode,0)
                with socket.create_connection(('127.0.0.1',port),timeout=2):pass
                record.write_bytes(saved);os.utime(record,ns=(metadata.st_atime_ns,metadata.st_mtime_ns))
                stopped=subprocess.run([*args,'-Action','Stop'],capture_output=True,encoding='utf-8',timeout=15)
                self.assertEqual(stopped.returncode,0,stopped.stdout+stopped.stderr)
                with self.assertRaises(OSError):socket.create_connection(('127.0.0.1',port),timeout=.5)
            finally:
                # Precise fixture identity only; cleanup never scans process names.
                if child:ps('$p=Get-Process -Id '+str(child['pid'])+' -ErrorAction SilentlyContinue;if($p -and $p.StartTime.ToUniversalTime().Ticks.ToString() -eq "'+child['ticks']+'"){$p.Kill();$p.WaitForExit(3000)|Out-Null}')
                if state:ps('$p=Get-Process -Id '+str(state['pid'])+' -ErrorAction SilentlyContinue;if($p -and $p.StartTime.ToUniversalTime().Ticks.ToString() -eq "'+state['ticks']+'"){$p.Kill();$p.WaitForExit(3000)|Out-Null}')
                time.sleep(.3)
