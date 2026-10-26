"""Original per-person resource bounds survive conversation key splitting."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from repair_pipeline_support import load_pipeline
from state_store import read_json,write_json
from task_runtime import Runtime
from test_repair_session_scope import ScopeEvent


class ResourceRegression(unittest.IsolatedAsyncioTestCase):
    def fixture(self,root):
        obj,ns=load_pipeline(root,names=('harvest_images','_harvest_one','_harvest_path','_spawn'),guarded=True)
        ns.update(_load=read_json,_save=write_json,_jf=lambda key,name:str(root/(name+'_'+key+'.json')),
                  sqlite3=sqlite3,_conf=lambda key:True,fetch_public_bytes=lambda *a,**k:None)
        class Image:
            def __init__(self,url):self.url=url
        ns['Image']=Image
        def error(tag,value):
            if isinstance(value,BaseException):raise value
        obj._err=error;obj.runtime=Runtime(lambda *a:True)
        pack=root/'pack';pack.mkdir()
        with closing(sqlite3.connect(pack/'index.db')) as db:
            db.execute('CREATE TABLE memes(path TEXT,tag TEXT,file_name TEXT,file_hash TEXT,caption TEXT,keywords TEXT,mtime REAL,captioned_at REAL)')
            db.commit()
        ns['_ensure_collect_pack']=lambda:str(pack)
        def event(group):
            e=ScopeEvent('a',group);e.message_obj.message=[Image('https://fixture.invalid/'+group+'.png')];return e
        return obj,ns,pack,event

    @unittest.skip('R01 新规则停止未知图片自动采集；保留旧额度断言，待有可靠平台类型协议后再恢复该路径')
    async def test_two_groups_share_one_harvest_job_and_one_person_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj,ns,pack,event=self.fixture(root)
            a=event('g1');b=event('g2');scope=obj._scope(a)
            ledger=Path(obj._harvest_path(scope.key));write_json(ledger,{'day':time.strftime('%Y-%m-%d'),'count':29})
            entered=asyncio.Event();release=asyncio.Event();downloads=[];tagged=[]
            async def download(fn,url,**kw):downloads.append(url);return (b'a' if 'g1' in url else b'b')*2048
            async def tag(path):tagged.append(path);entered.set();await release.wait();return 'happy',['fixture']
            obj._thread=download;obj._auto_tag_sticker=tag
            await obj.harvest_images(a);await obj.harvest_images(b)
            await asyncio.wait_for(entered.wait(),1)
            self.assertEqual(len(tagged),1);release.set()
            await asyncio.gather(*list(obj.runtime.tasks))
            await obj.harvest_images(event('g2'));await asyncio.gather(*list(obj.runtime.tasks))
            self.assertEqual(read_json(ledger,{})['count'],30);self.assertEqual(len(downloads),1)
            with closing(sqlite3.connect(pack/'index.db')) as db:self.assertEqual(db.execute('SELECT COUNT(DISTINCT path) FROM memes').fetchone()[0],1)
            self.assertEqual(obj.runtime.errors,[]);await obj.runtime.stop()

    async def test_existing_raw_harvest_cap_is_not_reset_to_a_new_person_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj,ns,pack,event=self.fixture(root)
            write_json(root/'harvest_a.json',{'day':time.strftime('%Y-%m-%d'),'count':30})
            async def forbidden(*a,**kw):raise AssertionError('over-cap work must not download or call model')
            obj._thread=obj._auto_tag_sticker=forbidden
            e=event('g1');scope=obj._scope(e)
            await obj.harvest_images(e);await asyncio.gather(*list(obj.runtime.tasks))
            self.assertFalse((root/('harvest_'+scope.memory_key+'.json')).exists())
            self.assertEqual(obj.runtime.errors,[]);await obj.runtime.stop()


if __name__=='__main__':unittest.main()
