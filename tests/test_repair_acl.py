import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt','Windows ACL')
class ConfigACL(unittest.TestCase):
    def test_plan_rejects_data_as_backup_before_any_permission_change(self):
        with tempfile.TemporaryDirectory(prefix='dsh-acl-reject-') as tmp:
            data=Path(tmp)/'data';data.mkdir();(data/'cmd_config.json').write_text('{}')
            shell=shutil.which('pwsh.exe')
            command="(Get-Acl -LiteralPath '"+str(data).replace("'","''")+"').Sddl"
            before=subprocess.check_output([shell,'-NoProfile','-NonInteractive','-Command',command])
            result=subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(REPO/'scripts/protect-config-acl.ps1'),'-RuntimeRoot',tmp,'-BackupDirectory',str(data),'-Mode','Plan'],capture_output=True,timeout=15)
            self.assertNotEqual(result.returncode,0,'Plan must reject data itself, before touching its ACL')
            self.assertFalse((data/'acl-rollback.json').exists())
            after=subprocess.check_output([shell,'-NoProfile','-NonInteractive','-Command',command])
            self.assertEqual(before,after)
    def test_plan_apply_restricted_token_atomic_save_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix='dsh-acl-') as tmp:
            root=Path(tmp);(root/'data').mkdir();config=root/'data/cmd_config.json';config.write_text('{"synthetic":true}',encoding='utf-8')
            backup=root/'rollback';shell=shutil.which('pwsh.exe')
            script=REPO/'scripts/protect-config-acl.ps1'
            def run(mode):return subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(script),'-RuntimeRoot',tmp,'-BackupDirectory',str(backup),'-Mode',mode],capture_output=True,encoding='utf-8',timeout=20)
            before=config.read_bytes();planned=run('Plan');self.assertEqual(planned.returncode,0,planned.stderr)
            applied=run('Apply');self.assertEqual(applied.returncode,0,applied.stderr)
            self.assertEqual(config.read_bytes(),before)
            # Actual owner read/save, then actual Windows restricted-token read/write.
            temp=root/'data/.cmd_config.synthetic.tmp';temp.write_text('{"synthetic":2}',encoding='utf-8');os.replace(temp,config)
            code="Add-Type -Path '"+str(REPO/'tests/restricted-file-probe.cs').replace("'","''")+"'; [RestrictedFileProbe]::Probe('"+str(config).replace("'","''")+"')|ConvertTo-Json -Compress"
            probe=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',code],capture_output=True,encoding='utf-8',timeout=20)
            self.assertEqual(probe.returncode,0,probe.stderr);self.assertEqual(json.loads(probe.stdout),[5,5])
            self.assertEqual(config.read_text(),'{"synthetic":2}')
            restored=run('Restore');self.assertEqual(restored.returncode,0,restored.stderr)
            saved=json.loads((backup/'acl-rollback.json').read_text(encoding='utf-8-sig'))
            check=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',"(Get-Acl -LiteralPath '"+str(root/'data').replace("'","''")+"').Sddl"],capture_output=True,encoding='utf-8',timeout=10)
            # Windows canonicalizes the auto-inherited bookkeeping flag (AI)
            # on restore. DACL entries and protected/unprotected inheritance
            # must still be exactly the same, including every inherited ACE.
            self.assertEqual(check.stdout.strip().replace('D:AI','D:'),saved['targets'][0]['sddl'].replace('D:AI','D:'))
