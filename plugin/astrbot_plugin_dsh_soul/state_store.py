"""One process owns live mutations. Disk readers never substitute emptiness for an error."""
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import time
from session_scope import Scope
from task_runtime import check_current

LAYERS=('rolling','archive','summary','memory','media','backups')


def person_ledger_key(scope,ledger):
    """Keep an existing raw-ID quota as a restriction; never infer history ownership."""
    return scope.memory_key if scope.memory_key in ledger or scope.sender not in ledger else scope.sender


class StateError(RuntimeError): pass


def read_text(path,default=''):
    try: return Path(path).read_text(encoding='utf-8')
    except FileNotFoundError: return default
    except (OSError,UnicodeError) as error: raise StateError(f'read {Path(path).name}: {type(error).__name__}') from error


def read_json(path,default):
    text=read_text(path,None)
    if text is None: return copy.deepcopy(default)
    try:
        value=json.loads(text)
        if not isinstance(value,type(default)): raise ValueError('unexpected data shape')
        return value
    except (ValueError,TypeError) as error: raise StateError(f'invalid JSON: {Path(path).name}') from error


def write_text(path,text):
    check_current()
    path=Path(path); tmp=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        check_current()
        os.replace(tmp,path)
    except OSError as error: raise StateError(f'write {path.name}: {type(error).__name__}') from error
    finally:
        if tmp and os.path.exists(tmp): os.unlink(tmp)


def write_json(path,value): write_text(path,json.dumps(value,ensure_ascii=False))


