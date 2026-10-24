const fs=require('node:fs');
const path=require('node:path');
function seed(root){
  const data=path.join(root,'dsh_data');fs.mkdirSync(data,{recursive:true});
  const source=(sender,group='')=>({platform:'qq_official',instance:'fixture-bot',bot:'self',sender,group,private:!group,message_id:'fixture'});
  const scopes={p1:source('private-A'),g1:source('member-A-1','group-one'),g2:source('member-A-2','group-two'),other:source('private-B')};
  const histories={};
  for(const [uid,s] of Object.entries(scopes)){
    histories[uid]=[{id:uid+'-u',role:'user',text:'SYNTHETIC-'+uid,ts:10,request_id:uid+'-r',source:{...s,message_id:uid+'-m'}},
      {id:uid+'-a',role:'assistant',text:'ANSWER-'+uid,ts:11,request_id:uid+'-r',source:s,delivery:{status:'accepted',message_id:uid+'-receipt'}}];
  }
  histories.g1.push({id:'foreign',role:'user',text:'OTHER-MEMBER-SECRET',ts:12,source:source('someone-else','group-one')},
    {id:'unbound',role:'assistant',text:'UNBOUND-ASSISTANT',ts:13,request_id:'other-request',source:scopes.g1,delivery:{status:'accepted'}});
  histories.legacy=[{role:'user',text:'LEGACY-ONLY',ts:1}];
  const save=(name,value)=>fs.writeFileSync(path.join(data,name),JSON.stringify(value));
  save('scopes_v2.json',scopes);save('history_v2.json',histories);
  save('names_all.json',{p1:'小林',g1:'小林',g2:'换过昵称',other:'小林',legacy:'旧档'});
  save('points_all.json',{});
  fs.mkdirSync(path.join(data,'media'),{recursive:true});
  fs.writeFileSync(path.join(data,'media','fixture.png'),Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64'));
  histories.p1[0].images=['media/fixture.png'];save('history_v2.json',histories);
  return {data,scopes,histories,save};
}
module.exports={seed};
