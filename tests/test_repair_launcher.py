"""Real Windows shells, temporary roots and finite local-only child processes."""
import json
import base64
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'scripts/start-bot.ps1'
ENTRY = ROOT / 'scripts/start-bot.cmd'


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); return sock.getsockname()[1]


@unittest.skipUnless(os.name == 'nt', 'Windows lifecycle contract')
class LauncherRegression(unittest.TestCase):
    def test_same_core_under_both_shells_and_explorer_entry(self):
        self.assertTrue(CORE.is_file(), 'one-click PowerShell core has not been implemented')
        shells = [shutil.which('pwsh.exe'), shutil.which('powershell.exe')]
        self.assertTrue(all(shells), 'both real shells required on this machine')
        for shell in shells:
            with self.subTest(shell=Path(shell).name), tempfile.TemporaryDirectory(prefix='dsh 启动 空格 ') as tmp:
                root = Path(tmp); cfg = root / 'deployment-config'; cfg.mkdir()
                (root/'venv/Scripts').mkdir(parents=True)
                shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
                (cfg/'runtime.json').write_text('{"OwnerPlatformId":"fixture-instance","AssistantRoot":"中文 路径"}', encoding='utf-8')
                fake = root/'run'
                build=root/'data/plugins/astrbot_plugin_dsh_soul';build.mkdir(parents=True)
                (build/'build_info.py').write_text('BUILD_VERSION = "synthetic-launcher"',encoding='utf-8')
                fake_code='import socket,time,sys,os\nassert os.environ["DSH_OWNER_PLATFORM_ID"]=="fixture-instance"\nassert os.environ["DSH_ASSISTANT_ROOT"]=="中文 路径"\ns=socket.socket();s.bind(("127.0.0.1",int(os.environ["DSH_FIXTURE_PORT"])));s.listen();print("合成日志可读",flush=True);time.sleep(90)\n'
                fake_code=fake_code.replace('time.sleep(90)','import json,pathlib\np=pathlib.Path("dsh_data/admin_v2/live.json");p.parent.mkdir(parents=True,exist_ok=True)\nend=time.time()+90\nwhile time.time()<end:\n p.write_text(json.dumps(dict(at=time.time(),pid=os.getpid(),version="synthetic-launcher",qq_connection=dict(configured=1,ready=1,status="ready"))))\n time.sleep(.1)')
                fake.write_text(fake_code, encoding='utf-8')
                service_port = port()
                args = ['-RuntimeRoot', str(root), '-BotPort', str(service_port), '-TimeoutSeconds', '15']
                fixture_env=os.environ.copy()
                fixture_env.update(PYTHONHOME=sys.base_prefix,DSH_FIXTURE_PORT=str(service_port))
                fixture_env['PATH']=sys.base_prefix+';'+str(Path(os.environ['SystemRoot'])/'System32')
                def run(extra=(), env=None, timeout=30):
                    actual = args.copy()
                    if '-TimeoutSeconds' in extra:
                        actual[actual.index('-TimeoutSeconds')+1] = extra[extra.index('-TimeoutSeconds')+1]
                        extra = tuple(v for i,v in enumerate(extra) if i not in (extra.index('-TimeoutSeconds'), extra.index('-TimeoutSeconds')+1))
                    return subprocess.run([shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(CORE), *actual, *extra],
                        cwd=os.environ['SystemRoot'], env=env or fixture_env, capture_output=True, encoding='utf-8', errors='replace', timeout=timeout)
                def cleanup():
                    state = root/'.launcher/Bot.json'
                    if state.exists():
                        stop_fixture(state)
                        for _ in range(50):
                            try:
                                with socket.create_connection(('127.0.0.1', service_port), timeout=.1): pass
                            except OSError: break
                            time.sleep(.1)
                        time.sleep(.2)  # kernel closes owned Job and log handles
                def collect_children(children):
                    # Finish every fixture launcher before asserting any one
                    # result. Failure/timeout must not abandon its siblings.
                    results=[];errors=[]
                    for child in children:
                        try:
                            out,err=child.communicate(timeout=30)
                        except subprocess.TimeoutExpired as error:
                            child.kill()  # exact Popen created by this fixture
                            out,err=child.communicate(timeout=10)
                            errors.append(error)
                        results.append((child.returncode,out,err))
                    if errors:raise errors[0]
                    return results
                def stop_fixture(state):
                    # Check start time AND nonce before stopping this fixture's
                    # worker. A stale PID must never target an unrelated task.
                    literal=str(state).replace("'","''")
                    script="$s=Get-Content -LiteralPath '"+literal+"' -Raw -Encoding UTF8|ConvertFrom-Json; $p=Get-Process -Id $s.pid -ErrorAction SilentlyContinue; if($p -and $p.StartTime.ToUniversalTime().Ticks.ToString() -eq $s.ticks) { $w=Get-CimInstance Win32_Process -Filter ('ProcessId='+$s.pid); if($w.CommandLine.Contains($s.nonce)) { $p.Kill(); $p.WaitForExit(5000)|Out-Null } }"
                    subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',script],capture_output=True,timeout=10)
                    # Also stop the verified independent dispatcher once this
                    # synthetic instance no longer has service workers.
                    run(('-Action','Stop'))
                try:
                    first = run(); self.assertEqual(first.returncode, 0, first.stdout+first.stderr)
                    state = json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'))
                    self.assertIn('ready', first.stdout)
                    # The tool host uses KILL_ON_JOB_CLOSE. Merely surviving
                    # a launcher exit would not prove independence from it.
                    import ctypes
                    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                    kernel.QueryInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]
                    buffer=ctypes.create_string_buffer(65536)
                    query_job=kernel.QueryInformationJobObject(None,3,buffer,len(buffer),None)
                    in_job=ctypes.c_int()
                    kernel.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
                    self.assertTrue(kernel.IsProcessInJob(ctypes.c_void_p(-1),None,ctypes.byref(in_job)))
                    if in_job.value:
                        self.assertTrue(query_job,'cannot verify parent Job membership')
                        count=ctypes.c_uint32.from_buffer(buffer,4).value
                        inherited=[ctypes.c_size_t.from_buffer(buffer,8+i*ctypes.sizeof(ctypes.c_size_t)).value for i in range(count)]
                        self.assertNotIn(state['pid'],inherited,'worker still belongs to the terminal host Job Object')
                        controller=json.loads((root/'.launcher/Controller.json').read_text(encoding='utf-8-sig'))
                        self.assertNotIn(controller['pid'],inherited,'independent controller still belongs to the terminal host Job Object')
                    second = run(); self.assertEqual(second.returncode, 0, second.stdout+second.stderr)
                    self.assertIn('reuse', second.stdout)
                    self.assertEqual(json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'))['pid'], state['pid'])
                    # Parent launcher is gone; independent worker/service remains.
                    with socket.create_connection(('127.0.0.1', service_port), timeout=2): pass
                    logs = list((root/'logs/launcher').glob('*stdout.log'))
                    for _ in range(30):
                        if any(p.stat().st_size for p in logs): break
                        time.sleep(.1)
                    self.assertIn('合成日志可读', ''.join(p.read_text(encoding='utf-8-sig') for p in logs))
                    env = fixture_env.copy(); env['DSH_LAUNCHER_NO_PAUSE'] = '1'
                    # Minimal Explorer-like PATH excludes the private Codex cache.
                    env['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')
                    entry_command = 'cmd.exe /d /s /c "' + subprocess.list2cmdline([str(ENTRY), *args]) + '"'
                    fallback = subprocess.run(entry_command, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
                    self.assertNotEqual(fallback.returncode, 0, 'cmd must require its Console dependency, not report Bot-only success')
                    self.assertIn('5.1', fallback.stdout)
                    env['PATH'] = str(Path(shells[0]).parent) + ';' + env['PATH']
                    preferred = subprocess.run(entry_command, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
                    self.assertNotEqual(preferred.returncode, 0, 'cmd must report missing Console setup')
                    self.assertIn('PowerShell 7', preferred.stdout)
                    # Concurrent launches serialize on this instance's file lock.
                    command = [shell,'-NoProfile','-NonInteractive','-File',str(CORE),*args]
                    pending = [subprocess.Popen(command, env=fixture_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
                    for code,out,err in collect_children(pending):
                        self.assertEqual(code, 0, (out+err).decode('utf-8',errors='replace'))
                    self.assertEqual(json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8'))['pid'], state['pid'])
                    # A reused PID/start-time mismatch must not authorize reuse or stop.
                    altered = dict(state, ticks='1')
                    (root/'.launcher/Bot.json').write_text(json.dumps(altered), encoding='utf-8')
                    reused_pid = run()
                    self.assertNotEqual(reused_pid.returncode,0)
                    self.assertIn('port conflict',reused_pid.stdout)
                    (root/'.launcher/Bot.json').write_text(json.dumps(state), encoding='utf-8')
                    # Console is opt-in and must never start with empty auth.
                    no_console = run(('-WithConsole',))
                    self.assertNotEqual(no_console.returncode,0)
                    self.assertIn('Bot reuse',no_console.stdout)
                    # Real Node binary, synthetic Console; decrypt only a
                    # temporary credential generated for this fixture.
                    console_port=port()
                    (root/'dsh-console').mkdir()
                    (root/'dsh-console/server.js').write_text(
                        'const API_VER = "synthetic-launcher";const http=require("node:http"),assert=require("node:assert");'
                        "assert.equal(process.env.DSH_RUNTIME_ROOT,process.cwd());"
                        "assert.equal(process.env.HOST,'127.0.0.1');assert.ok(process.env.DSH_CONSOLE_TOKEN.length>=32);"
                        "http.createServer((req,res)=>{if(!req.headers.authorization){res.writeHead(401);res.end();return;}res.setHeader('content-type','application/json');res.end(JSON.stringify({api_ver:API_VER,frontend_ver:API_VER,pid:process.pid}));}).listen(Number(process.env.PORT),'127.0.0.1');setTimeout(()=>process.exit(0),90000);",encoding='utf-8')
                    credential_path=str(cfg/'console-credential.clixml').replace("'","''")
                    credential_script="$ErrorActionPreference='Stop';$secret=New-Object System.Security.SecureString;foreach($letter in 'synthetic-launcher-token-0123456789abcdef'.ToCharArray()){$secret.AppendChar($letter)};$secret.MakeReadOnly();$credential=New-Object PSCredential('dsh',$secret); $credential | Export-Clixml -LiteralPath '"+credential_path+"'"
                    encoded=base64.b64encode(credential_script.encode('utf-16-le')).decode('ascii')
                    created=subprocess.run([shell,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=15)
                    self.assertEqual(created.returncode,0,created.stderr.decode('utf-8',errors='replace'))
                    probe_code="$ErrorActionPreference='Stop';try{$c=Import-Clixml -LiteralPath '"+credential_path+"';$c.GetNetworkCredential().Password.Length}catch{Write-Output ('probe-error:'+$_.Exception.GetType().Name);exit 1}"
                    encoded=base64.b64encode(probe_code.encode('utf-16-le')).decode('ascii')
                    probe=subprocess.run([shell,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,encoding='utf-8',timeout=15)
                    self.assertEqual(probe.stdout.strip(),'41',probe.stdout)
                    console_env=fixture_env.copy();console_env['PATH']=str(Path(shutil.which('node.exe')).parent)+';'+console_env['PATH']
                    # The user cmd must start both by default; explicit ConsolePort
                    # forwards once, avoiding duplicate switch/default arguments.
                    both_command='cmd.exe /d /s /c "'+subprocess.list2cmdline([str(ENTRY),*args,'-ConsolePort',str(console_port)])+'"'
                    together=subprocess.run(both_command,env={**console_env,'DSH_LAUNCHER_NO_PAUSE':'1'},capture_output=True,encoding='utf-8',errors='replace',timeout=45)
                    self.assertEqual(together.returncode,0,together.stdout+together.stderr)
                    self.assertIn('Console ready',together.stdout)
                    repeated=run(('-WithConsole','-ConsolePort',str(console_port)),env=console_env)
                    self.assertEqual(repeated.returncode,0,repeated.stdout+repeated.stderr)
                    self.assertIn('Console reuse',repeated.stdout)
                finally:
                    console_state=root/'.launcher/Console.json'
                    if console_state.exists():
                        # This file was created by the immediately preceding
                        # fixture launch; no production paths are selected.
                        stop_fixture(console_state)
                        time.sleep(.3)
                    cleanup()
                # Stale metadata is harmless after the verified worker exits;
                # a fresh worker must be created, rather than reusing the PID.
                fresh = [subprocess.Popen([shell,'-NoProfile','-NonInteractive','-File',str(CORE),*args],env=fixture_env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
                try:
                    fresh_outputs=[]
                    for code,out,err in collect_children(fresh):
                        self.assertEqual(code,0,(out+err).decode('utf-8',errors='replace'))
                        fresh_outputs.append(out.decode('utf-8'))
                    self.assertEqual(sum('Bot created' in out for out in fresh_outputs),1)
                    self.assertEqual(sum('Bot reuse' in out for out in fresh_outputs),1)
                    self.assertNotEqual(json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8'))['nonce'],state['nonce'])
                finally:
                    cleanup()
                # Required settings, port conflict, timeout and nonzero exit.
                for scenario in ('missing-config', 'missing-dependency', 'conflict', 'timeout', 'exit'):
                    with self.subTest(scenario=scenario):
                        listener = None
                        if scenario == 'missing-config': (cfg/'runtime.json').rename(cfg/'runtime.saved')
                        elif scenario == 'missing-dependency': (root/'venv/Scripts/astrbot.exe').rename(root/'venv/Scripts/astrbot.saved')
                        elif scenario == 'conflict':
                            listener=socket.socket(); listener.bind(('127.0.0.1',service_port)); listener.listen()
                        elif scenario == 'timeout': fake.write_text('import time; time.sleep(90)\n', encoding='utf-8')
                        elif scenario == 'exit': fake.write_text('import sys; sys.exit(23)\n', encoding='utf-8')
                        try:
                            failed = run(('-TimeoutSeconds','3'))
                            self.assertNotEqual(failed.returncode, 0, failed.stdout+failed.stderr)
                            expected = {'missing-config':'Missing required', 'missing-dependency':'Missing Bot dependency', 'conflict':'port conflict', 'timeout':'timeout', 'exit':'exit code 23'}[scenario]
                            self.assertIn(expected, failed.stdout+failed.stderr)
                        finally:
                            cleanup()
                            if listener: listener.close()
                            if scenario == 'missing-config': (cfg/'runtime.saved').rename(cfg/'runtime.json')
                            if scenario == 'missing-dependency': (root/'venv/Scripts/astrbot.saved').rename(root/'venv/Scripts/astrbot.exe')
                print(f'launcher matrix exercised: {Path(shell).name}')


@unittest.skipUnless(os.name == 'nt', 'Windows execution contract')
class LauncherExitCodeRegression(unittest.TestCase):
    def test_cmd_selects_once_and_preserves_quoted_arguments_and_exit_code(self):
        with tempfile.TemporaryDirectory(prefix='dsh cmd args 空格 ') as tmp:
            root=Path(tmp);entry=root/'tools with spaces';entry.mkdir()
            shutil.copyfile(ENTRY,entry/'start-bot.cmd')
            shutil.copyfile(ROOT/'scripts/launcher-shell.ps1',entry/'launcher-shell.ps1')
            (entry/'start-bot.ps1').write_text("param([string]$RuntimeRoot,[string]$Marker,[int]$BotPort)\n[IO.File]::AppendAllText((Join-Path $RuntimeRoot 'calls.txt'),($PSVersionTable.PSVersion.Major.ToString()+'|'+$Marker+'|'+$BotPort+[Environment]::NewLine))\nexit 37\n",encoding='utf-8-sig')
            base=os.environ.copy();base['DSH_LAUNCHER_NO_PAUSE']='1'
            base['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
            command='cmd.exe /d /s /c "'+subprocess.list2cmdline([str(entry/'start-bot.cmd'),'-RuntimeRoot',str(root),'-Marker','two words & 中文 literal','-BotPort','45678'])+'"'
            for preferred,want in [(True,'7'),(False,'5')]:
                env=base.copy()
                if preferred:env['PATH']=str(Path(shutil.which('pwsh.exe')).parent)+';'+env['PATH']
                result=subprocess.run(command,cwd=os.environ['SystemRoot'],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=15)
                self.assertEqual(result.returncode,37,result.stdout+result.stderr)
                lines=(root/'calls.txt').read_text(encoding='utf-8-sig').splitlines()
                self.assertEqual(lines[-1],want+'|two words & 中文 literal|45678')
                self.assertEqual(len(lines),1 if preferred else 2,'failed business script was retried with another shell')

    def test_fast_worker_exit_before_identity_uses_its_exact_observation(self):
        for shell in [shutil.which('pwsh.exe'),shutil.which('powershell.exe')]:
            with self.subTest(shell=Path(shell).name),tempfile.TemporaryDirectory(prefix='dsh early exit ') as tmp:
                root=Path(tmp);(root/'venv/Scripts').mkdir(parents=True);(root/'deployment-config').mkdir()
                shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
                (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"fixture"}',encoding='utf-8')
                (root/'run').write_text('import sys;sys.exit(23)',encoding='utf-8')
                # Fault-inject unavailable process.Path in a temporary copy only.
                copied=root/'start-bot.ps1';copied.write_text(CORE.read_text(encoding='utf-8-sig').replace('function Get-Identity($ProcessId) {','function Get-Identity($ProcessId) {\n    $probe=Get-CimInstance Win32_Process -Filter ("ProcessId="+[int]$ProcessId); if($probe.CommandLine -like "* -InternalWorker *"){return $null}'),encoding='utf-8-sig')
                shutil.copyfile(ROOT/'scripts/launcher-process.cs',root/'launcher-process.cs')
                env=os.environ.copy();env.update(PYTHONHOME=sys.base_prefix,PATH=sys.base_prefix+';'+str(Path(os.environ['SystemRoot'])/'System32'))
                child=subprocess.run([shell,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(copied),'-RuntimeRoot',str(root),'-BotPort',str(port()),'-TimeoutSeconds','8'],cwd=os.environ['SystemRoot'],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=20)
                self.assertEqual(child.returncode,23,child.stdout+child.stderr)

    def test_child_exit_code_is_preserved_under_both_real_shells(self):
        for shell in [shutil.which('pwsh.exe'), shutil.which('powershell.exe')]:
            with self.subTest(shell=Path(shell).name), tempfile.TemporaryDirectory(prefix='dsh exit 空格 ') as tmp:
                root=Path(tmp);(root/'venv/Scripts').mkdir(parents=True);(root/'deployment-config').mkdir()
                shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
                (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"fixture"}',encoding='utf-8')
                (root/'run').write_text('import sys;sys.exit(23)',encoding='utf-8')
                env=os.environ.copy();env['PYTHONHOME']=sys.base_prefix
                env['PATH']=sys.base_prefix+';'+str(Path(os.environ['SystemRoot'])/'System32')
                child=subprocess.run([shell,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(CORE),
                    '-RuntimeRoot',str(root),'-BotPort',str(port()),'-TimeoutSeconds','8'],cwd=os.environ['SystemRoot'],
                    env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=20)
                self.assertIn('exit code 23',child.stdout+child.stderr)
                self.assertEqual(child.returncode,23,child.stdout+child.stderr)


if __name__ == '__main__': unittest.main()
