const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createUserWorkbench}=require('../user-workbench');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
test('apply is whitelist only; observe or missing policy never merges new union proofs',t=>{
const root=fs.mkdtempSync(path.join(__dirname,'gray-data-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
const scopes={},hist={},profiles={version:1,sources:{}};for(const [uid,group] of [['p',''],['a','GA'],['b','GB']]){const s={platform:'qq_official',instance:'I',bot:group?'qq_official':'unknown_selfid',sender:uid,group,private:!group};scopes[uid]=s;hist[uid]=[{id:uid,role:'user',text:'synthetic',ts:100,source:s}];profiles.sources[uid]={source:s,app:'APP',observed_at:100,message_id:uid,identity:{namespace:'qq_union_openid',value:'UNION',basis:'qq_author_union'}};}
for(const[n,v]of Object.entries({'scopes_v2.json':scopes,'history_v2.json':hist,'workbench_profiles_v1.json':profiles}))fs.writeFileSync(path.join(root,n),JSON.stringify(v));
const w=createUserWorkbench(root);assert.equal(w.list().total,3);
const fingerprints=['p','a'].map(uid=>{const s=scopes[uid];return hash([s.platform,s.instance,s.bot,s.private?'private':'group',s.group,s.sender,'APP'])});
const p={version:1,mode:'observe',expires_at:Date.now()/1000+3600,comparison_key:'a'.repeat(64),fingerprints};
const save=()=>fs.writeFileSync(path.join(root,'union_rollout_v1.json'),JSON.stringify(p));save();assert.equal(w.list().total,3);
p.mode='apply';save();assert.equal(w.list().total,2);assert.equal(w.list().people.find(x=>x.sources.some(s=>s.uid==='p')).origin_count,2);
p.mode='observe';save();assert.equal(w.list().total,3);
});
