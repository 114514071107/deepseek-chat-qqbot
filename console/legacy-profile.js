const crypto=require('node:crypto');
const hash=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
function sourceValid(s){return s&&['platform','instance','bot','sender'].every(k=>typeof s[k]==='string'&&s[k].length>0&&s[k].length<=256)&&typeof s.private==='boolean'&&typeof s.group==='string'&&(s.private?s.group==='':s.group.length>0);}
function same(a,b){return sourceValid(a)&&sourceValid(b)&&['platform','instance','bot','sender','group','private'].every(k=>a[k]===b[k]);}
function legacyProfileFor(s,p){
  if(!p||!same(s,p.source)||!Number.isFinite(p.observed_at)||p.observed_at<=0)return {};
  const text=v=>typeof v==='string'&&v.length>0&&v.length<=256;
  const field=(value,kind,source)=>value&&value.kind===kind&&value.source===source&&text(value.value)&&
    Number.isFinite(value.at)&&value.at>0&&value.at<=p.observed_at?value:null;
  const qq=s.platform==='qq_official',onebot=s.platform==='aiocqhttp';
  const nickname=qq?field(p.nickname,'platform_name','qq.author.username'):
    onebot?field(p.nickname,'qq_nickname','onebot.sender.nickname'):null;
  const card=field(p.group_card,'group_card',qq?'qq.member.nick':'onebot.sender.card');
  const i=p.identity,valid=i&&text(p.app)&&text(i.value)&&(
    (qq&&i.namespace==='qq_user_openid'&&i.basis===(s.private?'qq_author_user':'qq_author_pair')&&(!s.private||i.value===s.sender))||
    (onebot&&i.namespace==='onebot_qq'&&i.basis==='onebot_message_sender'&&i.value===s.sender&&p.app===s.bot&&/^\d+$/.test(i.value)));
  return {profile:nickname||null,profile_first_seen:Number.isFinite(p.first_seen_at)&&p.first_seen_at>0?p.first_seen_at:p.observed_at,
    group_card:s.private?null:card,observed_app:text(p.app)?p.app:'',identity_key:valid?hash([s.platform,s.instance,p.app,i.namespace,i.value]):'',
    identity_origin:qq&&text(p.app)?hash([s.platform,s.instance,p.app,s.private?'user_openid':'member_openid',s.group,s.sender]):'',
    identity_domain:valid?hash([s.platform,s.instance,p.app,i.namespace]):'',identity_value:valid?i.value:'',
    identity_basis:valid?(qq?'平台同一 author 的 user_openid 映射（限当前应用/实例）':'OneBot 已核验 QQ 帐号（限当前机器人/实例）'):'',
    identity_at:valid?(p.identity_observed_at||p.observed_at):null,identity_message_id:valid?(p.identity_message_id||p.message_id):'',
    identity_conflict_count:Array.isArray(p.identity_conflicts)?p.identity_conflicts.length:0,
    identity_conflict:p.identity_conflict===true};
}

module.exports={legacyProfileFor};
