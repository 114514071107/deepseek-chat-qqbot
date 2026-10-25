// ds娘 AstrBot 控制台（零依赖 node:http）
// 只监听 127.0.0.1；直接读写 D:\dsbot\dsh_data 下的运行时文件（与插件同一份数据，热生效）
const http = require("http");
const fs = require("fs");
const path = require("path");
const { execFile, spawn } = require("child_process");
const crypto = require("crypto");
const {createStateBridge,readJson: readStateJson} = require("./state-bridge");
const {createUserWorkbench} = require("./user-workbench");

function createConsoleServer(options = {}) {

// ==================== 部署配置（使用前必改，共 2 处） ====================
// ① AstrBot 安装根目录
const DSH = options.dsh || process.env.DSH_RUNTIME_ROOT || "D:\\dsbot";
// ② 主人的 QQ openid（须与插件 main.py 里的 MASTER_OPENID 一致）
const MASTER = options.master || "YOUR_MASTER_OPENID";
// ============================================================
const DATA = path.join(DSH, "dsh_data");
const workbench = createUserWorkbench(DATA);
const applyState = createStateBridge(DATA, options.bridgeTimeout ?? 5000);
const RUN_LOG = path.join(DSH, "astrbot-run.log");
const ERR_LOG = path.join(DATA, "dsh_err.log");
const CMD_CONFIG = path.join(DSH, "data", "cmd_config.json");
const VENV_PY = path.join(DSH, "venv", "Scripts", "python.exe");
// 后端代码版本指纹：每次改 server.js 递增；前端带同名常量，不一致时提示用户重开控制台（防"新页面+旧进程"错位）
const API_VER = "20261026-lifecycle-1";
// 全局开关键（dsh_soul_conf.json）：enabled 为总开关，其余为各功能全局开关
// 20260902-3 新增 kimi（Kimi Code 外包总闸，缺省开）
const SWITCH_KEYS = ["enabled", "desire", "proactive", "sprinkle", "revive", "harvest", "safety", "reminders", "kimi"];
// 按用户开关键（friends_all.json，全用户含主人通用，缺省全开）
// 20260902-2 新增 alarm（闹钟）/ files（沙盒文件助理）：好友侧 skill 开放闸门
const USER_KEYS = ["reply", "voice", "proactive", "desire", "sprinkle", "revive", "harvest", "reminders", "alarm", "files"];
// 媒体接口白名单：resolve 后必须落在这两个根目录之内（防 ../ 穿越），扩展名限音频/图片
const MEDIA_ROOTS = [path.join(DATA, "media"), path.join(DATA, "sticker_packs")];
const MEDIA_TYPES = {
  ".wav": "audio/wav", ".mp3": "audio/mpeg", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".ogg": "audio/ogg",
};

function argVal(name, dflt) {
  const i = process.argv.indexOf("--" + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}
const HOST = options.host || argVal("host", process.env.HOST || "127.0.0.1");
const PORT = options.port ?? parseInt(argVal("port", process.env.PORT || "7850"), 10);
if (HOST !== "127.0.0.1") throw new Error("控制台只允许监听 127.0.0.1");
const TOKEN = options.token ?? process.env.DSH_CONSOLE_TOKEN;
if (typeof TOKEN !== "string" || TOKEN.length < 32 || /[\s:]/.test(TOKEN)) {
  throw new Error("请通过 DSH_CONSOLE_TOKEN 配置至少 32 字符的随机访问令牌（不得含空白或冒号）");
}
const expectedAuth = crypto.createHash("sha256").update("dsh:" + TOKEN).digest();

function protect(req, res) {
  res.setHeader("cache-control", "no-store");
  res.setHeader("referrer-policy", "no-referrer");
  res.setHeader("x-content-type-options", "nosniff");
  res.setHeader("x-frame-options", "DENY");
  const port = server.address().port;
  const hosts = ["127.0.0.1:" + port, "localhost:" + port];
  if (!hosts.includes(req.headers.host)) { send(res, 403, {error:"Host 被拒绝"}); return false; }
  const origin = "http://" + req.headers.host;
  // Opening the login page from a link is a navigation, not cross-site API access.
  // Keep this exception limited to user-initiated top-level entry pages and retain authentication.
  const entryNavigation = req.method === "GET" && ["/", "/index.html"].includes(req.url) &&
    req.headers.origin === undefined &&
    req.headers["sec-fetch-mode"] === "navigate" && req.headers["sec-fetch-dest"] === "document" &&
    req.headers["sec-fetch-user"] === "?1" &&
    ["cross-site", "same-site"].includes(req.headers["sec-fetch-site"]);
  if ((req.headers.origin !== undefined && req.headers.origin !== origin) ||
      (req.headers["sec-fetch-site"] && !["none", "same-origin"].includes(req.headers["sec-fetch-site"]) && !entryNavigation)) {
    send(res, 403, {error:"跨来源访问被拒绝"}); return false;
  }
  const match = /^Basic ([A-Za-z0-9+/]+={0,2})$/.exec(req.headers.authorization || "");
  const supplied = crypto.createHash("sha256").update(match ? Buffer.from(match[1], "base64") : Buffer.alloc(0)).digest();
  if (!crypto.timingSafeEqual(expectedAuth, supplied)) {
    res.setHeader("www-authenticate", 'Basic realm="DSH local console", charset="UTF-8"');
    send(res, 401, {error:"需要控制台认证"}); return false;
  }
  if (!["GET", "HEAD"].includes(req.method) &&
      (req.headers.origin !== origin || req.headers["x-dsh-request"] !== "1" ||
       !/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(req.headers["content-type"] || ""))) {
    send(res, 403, {error:"写请求需要同源、JSON 和 X-DSH-Request: 1"}); return false;
  }
  return true;
}

function readJson(file, dflt) { return readStateJson(file, dflt); }
function histories() { return {...readJson(path.join(DATA,"history_all.json"),{}),...readJson(path.join(DATA,"history_v2.json"),{})}; }
function thoughts() { return {...readJson(path.join(DATA,"thoughts_all.json"),{}),...readJson(path.join(DATA,"thoughts_v2.json"),{})}; }
function scopes() { return readJson(path.join(DATA,"scopes_v2.json"),{}); }
function pointsView() {
  const ledger=readJson(path.join(DATA,"points_all.json"),{}), view={...ledger};
  for(const [key,source] of Object.entries(scopes())) {
    const person="p2_"+crypto.createHash("sha256").update(JSON.stringify([source.platform,source.instance,source.bot,source.sender])).digest("hex");
    if(ledger[person] || ledger[source.sender])view[key]=ledger[person] || ledger[source.sender];
  }
  return view;
}
function knownTargets() {
  const targets=new Map();
  for(const [key,s] of Object.entries(scopes())) {
    const target={target_key:key,kind:s.private?"private":"group",instance:s.instance,platform:s.platform,address:s.private?s.sender:s.group};
    const id=JSON.stringify([s.platform,s.instance,s.bot,target.kind,target.address]);
    if(!targets.has(id))targets.set(id,target);
  }
  return [...targets.values()];
}
function jf(uid, name) {
  const safe = String(uid).replace(/[^A-Za-z0-9_-]/g, "_");
  return path.join(DATA, name + "_" + safe + ".json");
}
function tail(file, lines, stripAnsi) {
  try {
    let txt = fs.readFileSync(file, "utf-8").replace(/\0/g, "");
    if (stripAnsi) txt = txt.replace(/\x1b\[[0-9;]*m/g, "");
    const arr = txt.split(/\r?\n/);
    return arr.slice(-(lines || 200));
  } catch (e) { return ["（读取失败：" + e.message + "）"]; }
}
function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(body);
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    let b = "";
    let size = 0;
    req.on("data", (c) => { size += c.length; if (size > 65536) { reject(new Error("请求体超过上限")); req.destroy(); } else b += c; });
    req.on("error", reject);
    req.on("aborted", () => reject(new Error("请求中断")));
    req.on("end", () => { try {
      const body = JSON.parse(b);
      if (!body || Array.isArray(body) || typeof body !== "object") throw new Error("JSON 须为对象");
      resolve(body);
    } catch (e) { reject(new Error("JSON 请求体无效")); } });
  });
}
function execFileP(cmd, args, timeout) {
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout: timeout || 15000, windowsHide: true }, (err, stdout) => {
      resolve({ ok: !err, out: (stdout || "").toString() });
    });
  });
}

