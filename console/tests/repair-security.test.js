const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const vm = require('node:vm');
const crypto = require('node:crypto');

test('launcher-selected runtime root is used without reading another instance', async t => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-root-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  fs.mkdirSync(path.join(root,'dsh_data'));
  fs.writeFileSync(path.join(root,'dsh_data','history_all.json'),JSON.stringify({fixture:[{role:'user',text:'ISOLATED-ROOT'}]}));
  const file=path.join(__dirname,'../server.js'); const nativeRequire=require('node:module').createRequire(file);
  const bridge=nativeRequire('./state-bridge');
  const token=crypto.randomBytes(32).toString('hex');
  const sandbox={module:{exports:{}},__dirname:path.dirname(file),__filename:file,
    process:{argv:[],env:{DSH_RUNTIME_ROOT:root}},URL,console,Buffer,setTimeout,
    require(name){
      if(name==='./state-bridge') return {...bridge,readJson(file,fallback){
        // Fail before disk access if the real handler selects production.
        if(!path.resolve(file).startsWith(path.resolve(root)+path.sep)) throw Error('foreign instance read denied by fixture');
        return bridge.readJson(file,fallback);
      }};
      return nativeRequire(name);
    }};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),sandbox,{filename:file});
  const server=sandbox.module.exports.createConsoleServer({token,port:0});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
  const response=await fetch('http://127.0.0.1:'+server.address().port+'/api/history?uid=fixture',
    {headers:{authorization:'Basic '+Buffer.from('dsh:'+token).toString('base64')}});
  assert.equal(response.status,200); assert.equal((await response.json()).entries[0].text,'ISOLATED-ROOT');
});

async function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-security-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  fs.mkdirSync(path.join(root, 'dsh_data', 'media'), {recursive:true});
  fs.writeFileSync(path.join(root, 'dsh_data', 'history_all.json'), JSON.stringify({owner:[{role:'user',text:'fixture'}]}));
  fs.writeFileSync(path.join(root, 'dsh_data', 'media', 'test.png'), 'fixture-media');
  const token = crypto.randomBytes(32).toString('hex');
  const file = path.join(__dirname, '..', 'server.js');
  let source = fs.readFileSync(file, 'utf8');
  // Legacy baseline is evaluated with an isolated root and its listen removed.
  if (!source.includes('function createConsoleServer')) {
    source = source.replace(/const DSH = .*?;/, 'const DSH = ' + JSON.stringify(root) + ';')
      .replace(/server\.listen\(PORT, HOST,[\s\S]*$/, 'module.exports = server;');
  }
  const sandbox = {require:require("node:module").createRequire(file), module:{exports:{}}, __dirname:path.dirname(file), __filename:file,
    process:{argv:[], env:{}}, URL, console, Buffer, setTimeout};
  vm.runInNewContext(source, sandbox, {filename:file});
  const exp = sandbox.module.exports;
  const server = exp.createConsoleServer ? exp.createConsoleServer({dsh:root, token, master:'owner', port:0}) : exp;
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  t.after(() => new Promise(r => {server.closeAllConnections(); server.close(r);}));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const auth = 'Basic ' + Buffer.from('dsh:' + token).toString('base64');
  const request = (url, options={}) => new Promise((resolve,reject) => {
    const req = http.request(origin + url, options, res => {
      let body=''; res.on('data', c=>body+=c); res.on('end', ()=>resolve({status:res.statusCode,body,headers:res.headers}));
    }); req.on('error',reject); req.end(options.body);
  });
  return {root,origin,auth,request};
}

test('all pages, history, media and management require credentials', async t => {
  const {request} = await fixture(t);
  for (const url of ['/', '/index.html', '/api/history', '/api/media?f=media/test.png'])
    assert.equal((await request(url)).status, 401, url);
  assert.equal((await request('/api/switch', {method:'POST',body:'{"key":"enabled","value":false}'})).status,401);
});

test('accepted snapshots remain authenticated and unknown formats download only inside sent media', async t => {
  const {root,request,auth}=await fixture(t);
  const sent=path.join(root,'dsh_data','media','sent','fixture-scope');fs.mkdirSync(sent,{recursive:true});
  for(const name of ['image.png','attachment.md','audio.silk','unsafe.html'])fs.writeFileSync(path.join(sent,name),'snapshot');
  fs.writeFileSync(path.join(root,'dsh_data','media','private.md'),'not a sent snapshot');
  for(const name of ['image.png','attachment.md','audio.silk','unsafe.html']){
    const url='/api/media?f='+encodeURIComponent('media/sent/fixture-scope/'+name);
    assert.equal((await request(url)).status,401);
    const result=await request(url,{headers:{authorization:auth}});
    assert.equal(result.status,200,name);assert.equal(result.body,'snapshot');
    if(name!=='image.png'){
      assert.match(result.headers['content-disposition'],/^attachment;/);
      assert.equal(result.headers['content-type'],'application/octet-stream');
    }
  }
  assert.equal((await request('/api/media?f=media/private.md',{headers:{authorization:auth}})).status,403);
});

