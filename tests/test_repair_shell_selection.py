"""Executable presence is insufficient; preflight must precede any business call."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt','Windows executable selection')
class ShellSelection(unittest.TestCase):
    def test_unusable_first_pwsh_falls_back_before_one_business_call(self):
        with tempfile.TemporaryDirectory(prefix='dsh shell preflight ') as temp:
            root=Path(temp);bad=root/'bad shell';bad.mkdir()
            shutil.copyfile(Path(sys.base_prefix)/'python.exe',bad/'pwsh.exe')
            for name in ('python312.dll','python3.dll'):shutil.copyfile(Path(sys.base_prefix)/name,bad/name)
            for name in ('start-bot.cmd','launcher-shell.ps1'):
                source=REPO/'scripts'/name
                if source.exists():shutil.copyfile(source,root/name)
            (root/'start-bot.ps1').write_text("param([string]$RuntimeRoot)\n[IO.File]::AppendAllText(($RuntimeRoot+'\\calls.txt'),'once'+[Environment]::NewLine)\nexit 37\n",encoding='utf-8-sig')
            env={**os.environ,'PATH':str(bad)+';'+str(Path(os.environ['SystemRoot'])/'System32'),'DSH_LAUNCHER_NO_PAUSE':'1'}
            cmd='cmd.exe /d /s /c "'+subprocess.list2cmdline([str(root/'start-bot.cmd'),'-RuntimeRoot',str(root)])+'"'
            result=subprocess.run(cmd,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=25)
            self.assertEqual(result.returncode,37,'S02: first unusable executable prevented valid fallback: '+result.stdout+result.stderr)
            self.assertEqual((root/'calls.txt').read_text().splitlines(),['once'],'Business action must run once, never retry after its exit 37')
