const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
test('each operation rechecks executable capability; business failure never retries',async()=>{
 const file=path.join(__dirname,'../lifecycle.js'),nativeRequire=require('node:module').createRequire(file),root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-select-'));let probes=0;const actions=[];
 const sandbox={module:{exports:{}},process,require(name){if(name==='node:child_process')return {execFile(exe,args,opts,cb){
  if(args.includes('-SelectOnly')){probes++;return cb(null,JSON.stringify(probes===3?{ok:false}:{ok:true,exe:probes===1?'synthetic-7':'synthetic-51'}));}
  actions.push(exe);cb(Object.assign(Error('business exit'),{code:37}),'\n{"status":"failed","ok":false,"error":"synthetic business 37"}');
 }};return nativeRequire(name)}};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),sandbox);
 try{const manager=sandbox.module.exports.createLifecycle(root,12345);for(let i=0;i<2;i++){const row=await manager.status();assert.equal(row.status,'failed');assert.equal(row.error,'synthetic business 37');}const unavailable=await manager.status();assert.equal(unavailable.stage,'interpreter_preflight');assert.equal(unavailable.action_started,false);assert.deepEqual(actions,['synthetic-7','synthetic-51']);assert.equal(probes,3);}
 finally{fs.rmSync(root,{recursive:true,force:true});}
});
