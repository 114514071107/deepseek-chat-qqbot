"""Actual instance launcher/HTTP/restart under both shells; only temp roots."""
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
import urllib.error
import base64
import ast

REPO=Path(__file__).resolve().parents[1]
TOKEN='synthetic-lifecycle-credential-0123456789'


def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


@unittest.skipUnless(os.name=='nt','Windows only')
class ActualConsoleLifecycle(unittest.TestCase):
    def test_real_restart_and_bot_ownership_both_shells(self):
        for shell in ('powershell.exe','pwsh.exe'):
            with self.subTest(shell=shell),tempfile.TemporaryDirectory(prefix='dsh lifecycle ') as tmp:
                env=os.environ.copy()
                if shell=='powershell.exe':env['PSModulePath']=str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/Modules')
                if shell=='powershell.exe':env['PATH']=str(Path(shutil.which('node.exe')).parent)+';'+str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0')+';'+str(Path(os.environ['SystemRoot'])/'System32')+';'+os.environ['SystemRoot']
                root=Path(tmp);cfg=root/'deployment-config';cfg.mkdir()
                for name in ('start-bot.ps1','start-bot.cmd','launcher-process.cs','launcher-shell.ps1'):shutil.copyfile(REPO/'scripts'/name,root/name)
                shutil.copytree(REPO/'console',root/'dsh-console',ignore=shutil.ignore_patterns('tests'))
                (root/'dsh_data/admin_v2').mkdir(parents=True)
                (root/'data/plugins/astrbot_plugin_dsh_soul').mkdir(parents=True)
                shutil.copyfile(REPO/'plugin/astrbot_plugin_dsh_soul/build_info.py',root/'data/plugins/astrbot_plugin_dsh_soul/build_info.py')
                (cfg/'runtime.json').write_text('{"OwnerPlatformId":"synthetic"}',encoding='utf-8')
                py=root/'venv/Scripts';py.mkdir(parents=True)
                shutil.copyfile(Path(sys.base_prefix)/'python.exe',py/'astrbot.exe')
                for dll in ('python312.dll','python3.dll'):shutil.copyfile(Path(sys.base_prefix)/dll,py/dll)
                (py/'astrbot._pth').write_text(str(Path(sys.base_prefix)/'Lib')+'\n'+str(Path(sys.base_prefix)/'DLLs')+'\n',encoding='utf-8')
                bp,cp=port(),port()
                fixture_version=next(ast.literal_eval(n.value) for n in ast.parse((root/'data/plugins/astrbot_plugin_dsh_soul/build_info.py').read_text()).body if isinstance(n,ast.Assign) and n.targets[0].id=='BUILD_VERSION')
                (root/'run').write_text('import socket,time,json,os,pathlib\ns=socket.socket();s.bind(("127.0.0.1",'+str(bp)+'));s.listen()\np=pathlib.Path("dsh_data/admin_v2/live.json")\nwhile True:\n p.write_text(json.dumps(dict(pid=os.getpid(),version='+repr(fixture_version)+',qq_connection={"configured":1,"ready":1,"status":"ready"},at=time.time())),encoding="utf-8");time.sleep(.1)\n',encoding='utf-8')
                literal=str(cfg/'console-credential.clixml').replace("'","''")
                cmd="$s=ConvertTo-SecureString '"+TOKEN+"' -AsPlainText -Force; New-Object System.Management.Automation.PSCredential('dsh',$s)|Export-Clixml -LiteralPath '"+literal+"'"
                prep=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',cmd],capture_output=True,env=env)
                self.assertEqual(prep.returncode,0,prep.stderr.decode('utf-8',errors='replace'))
                args=[shell,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(root/'start-bot.ps1'),'-RuntimeRoot',tmp,'-BotPort',str(bp),'-ConsolePort',str(cp),'-TimeoutSeconds','12']
                def launch(component,action='Start',verify=True,seconds=None):
                    actual=args.copy()
                    if seconds:actual[actual.index('-TimeoutSeconds')+1]=str(seconds)
                    return subprocess.run([*actual,'-Component',component,'-Action',action,*(['-VerifyReady'] if verify else [])],capture_output=True,encoding='utf-8',errors='replace',timeout=45,env=env)
                base='http://127.0.0.1:'+str(cp)
                def http(route,body=None):
                    headers={'Authorization':'Basic '+base64.b64encode(('dsh:'+TOKEN).encode()).decode()}
                    if body is not None:headers.update(Origin=base,**{'Content-Type':'application/json','X-DSH-Request':'1'})
                    request=urllib.request.Request(base+route,None if body is None else json.dumps(body).encode(),headers)
                    with urllib.request.urlopen(request,timeout=18) as response:return json.load(response)
                def wait(id):
                    deadline=time.monotonic()+65;last=None
                    while time.monotonic()<deadline:
                        try:
                            last=http('/api/lifecycle?id='+id)
                            if last['status'] not in ('pending','running'):return last
                        except (OSError,urllib.error.URLError):pass
                        time.sleep(.3)
                    observations=[p.read_text(encoding='utf-8-sig',errors='replace') for p in (root/'.launcher/operations').glob('*')]
                    self.fail('operation did not resolve: '+str(last)+' records='+str(observations))
                try:
                    entry='cmd.exe /d /s /c "'+subprocess.list2cmdline([str(root/'dsh-console/start-dsh-console.cmd'),'-RuntimeRoot',str(root),'-ConsolePort',str(cp),'-TimeoutSeconds','12'])+'"'
                    first=subprocess.run(entry,cwd=os.environ['SystemRoot'],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
                    self.assertEqual(first.returncode,0,first.stdout+first.stderr)
                    before=http('/api/health');self.assertEqual(before['api_ver'],before['frontend_ver'])
                    repeated=subprocess.run(entry,cwd=os.environ['SystemRoot'],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
                    self.assertEqual(repeated.returncode,0,repeated.stdout+repeated.stderr)
                    self.assertEqual(before['pid'],http('/api/health')['pid'])
                    accepted=http('/api/console',{'action':'restart'})
                    self.assertEqual(accepted['status'],'pending');self.assertFalse(accepted['ok'])
                    done=wait(accepted['id']);self.assertEqual(done['status'],'succeeded',done)
                    self.assertNotEqual(before['pid'],http('/api/health')['pid'])
                    # Real bot worker + heartbeat; exact same launcher entry as Console.
                    first=launch('Bot');self.assertEqual(first.returncode,0,first.stdout+first.stderr)
                    state=root/'.launcher/Bot.json';original=json.loads(state.read_text(encoding='utf-8-sig'))
                    second=launch('Bot');self.assertEqual(second.returncode,0,second.stdout+second.stderr)
                    self.assertEqual(original['pid'],json.loads(state.read_text(encoding='utf-8-sig'))['pid'])
                    self.assertTrue(http('/api/status')['bot_running'])
                    repeat=http('/api/bot',{'action':'start'});repeated=wait(repeat['id']);self.assertEqual(repeated['status'],'succeeded',repeated)
                    self.assertEqual(original['pid'],json.loads(state.read_text(encoding='utf-8-sig'))['pid'])
                    # Inject stop faults only into this fixture copy, preserving
                    # the real worker, family, lock and final-result code path.
                    launcher=root/'start-bot.ps1';source=launcher.read_bytes()
                    try:
                        launcher.write_bytes(source.replace(b'$owned.Kill()',b"throw 'Synthetic AccessDenied'"))
                        denied=launch('Bot','Stop');self.assertNotEqual(denied.returncode,0);self.assertIn('AccessDenied',denied.stdout)
                        with socket.create_connection(('127.0.0.1',bp),timeout=2):pass
                        launcher.write_bytes(source.replace(b'$owned.Kill()',b'[void]0'))
                        timed=launch('Bot','Stop',seconds=2);self.assertNotEqual(timed.returncode,0);self.assertIn('Stop timeout',timed.stdout)
                        with socket.create_connection(('127.0.0.1',bp),timeout=2):pass
                    finally:launcher.write_bytes(source)
                    # PID reuse / mismatched ticks: do not stop even this synthetic worker.
                    changed={**original,'ticks':str(int(original['ticks'])+1)};state.write_text(json.dumps(changed),encoding='utf-8')
                    denied=launch('Bot','Stop');self.assertNotEqual(denied.returncode,0,denied.stdout)
                    state.write_text(json.dumps(original),encoding='utf-8')
                    self.assertEqual(launch('Bot','Status').returncode,0)
                    stop=http('/api/bot',{'action':'stop'});self.assertEqual(wait(stop['id'])['status'],'succeeded')
                    # Unrelated listener in temporary port is never terminated.
                    with socket.socket() as other:
                        other.bind(('127.0.0.1',bp));other.listen()
                        blocked=launch('Bot','Restart');self.assertNotEqual(blocked.returncode,0)
                        self.assertEqual(other.getsockname()[1],bp)
                    # New process exits before readiness: final failure, not success.
                    good_bot=(root/'run').read_bytes()
                    (root/'run').write_text('raise SystemExit(23)\n',encoding='utf-8')
                    failed=launch('Bot');self.assertNotEqual(failed.returncode,0,failed.stdout)
                    # A real listener + fresh version heartbeat still cannot
                    # claim startup complete while configured QQ is connecting.
                    (root/'run').write_bytes(good_bot.replace(b'"status":"ready"',b'"status":"connecting"'))
                    connecting=launch('Bot',seconds=2);self.assertNotEqual(connecting.returncode,0);self.assertIn('startup timeout',connecting.stdout)
                    (root/'run').write_bytes(good_bot)
                    # Console old port not released: external controller returns
                    # a final failure while old authenticated server survives.
                    launcher=root/'start-bot.ps1';source=launcher.read_bytes()
                    try:
                        launcher.write_bytes(source.replace(b'$owned.Kill()',b'[void]0').replace(b'$TimeoutSeconds = 30',b'$TimeoutSeconds = 2'))
                        command=[*args,'-Component','Console','-Action','Restart','-OperationId','b'*32,'-VerifyReady']
                        command[command.index('-TimeoutSeconds')+1]='2'
                        timed=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace',env=env,timeout=15)
                        self.assertNotEqual(timed.returncode,0);self.assertIn('Stop timeout',timed.stdout)
                        self.assertEqual(http('/api/lifecycle?id='+'b'*32)['status'],'failed')
                        self.assertEqual(http('/api/health')['api_ver'],fixture_version)
                    finally:launcher.write_bytes(source)
                    stopped=launch('Console','Stop');self.assertEqual(stopped.returncode,0,stopped.stdout)
                    # Foreign Console port holder is never stopped.
                    with socket.socket() as other:
                        other.bind(('127.0.0.1',cp));other.listen()
                        blocked=launch('Console');self.assertNotEqual(blocked.returncode,0);self.assertIn('port conflict',blocked.stdout)
                        self.assertEqual(other.getsockname()[1],cp)
                    console=root/'dsh-console/server.js';console_source=console.read_bytes()
                    try:
                        console.write_bytes(b'process.exit(17);\n')
                        failed=launch('Console');self.assertNotEqual(failed.returncode,0);self.assertIn('exit code 17',failed.stdout)
                        console.write_bytes(b"require('node:net').createServer().listen(Number(process.env.PORT),'127.0.0.1');\n")
                        timeout_args=[*args,'-Component','Console','-Action','Start','-OperationId','d'*32,'-VerifyReady']
                        timeout_args[timeout_args.index('-TimeoutSeconds')+1]='2'
                        timed=subprocess.run(timeout_args,capture_output=True,encoding='utf-8',errors='replace',env=env,timeout=20)
                        self.assertNotEqual(timed.returncode,0);self.assertIn('startup timeout',timed.stdout)
                        self.assertEqual(json.loads((root/'.launcher/operations'/('d'*32+'.json')).read_text(encoding='utf-8-sig'))['status'],'failed')
                    finally:console.write_bytes(console_source)
                    recovered=launch('Console');self.assertEqual(recovered.returncode,0,recovered.stdout+recovered.stderr)
                    self.assertEqual(http('/api/health')['api_ver'],fixture_version)
                    self.assertEqual(http('/api/lifecycle?id='+'d'*32)['status'],'failed')
                finally:
                    launch('Bot','Stop',False);launch('Console','Stop',False)


if __name__=='__main__':unittest.main()
