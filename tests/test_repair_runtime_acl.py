"""ACL changes only in disposable roots; test the actual Windows access check."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]
SHELL = shutil.which('pwsh.exe')
SCRIPT = Path(os.environ.get('DSH_TEST_ACL_SCRIPT', REPO / 'scripts/protect-config-acl.ps1'))


@contextmanager
def inherited_fixture():
    # Python TemporaryDirectory deliberately uses a Windows mode-0700 DACL;
    # that ancestor can reject a restricted token before our test object does.
    base = Path(tempfile.gettempdir()).resolve()
    outer = base / ('dsh-acl-runtime-' + uuid.uuid4().hex)
    outer.mkdir()
    try:
        yield outer
    finally:
        if outer.resolve().parent != base or not outer.name.startswith('dsh-acl-runtime-'):
            raise AssertionError('Unexpected ACL fixture cleanup target')
        shutil.rmtree(outer)


@unittest.skipUnless(os.name == 'nt' and SHELL, 'Windows ACL and installed PowerShell 7')
class RuntimeACL(unittest.TestCase):
    def invoke(self, root, backup, mode):
        return subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-File', str(SCRIPT),
            '-RuntimeRoot', str(root), '-BackupDirectory', str(backup), '-Mode', mode,
            '-RelativeTargets', '.'], capture_output=True, encoding='utf-8', timeout=30)

    def command(self, code):
        result = subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-Command', code],
            capture_output=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_inspect_has_no_backup_or_permission_side_effect(self):
        with tempfile.TemporaryDirectory(prefix='dsh acl inspect ') as temp:
            root = Path(temp) / 'runtime'; root.mkdir()
            (root / 'secret.json').write_text('synthetic')
            backup = Path(temp) / 'backup'
            literal = str(root).replace("'", "''")
            before = self.command("(Get-Acl -LiteralPath '" + literal + "').Sddl")
            result = self.invoke(root, backup, 'Inspect')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(backup.exists(), 'Read-only inspection created a backup')
            self.assertEqual(before, self.command("(Get-Acl -LiteralPath '" + literal + "').Sddl"))
            self.assertEqual(json.loads(result.stdout)['affected_objects'], 2)

    def test_runtime_root_protects_code_secrets_logs_and_parent_replacement_then_restores(self):
        with inherited_fixture() as temp:
            root = Path(temp) / 'runtime'; root.mkdir()
            for name in ('data', 'data/plugins', 'logs', 'dsh-console'):
                (root / name).mkdir(exist_ok=True)
            for name in ('data/secret.json', 'data/plugins/main.py', 'logs/worker.log', 'dsh-console/server.js'):
                (root / name).write_text('synthetic', encoding='utf-8')
            backup = Path(temp) / 'backup'
            literal = str(root).replace("'", "''")
            # A restricting SID supplies a real before/after access check, not
            # merely a token which would have been denied before the repair.
            self.command("foreach($p in @((Get-Item -LiteralPath '" + literal + "'))+@(Get-ChildItem -LiteralPath '" + literal + "' -Recurse)){$a=Get-Acl -LiteralPath $p.FullName;$a.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-5-12'),'FullControl','Allow'));Set-Acl -LiteralPath $p.FullName -AclObject $a}")
            probe = "Add-Type -Path '" + str(REPO / 'tests/restricted-file-probe.cs').replace("'", "''") + "';"
            container = str(Path(temp)).replace("'", "''")
            self.command("$a=Get-Acl -LiteralPath '" + container + "';$a.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-5-12'),'FullControl','ContainerInherit,ObjectInherit','None','Allow'));$d=[Security.AccessControl.DirectorySecurity]::new();$d.SetSecurityDescriptorSddlForm($a.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access),[Security.AccessControl.AccessControlSections]::Access);[IO.FileSystemAclExtensions]::SetAccessControl((Get-Item -LiteralPath '" + container + "'),$d)")
            def access(path):
                return json.loads(self.command(probe + "[RestrictedFileProbe]::Probe('" + str(path).replace("'", "''") + "')|ConvertTo-Json -Compress"))
            self.assertEqual(access(root / 'data/secret.json'), [0, 0])
            planned = self.invoke(root, backup, 'Plan')
            self.assertEqual(planned.returncode, 0, planned.stderr)
            applied = self.invoke(root, backup, 'Apply')
            self.assertEqual(applied.returncode, 0, applied.stderr)
            for name in ('data/secret.json', 'data/plugins/main.py', 'logs/worker.log', 'dsh-console/server.js'):
                self.assertEqual(access(root / name), [5, 5], name)
                self.assertEqual((root / name).read_text(), 'synthetic')
            parent = json.loads(self.command(probe + "[RestrictedFileProbe]::ProbeDirectory('" + literal + "')|ConvertTo-Json -Compress"))
            self.assertEqual(parent, [5, 5], 'Untrusted token can create or delete children of the instance')
            pending = root / 'data/.secret.tmp'; pending.write_text('updated')
            os.replace(pending, root / 'data/secret.json')
            self.assertEqual((root / 'data/secret.json').read_text(), 'updated')
            restored = self.invoke(root, backup, 'Restore')
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(access(root / 'data/secret.json'), [0, 0])
            self.assertEqual((root / 'data/secret.json').read_text(), 'updated', 'Rollback overwrote content')
            record = str(backup / 'acl-rollback.json').replace("'", "''")
            restored_objects = json.loads(self.command("$s=Get-Content -LiteralPath '" + record + "' -Raw|ConvertFrom-Json;$ok=@();foreach($r in $s.targets){$a=Get-Acl -LiteralPath $r.path;$e=if(Test-Path -LiteralPath $r.path -PathType Container){[Security.AccessControl.DirectorySecurity]::new()}else{[Security.AccessControl.FileSecurity]::new()};$e.SetSecurityDescriptorSddlForm($r.sddl);$actual=@($a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|ForEach-Object {$_.IdentityReference.Value+':'+$_.FileSystemRights+':'+$_.InheritanceFlags+':'+$_.PropagationFlags+':'+$_.AccessControlType+':'+$_.IsInherited}|Sort-Object);$expected=@($e.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|ForEach-Object {$_.IdentityReference.Value+':'+$_.FileSystemRights+':'+$_.InheritanceFlags+':'+$_.PropagationFlags+':'+$_.AccessControlType+':'+$_.IsInherited}|Sort-Object);$ok+=($a.AreAccessRulesProtected -eq $e.AreAccessRulesProtected -and !(Compare-Object $actual $expected))};ConvertTo-Json -InputObject $ok -Compress"))
            self.assertTrue(all(restored_objects), 'Per-object ACEs or inheritance did not restore')

    def test_apply_rejects_new_unreviewed_object_before_changing_any_dacl(self):
        with tempfile.TemporaryDirectory(prefix='dsh acl drift ') as temp:
            root = Path(temp) / 'runtime'; root.mkdir()
            (root / 'code.py').write_text('synthetic')
            backup = Path(temp) / 'backup'
            planned = self.invoke(root, backup, 'Plan')
            self.assertEqual(planned.returncode, 0, planned.stderr)
            literal = str(root).replace("'", "''")
            before = self.command("(Get-Acl -LiteralPath '" + literal + "').Sddl")
            (root / 'new.log').write_text('new')
            result = self.invoke(root, backup, 'Apply')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Target membership changed since Plan', result.stderr)
            self.assertEqual(before, self.command("(Get-Acl -LiteralPath '" + literal + "').Sddl"))
