"""Start is an observation of an existing instance, never implicit permission to stop it."""
import ctypes
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

REPO=Path(__file__).resolve().parents[1]
CORE=Path(os.environ.get('DSH_TEST_LAUNCHER_CORE',str(REPO/'scripts/start-bot.ps1')))
SHELL=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')

def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

def alive(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,pid)
    if not handle:return False
    try:return kernel.WaitForSingleObject(handle,0)==258
    finally:kernel.CloseHandle(handle)

@unittest.skipUnless(os.name=='nt','Windows instance ownership')
class ExistingStartOwnership(unittest.TestCase):
    def test_default_cold_start_requires_loaded_heartbeat_not_just_port(self):
        with tempfile.TemporaryDirectory(prefix='dsh default readiness ') as temp:
            root=Path(temp);(root/'venv/Scripts').mkdir(parents=True);(root/'deployment-config').mkdir()
            shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
            (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"synthetic"}',encoding='utf-8')
            p=unused_port()
            (root/'run').write_text('import socket,time\ns=socket.socket();s.bind(("127.0.0.1",'+str(p)+'));s.listen();time.sleep(25)',encoding='utf-8')
            env={**os.environ,'PYTHONHOME':sys.base_prefix,'PATH':sys.base_prefix+';'+str(Path(os.environ['SystemRoot'])/'System32')}
            args=[SHELL,'-NoProfile','-NonInteractive','-File',str(REPO/'scripts/start-bot.ps1'),'-RuntimeRoot',str(root),'-BotPort',str(p),'-TimeoutSeconds','2']
            try:
                result=subprocess.run(args,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
                self.assertNotEqual(result.returncode,0,'S01: port alone reported startup success: '+result.stdout)
                self.assertTrue((root/'.launcher/Bot.json').exists(), 'Launcher never created worker state; primary result: '+result.stdout+result.stderr)
                state=json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'))
                self.assertFalse(alive(state['pid']),'Newly created failed startup must clean its verified worker')
            finally:subprocess.run([*args,'-Action','Stop'],env=env,capture_output=True,timeout=15)

    def test_reused_readiness_timeout_preserves_original_instance(self):
        with tempfile.TemporaryDirectory(prefix='dsh reuse safety ') as temp:
            root=Path(temp);(root/'venv/Scripts').mkdir(parents=True);(root/'deployment-config').mkdir()
            shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
            (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"synthetic-only"}',encoding='utf-8')
            (root/'data/plugins/astrbot_plugin_dsh_soul').mkdir(parents=True)
            (root/'data/plugins/astrbot_plugin_dsh_soul/build_info.py').write_text('BUILD_VERSION = "synthetic-startup"',encoding='utf-8')
            p=unused_port()
            (root/'run').write_text('''import os,socket,time,json,pathlib
r=pathlib.Path.cwd();s=socket.socket();s.bind(("127.0.0.1",PORT));s.listen()
q=r/"dsh_data/admin_v2/live.json";q.parent.mkdir(parents=True,exist_ok=True)
end=time.time()+120
while time.time()<end:
 mode=(r/"mode").read_text() if (r/"mode").exists() else "ready"
 row=dict(at=time.time()+(60 if mode=="future" else -60 if mode=="stale" else 0),pid=os.getpid(),version="wrong" if mode=="wrong_version" else "synthetic-startup",qq_connection=dict(status="connecting" if mode=="connecting" else "ready",configured=1,ready=int(mode!="connecting")))
 if mode=="missing_qq":row.pop("qq_connection")
 q.write_text(json.dumps(row));time.sleep(.1)
'''.replace('PORT',str(p)),encoding='utf-8')
            env={**os.environ,'PYTHONHOME':sys.base_prefix,'PATH':sys.base_prefix+';'+str(Path(os.environ['SystemRoot'])/'System32')}
            def run(action='Start',timeout=8):
                return subprocess.run([SHELL,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(CORE),'-RuntimeRoot',str(root),'-Component','Bot','-BotPort',str(p),'-Action',action,'-VerifyReady','-TimeoutSeconds',str(timeout)],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
            state=None
            try:
                first=run();self.assertEqual(first.returncode,0,first.stdout+first.stderr+'\n'+str([p.read_text(encoding='utf-8-sig') for p in (root/'.launcher').glob('*.json')]))
                state=json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'))
                for mode in ('connecting','stale','future','wrong_version','missing_qq'):
                    (root/'mode').write_text(mode);time.sleep(.25)
                    repeat=run(timeout=1)
                    self.assertNotEqual(repeat.returncode,0,mode+repeat.stdout)
                    self.assertTrue(alive(state['pid']),'S08: repeated Start stopped the pre-existing verified worker: '+mode)
                    with socket.create_connection(('127.0.0.1',p),timeout=1):pass
                    self.assertEqual(json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'))['nonce'],state['nonce'])
                (root/'mode').write_text('ready');time.sleep(.25)
                recovered=run();self.assertEqual(recovered.returncode,0,recovered.stdout+recovered.stderr)
                self.assertEqual(json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'))['pid'],state['pid'])
            finally:
                stopped=run('Stop')
                if state and alive(state['pid']):raise AssertionError('Synthetic worker cleanup failed: '+stopped.stdout)
                time.sleep(.2)

    def test_dual_component_summary_cannot_hide_unready_bot(self):
        with tempfile.TemporaryDirectory(prefix='dsh component status ') as temp:
            root=Path(temp);(root/'venv/Scripts').mkdir(parents=True);(root/'deployment-config').mkdir()
            shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
            (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"synthetic"}',encoding='utf-8')
            build=root/'data/plugins/astrbot_plugin_dsh_soul';build.mkdir(parents=True)
            (build/'build_info.py').write_text('BUILD_VERSION = "synthetic"',encoding='utf-8')
            bp,cp=unused_port(),unused_port()
            (root/'run').write_text('import os,socket,time,json,pathlib\ns=socket.socket();s.bind(("127.0.0.1",'+str(bp)+'));s.listen()\np=pathlib.Path("dsh_data/admin_v2/live.json");p.parent.mkdir(parents=True,exist_ok=True)\nwhile True:\n p.write_text(json.dumps(dict(pid=os.getpid(),version="synthetic",at=time.time(),qq_connection=dict(configured=1,ready=1,status="ready"))))\n time.sleep(.1)',encoding='utf-8')
            (root/'dsh-console').mkdir()
            (root/'dsh-console/server.js').write_text('const API_VER = "synthetic";require("node:http").createServer((q,r)=>{if(!q.headers.authorization){r.writeHead(401);r.end();return;}r.setHeader("content-type","application/json");r.end(JSON.stringify({api_ver:API_VER,frontend_ver:API_VER,pid:process.pid}));}).listen('+str(cp)+',"127.0.0.1");',encoding='utf-8')
            env={**os.environ,'PYTHONHOME':sys.base_prefix,'PATH':sys.base_prefix+';'+os.environ['PATH']}
            prep="$env:PSModulePath=$PSHOME+'\\Modules';$s=ConvertTo-SecureString 'synthetic-component-credential-0123456789' -AsPlainText -Force;New-Object PSCredential('dsh',$s)|Export-Clixml -LiteralPath '"+str(root/'deployment-config/console-credential.clixml').replace("'","''")+"'"
            subprocess.run([SHELL,'-NoProfile','-Command',prep],capture_output=True,check=True)
            args=[SHELL,'-NoProfile','-NonInteractive','-File',str(CORE),'-RuntimeRoot',str(root),'-WithConsole','-BotPort',str(bp),'-ConsolePort',str(cp),'-TimeoutSeconds','8','-VerifyReady']
            try:
                started=subprocess.run(args,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=40)
                self.assertEqual(started.returncode,0,started.stdout+started.stderr)
                (build/'build_info.py').write_text('BUILD_VERSION = "wrong-loaded-version"',encoding='utf-8')
                status=subprocess.run([*args,'-Action','Status'],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
                summary=json.loads(status.stdout.strip().splitlines()[-1])
                self.assertEqual(summary.get('component'),'All','S05: final Console result was mislabeled as Bot: '+status.stdout)
                self.assertEqual(summary['status'],'partial')
                self.assertFalse(summary['ok'])
                self.assertEqual([row['component'] for row in summary['results']],['Bot','Console'])
                self.assertEqual(summary['results'][0]['status'],'not_ready')
                self.assertEqual(summary['results'][1]['status'],'succeeded')
                self.assertNotEqual(status.returncode,0)
            finally:
                stopped=subprocess.run([*args,'-Action','Stop'],env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
                self.assertEqual(stopped.returncode,0,stopped.stdout+stopped.stderr)
