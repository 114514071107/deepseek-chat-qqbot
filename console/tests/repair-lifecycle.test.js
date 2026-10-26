const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {createConsoleServer}=require('../server');
test('launcher receives the recorded instance Bot port',async()=>{
 const vm=require('node:vm'),file=path.join(__dirname,'../lifecycle.js'),nativeRequire=require('node:module').createRequire(file),root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-port-contract-'));
 fs.mkdirSync(path.join(root,'.launcher'));fs.writeFileSync(path.join(root,'.launcher/Bot.json'),JSON.stringify({root,component:'Bot',port:12345}));let called;
 const sandbox={module:{exports:{}},process,require(name){if(name==='node:child_process')return {execFile(exe,args,opts,cb){if(args.includes('-SelectOnly'))return cb(null,JSON.stringify({ok:true,exe:process.execPath}));called=args;cb(null,'{"status":"succeeded","running":true}') }};return nativeRequire(name)}};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),sandbox);
 try{await sandbox.module.exports.createLifecycle(root,12346).status();assert.equal(called[called.indexOf('-BotPort')+1],'12345');}
 finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('dispatch timeout cannot overwrite a controller result that already started',async()=>{
 const vm=require('node:vm'),moduleFile=path.join(__dirname,'../lifecycle.js'),nativeRequire=require('node:module').createRequire(moduleFile);
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-dispatch-'));
 const sandbox={module:{exports:{}},process,console,require(name){if(name==='node:child_process')return {execFile(exe,args,options,cb){
  if(args.includes('-SelectOnly'))return cb(null,JSON.stringify({ok:true,exe:process.execPath}));
  const dir=path.join(root,'.launcher/operations'),{id}=JSON.parse(fs.readFileSync(path.join(dir,'active.json')));
  fs.writeFileSync(path.join(dir,id+'.json'),JSON.stringify({id,status:'running',ok:false,time:new Date().toISOString()}));
  cb(Object.assign(Error('synthetic reply timeout'),{killed:true}),'');
 }};return nativeRequire(name)}};
 vm.runInNewContext(fs.readFileSync(moduleFile,'utf8'),sandbox);
 try{const manager=sandbox.module.exports.createLifecycle(root,12345),row=await manager.request('Bot','start');assert.equal(row.status,'running');assert.equal(manager.result(row.id).status,'running');}
 finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('lifecycle API exposes pending and final failures without claiming success',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-life-api-'));fs.mkdirSync(path.join(root,'dsh_data'));
 const calls=[]; const lifecycle={status:async()=>({status:'unknown',running:null,error:'ownership unknown'}),request:async(c,a)=>{calls.push([c,a]);return {ok:false,accepted:true,status:'pending',id:'a'.repeat(32)}},result:()=>({ok:false,status:'failed',error:'AccessDenied'})};
 const server=createConsoleServer({dsh:root,port:0,token:'synthetic-token-'.repeat(4),lifecycle});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try {
  const base='http://127.0.0.1:'+server.address().port,headers={authorization:'Basic '+Buffer.from('dsh:'+'synthetic-token-'.repeat(4)).toString('base64'),origin:base,'content-type':'application/json','x-dsh-request':'1'};
  const op=await (await fetch(base+'/api/bot',{method:'POST',headers,body:JSON.stringify({action:'stop'})})).json();
  assert.equal(op.status,'pending');assert.equal(op.ok,false);assert.deepEqual(calls,[['Bot','stop']]);
  const result=await (await fetch(base+'/api/lifecycle?id='+op.id,{headers})).json();assert.equal(result.status,'failed');assert.equal(result.ok,false);
  const restart=await (await fetch(base+'/api/console',{method:'POST',headers,body:JSON.stringify({action:'restart'})})).json();assert.equal(restart.status,'pending');
 } finally {server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
});
