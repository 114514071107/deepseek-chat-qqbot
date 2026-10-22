// The protected console submits commands; only the live plugin owns data mutations.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function readJson(file,fallback){
  try{return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));}
  catch(error){if(error.code==='ENOENT')return fallback;throw error;}
}
function atomicJson(file,value){
  const tmp=file+'.'+crypto.randomBytes(8).toString('hex')+'.tmp';
  try{fs.writeFileSync(tmp,JSON.stringify(value),{flag:'wx'});fs.renameSync(tmp,file);}
  finally{if(fs.existsSync(tmp))fs.unlinkSync(tmp);}
}

function createStateBridge(data,timeout=5000){
  return async(operation,body)=>{
    const root=path.join(data,'admin_v2');const live=readJson(path.join(root,'live.json'),{});
    if(!live.instance||live.stopped||Date.now()/1000-live.at>2||!Number.isFinite(live.at))
      return {ok:false,applied:false,error:'机器人运行态不可用，未修改数据；请待插件在线后重试'};
    const requests=path.join(root,'requests');const responses=path.join(root,'responses');
    fs.mkdirSync(requests,{recursive:true});fs.mkdirSync(responses,{recursive:true});
    if(fs.readdirSync(requests).filter(f=>f.endsWith('.json')).length>=64)
      return {ok:false,applied:false,error:'管理队列已满，请稍后重试'};
    const id=crypto.randomBytes(16).toString('hex');const file=id+'.json';
    const command={operation,body,instance:live.instance,deadline:(Date.now()+timeout)/1000};
    if(Buffer.byteLength(JSON.stringify(command))>65536)return {ok:false,error:'命令过大'};
    atomicJson(path.join(requests,file),command);
    const until=Date.now()+timeout;
    do{
      const result=readJson(path.join(responses,file),null);
      if(result){
        if(result.instance!==live.instance||result.id!==id)return {ok:false,applied:'unknown',id,error:'运行态确认不匹配'};
        return result;
      }
      await sleep(20);
    }while(Date.now()<until);
    return {ok:false,applied:'unknown',id,error:'运行态未及时确认；不能视为成功，请刷新核对。命令过期后不会开始应用'};
  };
}
module.exports={createStateBridge,readJson,atomicJson};
