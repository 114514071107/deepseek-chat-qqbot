"""Real temporary external controller: unconfirmed requests expire before action."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import base64
import ctypes
import msvcrt
from test_repair_startup_ownership import REPO,SHELL,unused_port,alive

def read_shared(path):
    """Observers must not block Windows ReplaceFile with a deny-delete CRT open."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    kernel.CreateFileW.restype=ctypes.c_void_p
    for attempt in range(4):
        handle=kernel.CreateFileW(str(path),0x80000000,7,None,3,0,None)
        if handle!=ctypes.c_void_p(-1).value:
            fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
            with os.fdopen(fd,'r',encoding='utf-8-sig') as stream:return json.load(stream)
        error=ctypes.get_last_error()
        if error not in (5,32,33) or attempt==3:raise ctypes.WinError(error)
        time.sleep(.02)

@unittest.skipUnless(os.name=='nt','Windows external controller')
class ControllerQueue(unittest.TestCase):
    @contextmanager
    def fixture(self,paused=False,state_failure=False):
        with tempfile.TemporaryDirectory(prefix='dsh controller queue ') as temp:
            root=Path(temp);(root/'deployment-config').mkdir();(root/'venv/Scripts').mkdir(parents=True)
            for name in ('start-bot.ps1','launcher-process.cs','launcher-shell.ps1'):shutil.copyfile(REPO/'scripts'/name,root/name)
            source=(root/'start-bot.ps1').read_text(encoding='utf-8-sig')
            if paused:source=source.replace('foreach($file in $requests){',"if(!(Test-Path -LiteralPath (Join-Path $root 'release-queue'))){$requests=@()}\n                foreach($file in $requests){")
            if state_failure:source=source.replace('function Save-Json($Path, $Value) {',"function Save-Json($Path, $Value) {\n if([IO.Path]::GetFileName($Path) -eq 'Bot.json' -and $Value.status -eq 'created'){[IO.File]::WriteAllText((Join-Path $root 'created-identity.json'),($Value|ConvertTo-Json));throw 'Synthetic state persistence failure'}")
            # Mutation controls are confined to this disposable script; they
            # reproduce the exact reviewed pre-fix branches for RED evidence.
            if os.environ.get('DSH_TEST_PRIOR_ZERO_EXIT'):
                source=source.replace(" -and [int]$componentFailure.Exception.Data['DshExitCode'] -ne 0",'')
            if os.environ.get('DSH_TEST_PRIOR_STATE_CLEANUP'):
                source=source.replace('if($createdThisAction -and $state -and (Test-Worker $state))','if($false)')
            if os.environ.get('DSH_TEST_PRIOR_QUEUE'):
                source=source.replace('if(!$request.deadline -or [double]$request.deadline -lt [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000)','if($false)').replace("$failureStatus=if($_.Exception.Data.Contains('ResultUnknown')){'unknown'}else{'failed'}","$failureStatus='failed'")
            if os.environ.get('DSH_TEST_PRIOR_CONTROLLER_SHELL'):
                source=source.replace('-FilePath $choice.exe','-FilePath $shellExe')
            (root/'start-bot.ps1').write_text(source,encoding='utf-8-sig')
            shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
            (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"synthetic"}',encoding='utf-8')
            (root/'run').write_text('raise SystemExit(0)',encoding='utf-8')
            cp,bp=unused_port(),unused_port();token='synthetic-controller-0123456789abcdef'
            (root/'dsh-console').mkdir()
            (root/'dsh-console/server.js').write_text('const API_VER = "synthetic-controller";require("node:http").createServer((q,r)=>{if(!q.headers.authorization){r.writeHead(401);r.end();return;}r.setHeader("content-type","application/json");r.end(JSON.stringify({api_ver:API_VER,frontend_ver:API_VER,pid:process.pid}));}).listen('+str(cp)+',"127.0.0.1");',encoding='utf-8')
            env={**os.environ,'PYTHONHOME':sys.base_prefix,'PATH':sys.base_prefix+';'+str(Path(shutil.which('node.exe')).parent)+';'+str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0')+';'+str(Path(os.environ['SystemRoot'])/'System32')}
            prep="$env:PSModulePath=$PSHOME+'\\Modules';$s=ConvertTo-SecureString '"+token+"' -AsPlainText -Force;New-Object PSCredential('dsh',$s)|Export-Clixml -LiteralPath '"+str(root/'deployment-config/console-credential.clixml').replace("'","''")+"'"
            subprocess.run([SHELL,'-NoProfile','-Command',prep],capture_output=True,check=True)
            def run(component,action='Start',extra=()):
                return subprocess.run([SHELL,'-NoProfile','-NonInteractive','-File',str(root/'start-bot.ps1'),'-RuntimeRoot',str(root),'-Component',component,'-Action',action,'-BotPort',str(bp),'-ConsolePort',str(cp),'-TimeoutSeconds','3',*extra],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
            def health():
                request=urllib.request.Request('http://127.0.0.1:'+str(cp)+'/api/health',headers={'Authorization':'Basic '+base64.b64encode(('dsh:'+token).encode()).decode()})
                with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
            try:
                started=run('Console');self.assertEqual(started.returncode,0,started.stdout+started.stderr)
                yield root,run,health
            finally:
                if (root/'created-identity.json').exists() and not (root/'.launcher/Bot.json').exists():
                    shutil.copyfile(root/'created-identity.json',root/'.launcher/Bot.json')
                for component in ('Bot','Console'):
                    stopped=run(component,'Stop');self.assertEqual(stopped.returncode,0,stopped.stdout+stopped.stderr)

    def test_no_ack_is_unknown_and_expired_request_never_restarts_console(self):
        with self.fixture(paused=True) as (root,run,health):
            original=health()['pid'];operations=root/'.launcher/operations';operations.mkdir(exist_ok=True);identity='c'*32
            (operations/(identity+'.json')).write_text(json.dumps(dict(id=identity,status='pending',ok=False,time='2026-10-27T00:00:00Z')),encoding='utf-8')
            result=run('Console','Restart',('-OperationId',identity,'-DetachOperation'))
            row=read_shared(operations/(identity+'.json'))
            self.assertEqual(row['status'],'unknown',result.stdout)
            self.assertEqual(health()['pid'],original)
            (root/'release-queue').touch()
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                row=read_shared(operations/(identity+'.json'))
                if row.get('stage')=='expired_before_action':break
                time.sleep(.15)
            self.assertEqual(row.get('stage'),'expired_before_action',row)
            self.assertFalse(row['action_started']);self.assertEqual(health()['pid'],original)

    def test_application_exit_zero_before_ready_is_failed_nonzero(self):
        with self.fixture() as (root,run,_):
            result=run('Bot')
            self.assertNotEqual(result.returncode,0,result.stdout)
            self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1])['status'],'failed')

    def test_new_worker_state_write_failure_cleans_created_identity(self):
        with self.fixture(state_failure=True) as (root,run,_):
            (root/'run').write_text('import time;time.sleep(30)',encoding='utf-8')
            result=run('Bot');self.assertNotEqual(result.returncode,0,result.stdout)
            self.assertIn('state persistence failure',result.stdout)
            state=json.loads((root/'created-identity.json').read_text())
            self.assertFalse(alive(state['pid']),'Failed initial state save leaked newly created worker')

    def test_controller_uses_new_preflight_choice_and_records_creation_failure(self):
        with self.fixture() as (root,run,health):
            original=health()['pid'];operations=root/'.launcher/operations';operations.mkdir(exist_ok=True)
            chosen=Path.home()/'AppData/Local/Microsoft/WindowsApps/pwsh.exe'
            selector=root/'launcher-shell.ps1'
            selector.write_text("@{ok=$true;exe='"+str(chosen).replace("'","''")+"';version='7.6.9';action_started=$false}|ConvertTo-Json -Compress",encoding='utf-8-sig')
            def request(identity):
                (operations/(identity+'.json')).write_text(json.dumps(dict(id=identity,status='pending',ok=False)),encoding='utf-8')
                run('Console','Start',('-OperationId',identity,'-DetachOperation'))
                deadline=time.monotonic()+12;row={}
                while time.monotonic()<deadline:
                    row=read_shared(operations/(identity+'.json'))
                    if row['status'] not in ('pending','running'):return row
                    time.sleep(.15)
                self.fail('No final controller result: '+str(row))
            row=request('a'*32);self.assertEqual(row['status'],'succeeded',row)
            self.assertIn('PowerShell 7',(operations/('a'*32+'-controller.log')).read_text(encoding='utf-8-sig',errors='replace'),'Controller ignored this action preflight and reused its startup 5.1')
            self.assertEqual(health()['pid'],original)
            selector.write_text("@{ok=$true;exe='"+str(root/'disappeared-shell.exe').replace("'","''")+"';version='synthetic'}|ConvertTo-Json -Compress",encoding='utf-8-sig')
            row=request('b'*32);self.assertEqual(row['status'],'failed',row);self.assertEqual(row['stage'],'action_process_creation');self.assertFalse(row['action_started']);self.assertEqual(health()['pid'],original)
