// Instance operations use the same PowerShell launcher, never a name/PID kill path.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{execFile}=require('node:child_process');
function createLifecycle(root,consolePort){
 const dir=path.join(root,'.launcher','operations');let dispatching=false;
 function read(p){try{return JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''))}catch{return null}}
 function result(id){
  if(!/^[a-f0-9]{32}$/.test(id||''))return {ok:false,status:'failed',error:'无效操作编号'};
  const row=read(path.join(dir,id+'.json'));
  if(!row)return {ok:false,id,status:'unknown',error:'找不到操作记录，请核查实例日志'};
  if(['pending','running'].includes(row.status)&&Date.now()-Date.parse(row.time)>150000)return {...row,ok:false,status:'unknown',error:'等待已超时；请核查记录，勿重复提交'};
  return row;
 }
 let chosen;
 async function shell(){if(chosen)return chosen;const located=await new Promise(resolve=>execFile('where.exe',['pwsh.exe'],{windowsHide:true,timeout:3000},(e,out)=>resolve(e?'':out.split(/\r?\n/).find(p=>fs.existsSync(p))||'')));
  const preferred=located||path.join(process.env.ProgramFiles||'C:\\Program Files','PowerShell','7','pwsh.exe');chosen=fs.existsSync(preferred)?preferred:path.join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');return chosen;}
 async function run(args){const exe=await shell(),env={...process.env};if(path.basename(exe).toLowerCase()==='powershell.exe')env.PSModulePath=path.join(env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','Modules')+';'+path.join(env.ProgramFiles||'C:\\Program Files','WindowsPowerShell','Modules');
 const state=read(path.join(root,'.launcher/Bot.json'));
 const botPort=state?.root===root&&state?.component==='Bot'&&Number.isInteger(state.port)&&state.port>0&&state.port<=65535?state.port:6185;
 return new Promise(resolve=>execFile(exe,['-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',path.join(root,'start-bot.ps1'),'-RuntimeRoot',root,'-BotPort',String(botPort),'-ConsolePort',String(consolePort),...args],{windowsHide:true,timeout:15000,maxBuffer:32768,env},(err,out)=>{
  let row;try{row=JSON.parse(out.trim().split(/\r?\n/).pop())}catch{}
  resolve(row||{ok:false,status:err&&!err.killed?'failed':'unknown',error:err?'启动器调用失败或超时，请核查实例日志':'启动器未返回有效结果'});
 }))}
 return {result,
  status:()=>run(['-Component','Bot','-Action','Status','-VerifyReady']),
  async request(component,action){
   if(!['start','stop','restart'].includes(action))return {ok:false,status:'failed',error:'action 须为 start/stop/restart'};
   if(dispatching)return {ok:false,status:'pending',error:'管理请求正在受理'};
   const active=read(path.join(dir,'active.json'));if(active){const current=result(active.id);if(['pending','running','unknown'].includes(current.status))return {...current,accepted:false,error:current.error||'实例已有操作，请等待其结果'};}
   dispatching=true;
   try{
    fs.mkdirSync(dir,{recursive:true});const id=crypto.randomBytes(16).toString('hex');
    const row={id,component,action,status:'pending',ok:false,time:new Date().toISOString()};
    fs.writeFileSync(path.join(dir,id+'.json'),JSON.stringify(row),{flag:'wx'});fs.writeFileSync(path.join(dir,'active.json'),JSON.stringify({id}));
    const dispatched=await run(['-Component',component,'-Action',action,'-OperationId',id,'-DetachOperation','-VerifyReady','-TimeoutSeconds','45']);
    if(!dispatched.accepted){
     const observed=result(id);
     if(observed.status!=='pending')return {...observed,accepted:observed.status==='running'};
     const failure={...row,...dispatched,ok:false,id};fs.writeFileSync(path.join(dir,id+'.json'),JSON.stringify(failure));return failure;
    }
    return {...row,accepted:true};
   }finally{dispatching=false;}
  }
 };
}
module.exports={createLifecycle};