test('history renders accepted image, audio and attachment references as inspectable media',()=>{
  const page=fs.readFileSync(path.join(__dirname,'../public/index.html'),'utf8');
  const renderer=page.slice(page.indexOf('const mediaUrl ='),page.indexOf('// 老记录'));
  const ctx={esc:String,fmtT:()=>''};vm.runInNewContext(renderer+';globalThis.render=histEntryHtml',ctx);
  const html=ctx.render({role:'assistant',text:'caption',images:['media/sent/scope/image.png'],voice:'media/sent/scope/audio.silk',files:['media/sent/scope/file.md']});
  assert.match(html,/src="\/api\/media\?f=media%2Fsent%2Fscope%2Fimage.png"/);
  assert.match(html,/href="\/api\/media\?f=media%2Fsent%2Fscope%2Faudio.silk"[^>]*download/);
  assert.match(html,/href="\/api\/media\?f=media%2Fsent%2Fscope%2Ffile.md"[^>]*download/);
});

test('user-initiated cross-site entry navigation reaches login and the console page', async t => {
  const {request,auth} = await fixture(t);
  const navigation = {'sec-fetch-site':'cross-site','sec-fetch-mode':'navigate',
    'sec-fetch-dest':'document','sec-fetch-user':'?1'};
  for (const url of ['/', '/index.html']) {
    assert.equal((await request(url,{headers:navigation})).status,401,url);
    const response = await request(url,{headers:{...navigation,authorization:auth}});
    assert.equal(response.status,200,url);
    assert.match(response.headers['content-type'],/text\/html/);
  }
});

test('entry navigation exception never exposes APIs, media, frames or cross-site writes', async t => {
  const {request,auth} = await fixture(t);
  const navigation = {authorization:auth,'sec-fetch-site':'cross-site',
    'sec-fetch-mode':'navigate','sec-fetch-dest':'document','sec-fetch-user':'?1'};
  for (const url of ['/api/history','/api/media?f=media/test.png'])
    assert.equal((await request(url,{headers:navigation})).status,403,url);
  for (const bad of [{'sec-fetch-mode':'cors'},{'sec-fetch-dest':'iframe'},
    {'sec-fetch-user':''},{origin:'https://foreign.invalid'},{origin:'null'}])
    assert.equal((await request('/',{headers:{...navigation,...bad}})).status,403,JSON.stringify(bad));
  assert.equal((await request('/api/switch',{method:'POST',headers:{...navigation,
    'content-type':'application/json','x-dsh-request':'1'},
    body:'{"key":"enabled","value":false}'})).status,403);
});

test('authenticated reads work; writes require same origin, JSON and custom header', async t => {
  const {request,auth,origin,root} = await fixture(t);
  assert.equal((await request('/api/history', {headers:{authorization:auth}})).status,200);
  assert.equal((await request('/api/media?f=media/test.png', {headers:{authorization:auth}})).body,'fixture-media');
  const headers = {authorization:auth, origin, 'content-type':'application/json','x-dsh-request':'1'};
  const body = '{"key":"enabled","value":false}';
  for (const bad of [{origin:'https://foreign.invalid'}, {origin:'null'}, {origin:''},
                     {'content-type':'text/plain'}, {'x-dsh-request':''}, {'sec-fetch-site':'cross-site'}]) {
    assert.equal((await request('/api/switch',{method:'POST',headers:{...headers,...bad},body})).status,403);
  }
  assert.equal(fs.existsSync(path.join(root,'dsh_data','dsh_soul_conf.json')),false);
  assert.equal((await request('/api/switch',{method:'POST',headers,body})).status,200);
  assert.equal(JSON.parse((await request('/api/switch',{method:'POST',headers,body})).body).ok,false);
  assert.equal(fs.existsSync(path.join(root,'dsh_data','dsh_soul_conf.json')),false);
  assert.equal((await request('/api/history',{headers:{authorization:auth,host:'rebind.invalid'}})).status,403);
  assert.equal((await request('/',{headers:{authorization:'Basic '+Buffer.from('dsh:wrong').toString('base64')}})).status,401);
  assert.equal((await request('/api/media?f=../outside.png',{headers:{authorization:auth}})).status,404);
});

test('startup fails closed without a strong token or with a public bind address', () => {
  const {createConsoleServer}=require('../server.js');
  assert.throws(()=>createConsoleServer({token:''}),/DSH_CONSOLE_TOKEN/);
  assert.throws(()=>createConsoleServer({token:'short'}),/DSH_CONSOLE_TOKEN/);
  assert.throws(()=>createConsoleServer({token:crypto.randomBytes(32).toString('hex'),host:'0.0.0.0'}),/127\.0\.0\.1/);
});

test('status reads an existing Windows UTF-8 BOM config without rewriting or hiding corrupt JSON', async t => {
  const {root,auth,request} = await fixture(t);
  fs.mkdirSync(path.join(root,'data'));
  const config=path.join(root,'data','cmd_config.json');
  const original='\uFEFF'+JSON.stringify({provider:[],provider_settings:{}});
  fs.writeFileSync(config,original);
  const response=await request('/api/status',{headers:{authorization:auth}});
  assert.equal(response.status,200,response.body);
  assert.equal(typeof JSON.parse(response.body).bot_running,'boolean');
  assert.equal(fs.readFileSync(config,'utf8'),original);
  fs.writeFileSync(config,'\uFEFF{broken');
  assert.equal((await request('/api/status',{headers:{authorization:auth}})).status,500);
});
