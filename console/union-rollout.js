const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
function readPolicy(root){try{const p=path.join(root,'union_rollout_v1.json');if(fs.statSync(p).size>16384)return null;
const v=JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'')),now=Date.now()/1000;
return v?.version===1&&['observe','apply'].includes(v.mode)&&Number.isFinite(v.expires_at)&&v.expires_at>now&&v.expires_at<=now+86400&&
Array.isArray(v.fingerprints)&&v.fingerprints.length>0&&v.fingerprints.length<=32&&v.fingerprints.every(x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x))&&typeof v.comparison_key==='string'&&/^[a-f0-9]{64}$/.test(v.comparison_key)?v:null;
}catch{return null;}}
function enabled(v,s,app){return v?.mode==='apply'&&s.platform==='qq_official'&&typeof app==='string'&&!!app&&v.fingerprints.includes(hash([s.platform,s.instance,s.bot,s.private?'private':'group',s.group,s.sender,app]));}
module.exports={readPolicy,enabled};