class StateController:
    def __init__(self,plugin,root,clear_framework):
        self.plugin=plugin; self.root=Path(root); self.clear_framework=clear_framework
        self.lock=asyncio.Lock()

    def path(self,name): return self.root/name
    def load(self,name,default): return read_json(self.path(name),default)
    def save(self,name,value): write_json(self.path(name),value)

    def backups(self):
        files=list(self.root.glob('*.bak*'))
        backup_root=self.root/'backups'
        if backup_root.exists(): files += [p for p in backup_root.rglob('*') if p.is_file()]
        return sorted(str(p.relative_to(self.root)).replace('\\','/') for p in files
                      if not p.is_symlink() and p.resolve().is_relative_to(self.root.resolve()))

    def preview(self,key):
        return {'uid':key,'layers':list(LAYERS),'backups':self.backups(),
                'backup_impact':'所列备份可能包含所有用户；删除所选整份文件，不是按用户擦除。外部/系统备份不在本入口范围',
                'mapping':{'rolling':'插件滚动历史及可准确定位的新框架会话历史',
                           'archive':'插件归档、脱敏投递结果账本及该来源在当前群的共享历史',
                           'summary':'会话摘要及临时念头','memory':'长期笔记、学习资料及私有 Markdown 画像',
                           'media':'本会话留存的收件和语音文件；共享表情图库不在此项',
                           'backups':'明确选中的整份备份文件'},
                'legacy':key not in self.plugin.scopes}

    async def delete(self,key,layers,*,backup_files=None,confirm_shared_backups=False):
        if not isinstance(key,str) or not key or not isinstance(layers,list) or not layers or set(layers)-set(LAYERS):
            raise ValueError('explicit valid layers and record key are required')
        async with self.lock:
            self.plugin.runtime.pause(key)
            try:
                return await self._delete(key,layers,backup_files=backup_files,confirm_shared_backups=confirm_shared_backups)
            finally:
                self.plugin.runtime.resume(key)

    async def _delete(self,key,layers,*,backup_files,confirm_shared_backups):
            obj=self.plugin; obj.runtime.invalidate(key)
            if hasattr(obj,'_reset_request'): obj._reset_request(key)
            tasks=[t for t,token in list(obj.runtime.borrowed.items()) if token.key==key and t is not asyncio.current_task()]
            tasks += [t for (scope,_),t in list(obj.runtime.jobs.items()) if scope==key and t is not asyncio.current_task()]
            if tasks: await asyncio.gather(*tasks,return_exceptions=True)
            if hasattr(obj,'_reset_request'): obj._reset_request(key,layers)
            results={}; known=key in obj.scopes
            # Collect references before deleting either history layer.
            media_error=None
            try: media=self._media_references(key,known) if 'media' in layers else []
            except Exception as error: media=[]; media_error=error
            for layer in LAYERS:
                if layer not in layers: continue
                try:
                    if layer=='media' and media_error: raise media_error
                    result=await self._delete_layer(key,layer,known,media,backup_files,confirm_shared_backups)
                    results[layer]=result or {'status':'done'}
                except Exception as error:
                    results[layer]={'status':'failed','error':type(error).__name__+': '+str(error)[:180]}
            return {'ok':all(r['status']=='done' for r in results.values()),'uid':key,'layers':results,
                    'retained':[layer for layer in LAYERS if layer not in layers],
                    'scope':'所选记录来源；未迁移来源不明旧档、共享图库和外部备份分别保留'}

    def _table_remove(self,path,key,cache=None):
        table=read_json(path,{})
        count=len(table.get(key,[])) if isinstance(table.get(key,[]),list) else int(key in table)
        table[key]=[]
        write_json(path,table)
        if cache is not None:
            cache.clear(); cache.update(table)
        return count

    def _unlink(self,path):
        check_current()
        try: Path(path).unlink()
        except FileNotFoundError: pass

    def _media_references(self,key,known):
        refs=set(self.load('media_v2.json',{}).get(key,[]))
        rows=(self.plugin.h.get(key,[]) if known else self.load('history_all.json',{}).get(key,[]))
        archive=self.path('history_archive_v2.jsonl' if known else 'history_archive.jsonl')
        for line in read_text(archive,'').splitlines():
            record=json.loads(line)
            if record.get('uid')==key: rows=rows+[record]
        for entry in rows:
            for name in ('voice','images','files'):
                value=entry.get(name,[])
                refs.update([value] if isinstance(value,str) else value)
        return sorted(refs)

    async def _delete_layer(self,key,layer,known,media,backup_files,confirm):
        obj=self.plugin; safe=re.sub(r'[^A-Za-z0-9_-]','_',key)
        if layer=='rolling':
            count=self._table_remove(obj.h_path if known else self.path('history_all.json'),key,obj.h if known else None)
            if not known:
                return {'status':'partial','plugin_cleared':count,'retained':'旧框架历史没有可信平台/场景映射，未猜测删除'}
            try: await asyncio.wait_for(self.clear_framework(key),timeout=10)
            except Exception as error:
                return {'status':'partial','plugin_cleared':count,'framework_error':type(error).__name__}
            return {'status':'done','plugin_cleared':count,'framework':'scoped conversations cleared'}
        if layer=='archive':
            path=self.path('history_archive_v2.jsonl' if known else 'history_archive.jsonl')
            rows=[json.loads(line) for line in read_text(path,'').splitlines() if line.strip()]
            kept=[row for row in rows if row.get('uid')!=key]
            write_text(path,''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in kept))
            if known:
                self._table_remove(self.path('delivery_receipts_v2.json'),key)
                groups=copy.deepcopy(obj.groups)
                for group,entries in groups.items():
                    groups[group]=[row for row in entries if not self._same_source(row.get('source'),obj.scopes[key])]
                try: write_json(obj.group_path,groups); obj.groups=groups
                except StateError as error:
                    return {'status':'partial','archive_cleared':len(rows)-len(kept),'retained':'current group history','error':str(error)}
            return {'status':'done','archive_cleared':len(rows)-len(kept)}
        if layer=='summary':
            self._unlink(self.path('session_'+safe+'.json'))
            try: self._table_remove(obj.t_path if known else self.path('thoughts_all.json'),key,obj.th if known else None)
            except StateError as error:
                return {'status':'partial','session':'removed','thoughts':'retained','error':str(error)}
        elif layer=='memory':
            removed=[]; failed=[]
            for folder in ('memories','profiles','memes'):
                try: self._unlink(self.path(folder)/(safe+'.md')); removed.append(folder)
                except OSError: failed.append(folder)
            retained_shared=not known and self.path('memes.md').exists()
            return {'status':'partial' if failed or retained_shared else 'done','removed':removed,'failed':failed,
                    'legacy_shared_memes':'retained; unattributed shared data' if retained_shared else 'not applicable'}
        elif layer=='media':
            failed=[]; removed=[]
            shared=set()
            for owner,refs in self.load('media_v2.json',{}).items():
                if owner!=key: shared.update(refs)
            for name in ('history_all.json','history_v2.json'):
                for owner,rows in self.load(name,{}).items():
                    if owner==key: continue
                    for row in rows: shared.update(self._entry_media(row))
            for name in ('history_archive.jsonl','history_archive_v2.jsonl'):
                for line in read_text(self.path(name),'').splitlines():
                    row=json.loads(line)
                    if row.get('uid')!=key: shared.update(self._entry_media(row))
            for rel in media:
                if rel in shared: failed.append(rel); continue
                file=self.path(rel).resolve()
                allowed=any(file.is_relative_to(self.path(root).resolve()) for root in ('media/inbox','media/voice','media/sent','files/inbox'))
                if not allowed: failed.append(rel); continue
                try: self._unlink(file); removed.append(rel)
                except OSError: failed.append(rel)
            index=self.load('media_v2.json',{}); index[key]=[r for r in index.get(key,[]) if r not in removed]
            self.save('media_v2.json',index)
            return {'status':'partial' if failed else 'done','removed':len(removed),'retained_files':failed,'shared_gallery':'retained'}
        elif layer=='backups':
            if not confirm or not isinstance(backup_files,list):
                raise ValueError('必须明确确认整份备份影响并选择文件；未删除任何备份')
            available=set(self.backups())
            if available and not backup_files: raise ValueError('未选择任何整份备份文件')
            if set(backup_files)-available: raise ValueError('备份清单已变化，请重新查看')
            removed=[]; failed=[]
            for rel in backup_files:
                try: self._unlink(self.path(rel)); removed.append(rel)
                except OSError: failed.append(rel)
            return {'status':'partial' if failed else 'done','whole_files_removed':removed,'failed':failed,'remaining_backups':self.backups(),'affects':'all users in selected whole files'}

    @staticmethod
    def _same_source(a,b):
        return isinstance(a,dict) and all(a.get(k)==b.get(k) for k in ('platform','instance','bot','sender','group','private'))

    @staticmethod
    def _entry_media(row):
        refs=[]
        for key in ('voice','images','files'):
            value=row.get(key,[])
            refs.extend([value] if isinstance(value,str) else value)
        return refs

    async def apply(self,operation,body):
        if operation=='delete':
            return await self.delete(body.get('uid'),body.get('layers'),backup_files=body.get('backup_files'),confirm_shared_backups=body.get('confirm_shared_backups') is True)
        if operation=='preview': return {'ok':True,**self.preview(body.get('uid',''))}
        if operation=='send':
            key=body.get('target_key'); data=self.plugin.scopes.get(key)
            if not data: raise ValueError('请选择已接收事件确认的目标，旧 uid 不能猜测为私聊目标')
            scope=Scope(**data)
            if body.get('kind')!=scope.target.kind or body.get('instance')!=scope.instance:
                raise ValueError('目标类型或平台实例不一致')
            task=self.plugin.runtime.spawn(self.plugin._admin_send(scope,body.get('text','')),key=scope.key,feature='reply')
            if task is None: raise ValueError('instance unavailable')
            result=await task
            from qq_delivery import DeliveryResult, failure
            if not isinstance(result,DeliveryResult): result=failure('unknown','message','missing_receipt')
            return {'ok':result.status=='accepted','target':scope.target.kind,'instance':scope.instance,
                    'delivery':result.public(),'note':'QQ 接口接受' if result.status=='accepted' else '发送'+result.status,
                    'error':None if result.status=='accepted' else result.error or result.status}
        async with self.lock:
            return self._modify(operation,body)

    def _modify(self,operation,body):
        obj=self.plugin; key=body.get('uid'); result={}
        if operation in ('switch','points/conf'):
            name='dsh_soul_conf.json'; table=self.load(name,{})
            if operation=='switch':
                if body.get('key') in ('harvest','kimi'):
                    raise ValueError('当前不可用：harvest 缺可靠平台表情标识；kimi 被执行权限禁止，开关不能恢复')
                if body.get('key') not in ('enabled','desire','proactive','sprinkle','revive','harvest','safety','reminders','kimi'): raise ValueError('unknown switch')
                if type(body.get('value')) is not bool: raise ValueError('boolean required')
                table[body['key']]=body['value']
            else:
                if 'daily' in body:
                    if type(body['daily']) is not int or body['daily']<0: raise ValueError('invalid daily grant')
                    table['points_daily']=body['daily']
                if 'enabled' in body:
                    if type(body['enabled']) is not bool: raise ValueError('boolean required')
                    table['points_enabled']=body['enabled']
            result={'conf':table,**table}
        else:
            if not isinstance(key,str) or not key: raise ValueError('missing record key')
            if operation=='user':
                if body.get('key') in ('harvest','alarm'):
                    raise ValueError('当前不可用：自动收图缺平台标识；闹钟政策暂缓，旧数据保留')
                if body.get('key') not in ('reply','voice','proactive','desire','sprinkle','revive','harvest','reminders','alarm','files') or type(body.get('value')) is not bool: raise ValueError('invalid user switch')
                name='friends_all.json'; table=self.load(name,{})
                table.setdefault(key,{})[body['key']]=body['value']; result={'friends':table}
            elif operation=='name':
                name='names_all.json'; table=self.load(name,{}); table[key]=str(body.get('name',''))[:30]; result={'names':table}
            elif operation in ('points','points/grant'):
                scope=obj.scopes.get(key)
                name='points_all.json'; table=self.load(name,{})
                key=person_ledger_key(Scope(**scope),table) if scope else key
                entry=table.setdefault(key,{'balance':0,'grant':None,'last':'','spent':0,'notified':''})
                value=body.get('value')
                if operation=='points/grant':
                    if value is not None and (type(value) is not int or value<0): raise ValueError('invalid grant')
                    entry['grant']=value
                else:
                    if type(value) is not int or body.get('mode') not in ('add','set'): raise ValueError('invalid points operation')
                    entry['balance']=max(0,entry.get('balance',0)+value if body['mode']=='add' else value)
                result={'entry':entry}
            elif operation=='unblock':
                name='blocked_all.json'; table=[k for k in self.load(name,[]) if k!=key]; result={'blocked':table}
            elif operation=='unsilence':
                name='silence_v2.json' if key in obj.scopes else 'silence_all.json'; table=self.load(name,{}); table.pop(key,None); result={'silence':table}
            elif operation=='thought/del':
                name='thoughts_v2.json' if key in obj.scopes else 'thoughts_all.json'; table=self.load(name,{})
                index=body.get('index'); rows=table.get(key,[])
                if type(index) is not int or index<0 or index>=len(rows): raise ValueError('invalid thought index')
                rows.pop(index); result={'thoughts':rows}
                obj.runtime.invalidate(key)
            else: raise ValueError('unknown operation')
        self.save(name,table)
        # Publish cache changes only after successful persistence.
        if name=='names_all.json': obj.names=table
        if name=='blocked_all.json': obj.blocked=set(table)
        if name=='silence_v2.json': obj.sil=table
        if name=='thoughts_v2.json': obj.th=table
        if operation=='switch' and body.get('value') is False:
            if body['key']=='enabled':
                for scope in list(obj.scopes):
                    if hasattr(obj, '_reset_request'): obj._reset_request(scope)
                for scope in list(obj.scopes): obj.runtime.invalidate(scope)
            else: obj.runtime.revoke_feature(body['key'])
        if operation=='user' and body.get('value') is False:
            affected=[body['uid']] if body['uid'] in obj.scopes else [
                scope for scope,source in obj.scopes.items() if source['sender']==body['uid']
                and body['key'] not in table.get(scope,{})]
            if body['key']=='reply':
                for scope in affected:
                    if hasattr(obj, '_reset_request'): obj._reset_request(scope)
                for scope in affected: obj.runtime.invalidate(scope)
            else:
                for scope in affected: obj.runtime.revoke_feature(body['key'],scope)
        return {'ok':True,'applied_instance':obj.runtime.id,**result}
