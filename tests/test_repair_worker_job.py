"""Abnormal termination of verified temporary workers must end their application."""
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
from test_repair_startup_ownership import REPO,SHELL,unused_port

@unittest.skipUnless(os.name=='nt','Windows Job ownership')
class WorkerJob(unittest.TestCase):
    def test_application_dies_with_worker_under_real_supported_shells(self):
        choices=[SHELL,str(Path.home()/'AppData/Local/Microsoft/WindowsApps/pwsh.exe')]
        for shell in choices:
            with self.subTest(shell=Path(shell).name),tempfile.TemporaryDirectory(prefix='dsh job ownership ') as temp:
                root=Path(temp);(root/'venv/Scripts').mkdir(parents=True);(root/'deployment-config').mkdir()
                shutil.copyfile(Path(sys.base_prefix)/'python.exe',root/'venv/Scripts/astrbot.exe')
                (root/'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"synthetic"}',encoding='utf-8')
                build=root/'data/plugins/astrbot_plugin_dsh_soul';build.mkdir(parents=True);(build/'build_info.py').write_text('BUILD_VERSION = "synthetic-job"',encoding='utf-8')
                p=unused_port()
                (root/'run').write_text('import socket,time,os,pathlib,json\nr=pathlib.Path.cwd();(r/"app-pid").write_text(str(os.getpid()))\ns=socket.socket();s.bind(("127.0.0.1",'+str(p)+'));s.listen()\nf=r/"dsh_data/admin_v2/live.json";f.parent.mkdir(parents=True,exist_ok=True)\nend=time.time()+45\nwhile time.time()<end:\n f.write_text(json.dumps(dict(at=time.time(),pid=os.getpid(),version="synthetic-job",qq_connection=dict(configured=1,ready=1,status="ready"))))\n time.sleep(.1)',encoding='utf-8')
                env={**os.environ,'PYTHONHOME':sys.base_prefix,'PATH':sys.base_prefix+';'+str(Path(os.environ['SystemRoot'])/'System32')}
                args=[shell,'-NoProfile','-NonInteractive','-File',str(REPO/'scripts/start-bot.ps1'),'-RuntimeRoot',str(root),'-BotPort',str(p),'-TimeoutSeconds','8']
                handles=[];kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];kernel.OpenProcess.restype=ctypes.c_void_p
                kernel.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                try:
                    launch=subprocess.run(args,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
                    self.assertEqual(launch.returncode,0,launch.stdout+launch.stderr)
                    state=json.loads((root/'.launcher/Bot.json').read_text(encoding='utf-8-sig'));app_pid=int((root/'app-pid').read_text())
                    # State is from this unique fixture. Stop verifies the
                    # nonce/ticks/exe before abnormal termination is injected.
                    literal=str(root/'.launcher/Bot.json').replace("'","''")
                    check="$env:PSModulePath=$PSHOME+'\\Modules';$s=Get-Content -LiteralPath '"+literal+"' -Raw|ConvertFrom-Json;$p=Get-Process -Id $s.pid;$w=Get-CimInstance Win32_Process -Filter ('ProcessId='+$s.pid);if($p.Path -ne $s.exe -or $p.StartTime.ToUniversalTime().Ticks.ToString() -ne $s.ticks -or !$w.CommandLine.Contains($s.nonce)){exit 1}"
                    verified=subprocess.run([SHELL,'-NoProfile','-Command',check],capture_output=True,timeout=10)
                    self.assertEqual(verified.returncode,0,'Temporary worker identity not verified')
                    for pid in (state['pid'],app_pid):
                        handle=kernel.OpenProcess(0x100001,False,pid);self.assertTrue(handle);handles.append(handle)
                    self.assertTrue(kernel.TerminateProcess(handles[0],1))
                    self.assertEqual(kernel.WaitForSingleObject(handles[1],5000),0,'S04: application escaped worker Job')
                    with self.assertRaises(OSError):socket.create_connection(('127.0.0.1',p),timeout=.2)
                finally:
                    for handle in handles:
                        if kernel.WaitForSingleObject(handle,0)==258:kernel.TerminateProcess(handle,1);kernel.WaitForSingleObject(handle,3000)
                        kernel.CloseHandle(handle)
                    stopped=subprocess.run([*args,'-Action','Stop'],env=env,capture_output=True,timeout=20)
                    self.assertEqual(stopped.returncode,0,stopped.stdout.decode('utf-8',errors='replace'))
