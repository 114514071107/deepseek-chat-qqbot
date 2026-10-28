"""Standalone cmd uses actual instance controller and truthful final result."""
import json,os,shutil,socket,subprocess,tempfile,unittest,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
class ConsoleEntry(unittest.TestCase):
    def test_missing_credential_fails_and_cmd_propagates_final_result(self):
        with tempfile.TemporaryDirectory(prefix='dsh 独立 console ') as tmp:
            root=Path(tmp);(root/'dsh-console').mkdir();(root/'deployment-config').mkdir()
            for name in ('start-bot.ps1','launcher-shell.ps1','launcher-process.cs'):shutil.copyfile(REPO/'scripts'/name,root/name)
            for name in ('start-dsh-console.cmd','start-dsh-console.vbs'):shutil.copyfile(REPO/'console'/name,root/'dsh-console'/name)
            (root/'dsh-console/server.js').write_text('throw Error("must never start without credential");')
            command='cmd.exe /d /s /c "'+subprocess.list2cmdline([str(root/'dsh-console/start-dsh-console.cmd'),'-RuntimeRoot',str(root)])+'"'
            p=subprocess.run(command,cwd=os.environ['SystemRoot'],capture_output=True,encoding='utf-8',errors='replace',timeout=25)
            time.sleep(1)  # old detached entry exits asynchronously; preserve primary failure
            self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertNotIn('started on',p.stdout)
            # Version of the core for this isolated return-code contract, no services.
            (root/'start-bot.ps1').write_text('param([string]$Component,[string]$RuntimeRoot)\nif($Component -ne "Console"){exit 99}\nexit 37',encoding='utf-8-sig')
            p=subprocess.run(command,cwd=os.environ['SystemRoot'],capture_output=True,timeout=20)
            self.assertEqual(p.returncode,37,p.stdout+p.stderr)
            p=subprocess.run(['cscript.exe','//nologo',str(root/'dsh-console/start-dsh-console.vbs')],cwd=os.environ['SystemRoot'],capture_output=True,timeout=20)
            self.assertEqual(p.returncode,37,p.stdout+p.stderr)