const api = {
  "GET /api/people": async q => workbench.list(q),
  "GET /api/people/history": async q => workbench.history(q),
  "GET /api/people/outbound": async q => workbench.outbound(q),
  "GET /api/admin/result": async q => {
    const id=q.get("id") || "";
    if (!/^[a-f0-9]{32}$/.test(id)) return {ok:false,error:"无效命令编号"};
    return readJson(path.join(DATA,"admin_v2","responses",id+".json"),{ok:false,pending:true,id});
  },
  "GET /api/targets": async () => ({targets:knownTargets()}),
  // 状态总览：进程、文件新鲜度、各 uid 数据量、模型与开关摘要
  "GET /api/status": async () => {
    const proc = await execFileP("tasklist", ["/FI", "IMAGENAME eq astrbot.exe", "/FO", "CSV", "/NH"]);
    const running = proc.ok && proc.out.includes("astrbot.exe");
    const hist = histories();
    const th = thoughts();
    const users = Object.keys(hist).map((uid) => ({
      uid, master: uid === MASTER,
      history: (hist[uid] || []).length,
      thoughts: (th[uid] || []).length,
    }));
    const cfg = readJson(CMD_CONFIG, {});
    const prov = (cfg.provider || []).find((p) => p.id === "deepseek") || {};
    const ps = cfg.provider_settings || {};
    const stat = (f) => { try { return fs.statSync(f).mtimeMs; } catch (e) { return 0; } };
    return {
      bot_running: running, now: Date.now(),
      model: prov.model, modalities: prov.modalities, extra_body: prov.custom_extra_body,
      caption_provider: ps.default_image_caption_provider_id,
      err_log_mtime: stat(ERR_LOG), run_log_mtime: stat(RUN_LOG),
      users,
      api_ver: API_VER,
      conf: readJson(path.join(DATA, "dsh_soul_conf.json"), {}),
      blocked: readJson(path.join(DATA, "blocked_all.json"), []),
      usage: (() => {  // 今日模型调用（插件侧计量 usage_all.json；主对话调用在框架内不在此列）
        const all = readJson(path.join(DATA, "usage_all.json"), {});
        const day = new Date();
        const key = day.getFullYear() + "-" + String(day.getMonth() + 1).padStart(2, "0") + "-" + String(day.getDate()).padStart(2, "0");
        const d = all[key] || { calls: 0, in: 0, out: 0, by: {} };
        const by = Object.entries(d.by || {}).map(([tag, v]) => ({ tag, ...v }))
          .sort((a, b) => (b.in + b.out) - (a.in + a.out));
        return { day: key, calls: d.calls || 0, in: d.in || 0, out: d.out || 0, by };
      })(),
    };
  },
  // 日志（dsh=插件日志 / run=框架日志），支持行数与关键字过滤
  "GET /api/logs": async (q) => {
    const file = q.get("file") === "run" ? RUN_LOG : ERR_LOG;
    const lines = Math.min(parseInt(q.get("lines") || "300", 10) || 300, 2000);
    const kw = (q.get("q") || "").toLowerCase();
    let arr = tail(file, lines, true);
    if (kw) arr = arr.filter((l) => l.toLowerCase().includes(kw));
    return { file: q.get("file") === "run" ? "run" : "dsh", lines: arr };
  },
  // 聊天记录（含主动消息），新→旧
  "GET /api/history": async (q) => {
    const uid = q.get("uid") || MASTER;
    const limit = Math.min(parseInt(q.get("limit") || "120", 10) || 120, 500);
    const hist = histories();
    const entries = (hist[uid] || []).slice(-limit).reverse();
    return { uid, master: uid === MASTER, count: (hist[uid] || []).length, entries };
  },
  "GET /api/thoughts": async (q) => {
    const uid = q.get("uid") || MASTER;
    const th = thoughts();
    return { uid, thoughts: (th[uid] || []).slice().reverse() };
  },
  "GET /api/notes": async (q) => {
    const uid = q.get("uid") || MASTER;
    const safe = String(uid).replace(/[^A-Za-z0-9_-]/g, "_");
    let text = "";
    try { text = fs.readFileSync(path.join(DATA, "memories", safe + ".md"), "utf-8"); } catch (e) { text = "（暂无长期记忆）"; }
    return { uid, text };
  },
  "GET /api/memes": async (q) => {
    let text = "";
    try { text = fs.readFileSync(scopes()[q.get("uid")] ? path.join(DATA,"memes",String(q.get("uid"))+".md") : path.join(DATA,"memes.md"), "utf-8"); } catch (e) { text = "（梗图鉴为空）"; }
    return { text };
  },
  "GET /api/session": async (q) => {
    const uid = q.get("uid") || MASTER;
    return { uid, session: readJson(jf(uid, "session"), {}) };
  },
  // 开关面板数据（conf=全局开关，friends=按用户开关原始表，users=用户列表：主人排最前）
  "GET /api/switches": async () => {
    const friends = readJson(path.join(DATA, "friends_all.json"), {});
    for (const [key,source] of Object.entries(scopes())) {
      const overrides=friends[key] || {}, legacy=friends[source.sender] || {};
      friends[key]={...overrides};
      for(const feature of USER_KEYS) friends[key][feature]=feature in overrides ? overrides[feature] : legacy[feature]===false ? false : !(source.private && feature==="proactive");
    }
    const hist = histories();
    const names = readJson(path.join(DATA, "names_all.json"), {});
    // 用户列表 = 聊天记录键 ∪ friends_all 键 ∪ {主人}，每项 {uid, name, master}，主人排最前
    const uids = Array.from(new Set([MASTER].concat(Object.keys(hist), Object.keys(friends), Object.keys(scopes()))));
    const users = uids
      .map((uid) => ({ uid, name: names[uid] || (scopes()[uid] ? ((scopes()[uid].private ? "私聊" : "群 "+scopes()[uid].group)+" · "+scopes()[uid].sender+" · "+scopes()[uid].instance) : "旧档（来源未定）"), master: uid === MASTER }))
      .sort((a, b) => (b.master ? 1 : 0) - (a.master ? 1 : 0));
    const conf2 = readJson(path.join(DATA, "dsh_soul_conf.json"), {});
    return {
      conf: conf2,
      conf_keys: SWITCH_KEYS,
      friends,
      user_keys: USER_KEYS,
      users,
      // 积分系统：points_all 全量 + 全局默认（points_daily 数值 / points_enabled 布尔，缺省 30/true）
      points: pointsView(),
      points_daily: typeof conf2.points_daily === "number" ? conf2.points_daily : 30,
      points_enabled: conf2.points_enabled !== false,
      blocked: readJson(path.join(DATA, "blocked_all.json"), []),
      silence: {...readJson(path.join(DATA,"silence_all.json"),{}),...readJson(path.join(DATA,"silence_v2.json"),{})},
      names,
      master: MASTER,
    };
  },
  // 图库统计（借 venv python 查 sqlite 索引）
  "GET /api/stickers": async () => {
    const code = "import sqlite3,json,glob,os;" +
      "out={};" +
      "base=r'" + DATA.replace(/\\/g, "\\\\") + "\\\\sticker_packs';" +
      "[out.setdefault(os.path.basename(os.path.dirname(db)),dict(sqlite3.connect(db).execute('SELECT tag,COUNT(*) FROM memes GROUP BY tag').fetchall())) for db in glob.glob(base+'\\\\*\\\\index.db')];" +
      "print(json.dumps(out,ensure_ascii=False))";
    const r = await execFileP(VENV_PY, ["-c", code]);
    try { return { packs: JSON.parse(r.out.trim().split("\n").pop()) }; }
    catch (e) { return { packs: {}, error: r.out.slice(0, 300) }; }
  },
  // 老记录示意：某情绪桶任取一张图的相对路径（借 venv python 查各 pack 的 index.db）
  "GET /api/sticker_sample": async (q) => {
    const tag = String(q.get("tag") || "").trim();
    if (!/^[A-Za-z0-9_-]{1,30}$/.test(tag)) return { rel: "" };
    const code = "import sqlite3,json,glob,os,random;" +
      "base=r'" + DATA.replace(/\\/g, "\\\\") + "\\\\sticker_packs';" +
      "tag=" + JSON.stringify(tag) + ";" +
      "res=None;" +
      "dbs=glob.glob(base+'\\\\*\\\\index.db');" +
      "random.shuffle(dbs);" +
      "exec(\"for db in dbs:\\n rows=sqlite3.connect(db).execute('SELECT path FROM memes WHERE tag=? LIMIT 30',(tag,)).fetchall()\\n if rows:\\n  res={'pack':os.path.basename(os.path.dirname(db)),'rel':random.choice(rows)[0]}\\n  break\");" +
      "print(json.dumps(res,ensure_ascii=False))";
    const r = await execFileP(VENV_PY, ["-c", code]);
    try {
      const j = JSON.parse(r.out.trim().split("\n").pop());
      return j && j.rel ? { rel: "sticker_packs/" + j.pack + "/" + String(j.rel).replace(/\\/g, "/") } : { rel: "" };
    } catch (e) { return { rel: "", error: r.out.slice(0, 200) }; }
  },
};

