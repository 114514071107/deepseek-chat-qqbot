// Six synthetic people; identity evidence is intentionally incomplete for C/F.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
const memory=s=>'p2_'+digest([s.platform,s.instance,s.bot,s.sender]);
function seedTriage(root){
  const data=path.join(root,'dsh_data');fs.mkdirSync(data,{recursive:true});
  const scopes={},histories={},profiles={version:1,sources:{}},names={},points={};
  const save=(name,value)=>fs.writeFileSync(path.join(data,name),JSON.stringify(value));
  let stamp=100;
  function source(uid,sender,group='',{onebot=false,app='qq-app',instance='qq-fixture',bot,user=null,name='同名合成'}={}){
    const s=scopes[uid]={platform:onebot?'aiocqhttp':'qq_official',instance:onebot?'onebot-fixture':instance,
      bot:bot||(onebot?'900001':group?'qq_official':'unknown_selfid'),sender,group,private:!group,message_id:uid+'-message'};
    histories[uid]=[{role:'user',text:'SYNTHETIC-'+uid,ts:stamp,request_id:uid+'-request',source:s},
      {role:'assistant',text:'ANSWER-'+uid,ts:stamp+1,request_id:uid+'-request',source:s,delivery:{status:'accepted',message_id:uid+'-reply'}}];
    const at=stamp++;profiles.sources[uid]={source:s,app:onebot?'900001':app,observed_at:at,first_seen_at:at+1000,message_id:uid+'-profile',
      identity:onebot?{namespace:'onebot_qq',value:sender,basis:'onebot_message_sender'}:
        user?{namespace:'qq_user_openid',value:user,basis:group?'qq_author_pair':'qq_author_user'}:null,
      nickname:name?{value:name,kind:onebot?'qq_nickname':'platform_name',source:onebot?'onebot.sender.nickname':'qq.author.username',at,message_id:uid+'-profile'}:null};
  }
  source('pA','user-A','',{user:'user-A',name:'A私聊'});source('gA','member-A','g-one',{user:'user-A',name:'A群名'});
  source('pB','100002','',{onebot:true});source('gB1','100002','g-one',{onebot:true});source('gB2','100002','g-two',{onebot:true});
  source('pC','literal-C','',{user:'literal-C'});source('gC','literal-C','g-one');
  source('gD1','member-D1','g-one',{user:'user-D'});source('gD2','member-D2','g-two');
  source('gE','member-E','g-three',{name:''});source('gEold','member-E','g-three',{bot:'sdk-self-id-alias',name:''});
  source('gF','member-E','g-three',{app:'different-app',instance:'other-instance'});
  histories.oldA=[{role:'user',text:'ARCHIVE-A-SCENE-UNKNOWN',ts:1}];histories.oldF=[{role:'user',text:'ARCHIVE-F-SCENE-UNKNOWN',ts:2}];
  names.oldA='同名合成';names.oldF='同名合成';
  for(const uid of ['gA','pB','gE']){const key=memory(scopes[uid]);names[key]='历史称呼-'+uid;points[key]={balance:32100};}
  names.noChat='只有设置';points.noChat={balance:32100};
  function flush(){save('scopes_v2.json',scopes);save('history_v2.json',histories);save('workbench_profiles_v1.json',profiles);save('names_all.json',names);save('points_all.json',points);}
  flush();save('console_people_v1.json',{version:1,groups:[['gD1','gD2']]});
  return {data,scopes,histories,profiles,names,points,source,flush,save,
    evidence:{A:'platform author pair',B:'OneBot QQ account',C:'no cross-domain mapping',D:'manual group plus one witnessed global alias',E:'same verified app/group-member with SDK placeholder change',F:'different app/instance; old archive not attributed'}};
}
module.exports={seedTriage};
