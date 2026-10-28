const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {createConsoleServer}=require('D:/DSH Workspace/deepseek-chat-qqbot/console/server.js');
(async()=>{const tempRoot=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-switch-review-'));let server;
try{
 const data=path.join(tempRoot,'dsh_data');fs.mkdirSync(data);
 for(const [name,value] of Object.entries({'dsh_soul_conf.json':{points_enabled:false,points_daily:0},'blocked_all.json':['SYNTHETIC-A'],'silence_v2.json':{'SYNTHETIC-A':1999999999}}))fs.writeFileSync(path.join(data,name),JSON.stringify(value));
 const token='synthetic-switch-review-token-1234567890';server=createConsoleServer({dsh:tempRoot,port:0,token});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const response=await fetch('http://127.0.0.1:'+server.address().port+'/api/switches',{headers:{authorization:'Basic '+Buffer.from('dsh:'+token).toString('base64')}});assert.equal(response.status,200);const actual=await response.json();
 const result={synthetic_only:true,configured:{points_enabled:false,points_daily:0,blocked_count:1,silenced_count:1},reported:{points_enabled:actual.points_enabled,points_daily:actual.points_daily,blocked_count:actual.blocked.length,silenced_count:Object.keys(actual.silence).length}};
 assert.equal(actual.points_enabled,true);assert.equal(actual.points_daily,30);assert.equal(actual.blocked.length,0);
 fs.writeFileSync(path.join(__dirname,'reproduced-switches.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{
 if(server){server.closeAllConnections();await new Promise(r=>server.close(r));}
 const target=path.resolve(tempRoot),parent=path.resolve(os.tmpdir())+path.sep;assert.ok(target.startsWith(parent));fs.rmSync(target,{recursive:true,force:true});
}})().catch(e=>{console.error(e);process.exitCode=1;});