// ---- AstrBot 进程启停（与备忘录同一套：launcher 脚本起、taskkill /T /F 停） ----
const LAUNCHER = path.join(DSH, "start-bot.cmd");
async function botPids() {
  const r = await execFileP("tasklist", ["/FI", "IMAGENAME eq astrbot.exe", "/FO", "CSV", "/NH"]);
  const pids = [];
  for (const line of r.out.split(/\r?\n/)) {
    const m = line.match(/"?astrbot\.exe"?,"?(\d+)"?/i);
    if (m) pids.push(parseInt(m[1], 10));
  }
  return pids;
}
async function botStop() {
  const pids = await botPids();
  for (const pid of pids) await execFileP("taskkill", ["/PID", String(pid), "/T", "/F"]);
  return pids;
}
function botStart() {
  // 独立 detached 进程启动 launcher，控制台自身重启/退出不影响机器人
  const child = spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", '""'+LAUNCHER+'" -RuntimeRoot "'+DSH+'""'], { detached: true, stdio: "ignore", windowsHide: true, windowsVerbatimArguments:true });
  child.unref();
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

const post = {
  "/api/people/link": async body => workbench.link(body),
  "/api/people/unlink": async body => workbench.unlink(body),
  "/api/people/deny": async body => workbench.deny(body),
  "/api/people/confirm": async body => workbench.confirm(body),
  // 机器人进程开关：start / stop / restart
  "/api/bot": async (b) => {
    const action = String(b.action || "");
    if (action === "stop") {
      const killed = await botStop();
      return { ok: true, action, killed, running: (await botPids()).length > 0 };
    }
    if (action === "start") {
      if ((await botPids()).length > 0) return { ok: true, action, note: "已在运行" };
      botStart();
      await sleep(4000);
      return { ok: true, action, running: (await botPids()).length > 0 };
    }
    if (action === "restart") {
      await botStop();
      await sleep(1500);
      botStart();
      await sleep(4000);
      return { ok: true, action, running: (await botPids()).length > 0 };
    }
    return { ok: false, error: "action 须为 start/stop/restart" };
  },

  // 控制台自重启：进程自我退出可由非提权 shell 触发（绕过 taskkill 拒绝访问）
  "/api/console": async (b) => {
    if (String(b.action || "") !== "restart") return { ok: false, error: "action 须为 restart" };
    setTimeout(() => {
      const child = spawn(process.execPath, [__filename, "--port", String(PORT)], { detached: true, stdio: "ignore", windowsHide: true, cwd: __dirname });
      child.unref();
      setTimeout(() => process.exit(0), 500);
    }, 300);
    return { ok: true, action: "restart", note: "控制台将在 1 秒内自重启" };
  },

  "/api/delete/preview": async b => applyState("preview", b),
  "/api/history/clear": async b => applyState("delete", b),
  "/api/admin_send": async b => {
    if (!b.target_key || !["group","private"].includes(b.kind) || !b.instance)
      return {ok:false,applied:false,error:"必须明确选择目标类型与平台实例"};
    return applyState("send", b);
  },
  "/api/admin_broadcast": async b => {
    if (!Array.isArray(b.targets) || !b.targets.length || b.targets.length>20 || b.targets.some(t=>!t.target_key||!t.kind||!t.instance))
      return {ok:false,error:"必须明确选择目标列表（每次最多20个）"};
    const results=[];
    for (const target of b.targets) results.push(await applyState("send",{...target,text:b.text}));
    return {ok:results.every(r=>r.ok),count:results.length,results};
  },
};
for (const operation of ["switch","user","name","points","points/grant","points/conf","unblock","unsilence","thought/del"])
  post["/api/"+operation] = async body => applyState(operation,body);

// ---- 媒体文件直出（语音/图片）：白名单根目录 + 扩展名校验 + Range 支持（audio 拖动） ----
function serveMedia(f, req, res) {
  try {
    const rp = fs.realpathSync(path.resolve(DATA, f));
    const low = rp.toLowerCase();
    const inRoot = MEDIA_ROOTS.some((r) => {
      const rl = r.toLowerCase();
      return low === rl || low.startsWith(rl + path.sep);
    });
    const ext = path.extname(rp).toLowerCase();
    const sentRoot = path.join(DATA, "media", "sent").toLowerCase() + path.sep;
    const download = !MEDIA_TYPES[ext] && low.startsWith(sentRoot);
    if (!inRoot || (!MEDIA_TYPES[ext] && !download)) { res.writeHead(403); res.end("forbidden"); return; }
    const st = fs.statSync(rp);
    const type = MEDIA_TYPES[ext] || "application/octet-stream";
    if (download) res.setHeader("content-disposition", "attachment; filename*=UTF-8''" + encodeURIComponent(path.basename(rp)));
    const range = req.headers.range;
    if (range) {
      const m = /bytes=(\d*)-(\d*)/.exec(range);
      let start = m && m[1] ? parseInt(m[1], 10) : 0;
      let end = m && m[2] ? parseInt(m[2], 10) : st.size - 1;
      if (isNaN(start) || isNaN(end) || start > end || end >= st.size) { res.writeHead(416); res.end(); return; }
      res.writeHead(206, {
        "content-type": type, "content-length": end - start + 1,
        "content-range": "bytes " + start + "-" + end + "/" + st.size, "accept-ranges": "bytes",
      });
      fs.createReadStream(rp, { start, end }).pipe(res);
    } else {
      res.writeHead(200, { "content-type": type, "content-length": st.size, "accept-ranges": "bytes", "cache-control": "no-store" });
      fs.createReadStream(rp).pipe(res);
    }
  } catch (e) { res.writeHead(404); res.end("not found"); }
}

const server = http.createServer(async (req, res) => {
  try {
    if (!protect(req, res)) return;
    if (!req.url.startsWith("/") || req.url.startsWith("//")) { send(res, 400, {error:"请求路径无效"}); return; }
    const u = new URL(req.url, "http://x");
    if (req.method === "GET" && u.pathname === "/api/media") {
      serveMedia(u.searchParams.get("f") || "", req, res);
      return;
    }
    if (req.method === "GET" && (u.pathname === "/" || u.pathname === "/index.html")) {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
      res.end(fs.readFileSync(path.join(__dirname, "public", "index.html")));
      return;
    }
    if (req.method === "GET" && ["/assets/user-workbench.js","/assets/reading-state.js"].includes(u.pathname)) {
      res.writeHead(200, {"content-type":"application/javascript; charset=utf-8", "cache-control":"no-store"});
      res.end(fs.readFileSync(path.join(__dirname,"public",path.basename(u.pathname))));
      return;
    }
    if (req.method === "GET" && api["GET " + u.pathname]) {
      send(res, 200, await api["GET " + u.pathname](u.searchParams));
      return;
    }
    if (req.method === "POST" && post[u.pathname]) {
      const body = await readBody(req);
      const operationIds=[body.uid,body.target_key,...(Array.isArray(body.targets)?body.targets.map(t=>t?.target_key):[])];
      if (!u.pathname.startsWith('/api/people/') && operationIds.some(value=>typeof value==='string'&&/^person_[a-f0-9]{64}$/.test(value))) {
        send(res,400,{ok:false,applied:false,error:'聚合入口不是操作来源，请明确选择原始来源会话'});
        return;
      }
      send(res, 200, await post[u.pathname](body));
      return;
    }
    send(res, 404, { error: "not found" });
  } catch (e) {
    send(res, e.statusCode || 500, { ok:false, error: String(e && e.message || e) });
  }
});

server.requestTimeout = 15000;
server.headersTimeout = 10000;
return server;
}

module.exports = { createConsoleServer };
if (require.main === module) {
  const server = createConsoleServer();
  const i = process.argv.indexOf("--port");
  const port = parseInt((i >= 0 && process.argv[i + 1]) || process.env.PORT || "7850", 10);
  server.listen(port, "127.0.0.1", () => {
    console.log("[dsh-console] listening on http://127.0.0.1:" + server.address().port);
  });
}
