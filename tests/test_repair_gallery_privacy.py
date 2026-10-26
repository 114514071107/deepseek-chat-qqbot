"""Real gallery and send boundaries, AST-only plugin, synthetic files/SQLite."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from types import SimpleNamespace

from repair_pipeline_support import load_pipeline, PLUGIN
from state_store import read_json, write_json
from test_repair_session_scope import ScopeEvent
from qq_delivery import DeliveryResult


class GalleryPrivacy(unittest.IsolatedAsyncioTestCase):
    async def test_published_content_is_verified_by_hash_not_folder_or_missing_metadata(self):
        from gallery_policy import shared_file
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pack=root/'arbitrary';pack.mkdir();data=b'synthetic published meme'
            (pack/'image.png').write_bytes(data)
            digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            catalog={'published_sources':[{'repository':'https://example.invalid/synthetic-public','revision':'synthetic','git_blobs':[digest]}]}
            with patch('gallery_policy._json',side_effect=lambda path:catalog if path.name=='public-gallery-source.json' else {}):
                self.assertEqual(shared_file(root,'arbitrary','image.png',content=True),data)
                (pack/'image.png').write_bytes(b'synthetic private replacement')
                self.assertIsNone(shared_file(root,'arbitrary','image.png'))

    async def test_unknown_images_never_harvest_and_legacy_is_not_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            obj,ns=load_pipeline(root,names=('harvest_images','_harvest_one','_harvest_path','list_stickers','_send_sticker_row'))
            self.addAsyncCleanup(obj.runtime.stop); self.addAsyncCleanup(obj.resources.close)
            ns.update(sqlite3=sqlite3,PACKS=str(root/'sticker_packs'),_save=write_json,_load=read_json)
            tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
            names={'_all_sticker_rows','_gallery_db_rows','_pick_sticker','_ensure_collect_pack','_gallery_shared','_meme_catalog_text'}
            for n in tree.body:
                if getattr(n,'name','') in names or isinstance(n,ast.Assign) and any(getattr(t,'id','') in {'COLLECT_PACK','_MEMES_DDL','MOOD_WORDS'} for t in n.targets):
                    exec(compile(ast.Module(body=[n],type_ignores=[]),'<gallery>','exec'),ns)
            from PIL import Image as PILImage
            import random
            image=root/'private.gif'; PILImage.frombytes('RGB',(64,64),random.Random(9).randbytes(12288)).save(image,format='PNG')
            class Image:
                def __init__(self): self.url=str(image);self.file=str(image)
                @staticmethod
                def fromFileSystem(p): return SimpleNamespace(file=p)
                @staticmethod
                def fromBytes(data): return SimpleNamespace(data=data)
            ns.update(Image=Image,_conf=lambda *a:True)
            try:
                from gallery_policy import shared_file, auto_collectible
                ns.update(shared_file=shared_file,auto_collectible=auto_collectible)
            except ImportError: pass
            obj._err=lambda *a:None
            obj._perm=lambda *a:True
            spawned=[]
            def spawn(coro,**kw): spawned.append(kw);coro.close()
            obj._spawn=spawn
            for group in ('','group-A'):
                event=ScopeEvent('A',group);event.message_str='[表情] GIF sticker';event.message_obj.message=[Image(),Image()]
                await obj.harvest_images(event)
            self.assertEqual(spawned,[], 'unknown/mixed images must be rejected before background work')
            scope=obj._scope(ScopeEvent('A'))
            await obj._harvest_one(scope.key,str(image),str(root/'ledger.json'))
            self.assertFalse((root/'sticker_packs/collect-001').exists())
            # An old automatic entry remains on disk; B cannot list/pick/send it.
            pack=root/'sticker_packs/collect-001';pack.mkdir(parents=True)
            original=pack/'private.png';original.write_bytes(image.read_bytes())
            with closing(sqlite3.connect(pack/'index.db')) as conn:
                conn.execute('create table memes(path,tag,caption,keywords,mtime)')
                conn.execute('insert into memes values(?,?,?,?,?)',('private.png','daily','PRIVATE_SENTINEL','PRIVATE_SENTINEL',1))
                conn.commit()
            eventB=ScopeEvent('B','group-B');obj._scope(eventB)
            self.assertNotIn('PRIVATE_SENTINEL',await obj.list_stickers(eventB))
            self.assertNotIn('PRIVATE_SENTINEL',ns['_meme_catalog_text']())
            self.assertIsNone(ns['_pick_sticker']('daily'))
            sent=[]
            async def send(target,chain):sent.append(chain);return DeliveryResult('accepted')
            obj._send=send
            result=await obj._send_sticker_row(obj._scope(eventB).target,dict(pack='collect-001',rel='private.png'))
            self.assertNotEqual(result.status,'accepted');self.assertEqual(sent,[])
            # Explicit content-bound owner sharing remains usable, never inferred from pack/tag.
            approval={'version':1,'files':{'collect-001/private.png':{'sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'basis':'owner-explicit-share','source':'synthetic approval'}}}
            (root/'sticker_packs/shared_gallery_v1.json').write_text(json.dumps(approval),encoding='utf-8')
            self.assertIn('PRIVATE_SENTINEL',await obj.list_stickers(eventB))
            row=ns['_pick_sticker']('daily');self.assertIsNotNone(row)
            self.assertEqual((await obj._send_sticker_row(obj._scope(eventB).target,row)).status,'accepted')
            original.write_bytes(b'replaced private photo')
            self.assertNotEqual((await obj._send_sticker_row(obj._scope(eventB).target,row)).status,'accepted')
            self.assertEqual(len(sent),1)
            self.assertEqual(sent[0].chain[0].data,image.read_bytes(),'send uses the verified bytes even if original changes later')


if __name__=='__main__':unittest.main()
