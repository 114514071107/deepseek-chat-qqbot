import unittest,tempfile,json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from conversation_cleanup import plan,apply_plan,restore
from session_scope import Scope
class Cleanup(unittest.TestCase):
 def test_plan_backup_quarantine_idempotence_and_private_chat_preservation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'data';root.mkdir();backup=Path(tmp)/'recovery';m=root/'memories';m.mkdir()
   group=Scope('qq_official','bot','self','member','G','m',False);private=Scope('qq_official','bot','self','private','','p',True)
   (root/'scopes_v2.json').write_text(json.dumps({group.key:group.source(),private.key:private.source()}))
   for key,txt in [(group.memory_key,'OLD-MEMBER'),(private.key,'KEEP-PRIVATE'),(group.group_key,'KEEP-GROUP'),('unknown','MIXED')]: (m/(key+'.md')).write_text(txt)
   (root/'history_v2.json').write_text('SYNTHETIC RAW CHAT');chat=(root/'history_v2.json').read_bytes()
   p=plan(root);self.assertEqual(len(p['actions']),2);apply_plan(root,backup,p)
   self.assertFalse((m/(group.memory_key+'.md')).exists());self.assertFalse((m/'unknown.md').exists());self.assertEqual((m/(private.key+'.md')).read_text(),'KEEP-PRIVATE');self.assertEqual((m/(group.group_key+'.md')).read_text(),'KEEP-GROUP')
   self.assertEqual((root/'history_v2.json').read_bytes(),chat);self.assertEqual(plan(root)['actions'],[]);apply_plan(root,backup,plan(root));self.assertTrue((backup/'original/memories/unknown.md').exists());restore(backup);self.assertEqual((m/'unknown.md').read_text(),'MIXED');self.assertFalse((root/'conversation_storage_v1.json').exists());self.assertEqual((root/'history_v2.json').read_bytes(),chat)
 def test_drift_and_backup_inside_root_refused_without_removing_any_file(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'data';root.mkdir();(root/'memories').mkdir();f=root/'memories/x.md';f.write_text('before');p=plan(root);f.write_text('changed')
   with self.assertRaises(ValueError):apply_plan(root,Path(tmp)/'backup',p)
   self.assertEqual(f.read_text(),'changed')
   with self.assertRaises(ValueError):apply_plan(root,root/'backup',plan(root))

 def test_new_private_memory_after_cleaning_ambiguous_key_is_never_cleaned_again(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'data';root.mkdir();backup=Path(tmp)/'backup';(root/'memories').mkdir()
   group=Scope('qq_official','instance','self','same','G','m',False);private=Scope('qq_official','instance','self','same','','p',True)
   (root/'scopes_v2.json').write_text(json.dumps({group.key:group.source(),private.key:private.source()}));f=root/'memories'/(private.key+'.md');f.write_text('OLD-MIXED')
   apply_plan(root,backup,plan(root));f.write_text('NEW-PRIVATE-ONLY')
   self.assertEqual(plan(root)['actions'],[]);self.assertEqual(f.read_text(),'NEW-PRIVATE-ONLY')
 def test_failed_restore_revokes_memory_permission_before_reintroducing_any_old_material(self):
  from unittest.mock import patch
  from conversation_storage import memory_available
  import os
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'data';root.mkdir();backup=Path(tmp)/'backup';(root/'memories').mkdir()
   group=Scope('qq_official','instance','self','same','G','m',False);private=Scope('qq_official','instance','self','same','','p',True)
   (root/'scopes_v2.json').write_text(json.dumps({group.key:group.source(),private.key:private.source()}));f=root/'memories'/(private.key+'.md');f.write_text('OLD-MIXED');(root/'memories/zunknown.md').write_text('UNKNOWN')
   apply_plan(root,backup,plan(root));self.assertTrue(memory_available(root,private.key));original=os.replace;calls=[]
   def failing(a,b):
    calls.append(str(b))
    if len(calls)==2:raise OSError('synthetic interrupted restore')
    return original(a,b)
   with patch('conversation_cleanup.os.replace',side_effect=failing):
    with self.assertRaises(OSError):restore(backup)
   self.assertFalse(memory_available(root,private.key))

 def test_empty_legacy_material_still_initializes_ambiguous_storage_and_restores(self):
  from conversation_storage import memory_available
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'data';root.mkdir();backup=Path(tmp)/'backup'
   group=Scope('qq_official','instance','self','same','G','m',False);private=Scope('qq_official','instance','self','same','','p',True)
   (root/'scopes_v2.json').write_text(json.dumps({group.key:group.source(),private.key:private.source()}))
   proposal=plan(root);self.assertEqual(proposal['actions'],[]);apply_plan(root,backup,proposal);self.assertTrue(memory_available(root,private.key));self.assertTrue((backup/'manifest.json').exists())
   restore(backup);self.assertFalse((root/'conversation_storage_v1.json').exists())
