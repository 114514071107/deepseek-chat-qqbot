// ds娘 AstrBot 控制台（零依赖 node:http）
// 只监听 127.0.0.1；直接读写 D:\dsbot\dsh_data 下的运行时文件（与插件同一份数据，热生效）
const http = require("http");
const fs = require("fs");
const path = require("path");
const { execFile, spawn } = require("child_process");

// ==================== 部署配置（使用前必改，共 2 处） ====================
// ① AstrBot 安装根目录
const DSH = "D:\\dsbot";
// ② 主人的 QQ openid（须与插件 main.py 里的 MASTER_OPENID 一致）
const MASTER = "YOUR_MASTER_OPENID";
// ============================================================
const DATA = path.join(DSH, "dsh_data");
const RUN_LOG = path.join(DSH, "astrbot-run.log");
const ERR_LOG = path.join(DATA, "dsh_err.log");
const CMD_CONFIG = path.join(DSH, "data", "cmd_config.json");
const VENV_PY = path.join(DSH, "venv", "Scripts", "python.exe");
// 后端代码版本指纹：每次改 server.js 递增；前端带同名常量，不一致时提示用户重开控制台（防"新页面+旧进程"错位）
const API_VER = "20260902-3";
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
  ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
};

function argVal(name, dflt) {
  const i = process.argv.indexOf("--" + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}
const HOST = argVal("host", process.env.HOST || "127.0.0.1");
const PORT = parseInt(argVal("port", process.env.PORT || "7850"), 10);

function readJson(file, dflt) {
  try { return JSON.parse(fs.readFileSync(file, "utf-8")); } catch (e) { return dflt; }
}
function writeJson(file, obj) {
  const tmp = file + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 1));
  fs.renameSync(tmp, file);
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
  return new Promise((resolve) => {
    let b = "";
    req.on("data", (c) => { b += c; if (b.length > 65536) req.destroy(); });
    req.on("end", () => { try { resolve(JSON.parse(b || "{}")); } catch (e) { resolve({}); } });
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
  // 状态总览：进程、文件新鲜度、各 uid 数据量、模型与开关摘要
  "GET /api/status": async () => {
    const proc = await execFileP("tasklist", ["/FI", "IMAGENAME eq astrbot.exe", "/FO", "CSV", "/NH"]);
    const running = proc.ok && proc.out.includes("astrbot.exe");
    const hist = readJson(path.join(DATA, "history_all.json"), {});
    const th = readJson(path.join(DATA, "thoughts_all.json"), {});
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
    const hist = readJson(path.join(DATA, "history_all.json"), {});
    const entries = (hist[uid] || []).slice(-limit).reverse();
    return { uid, master: uid === MASTER, count: (hist[uid] || []).length, entries };
  },
  "GET /api/thoughts": async (q) => {
    const uid = q.get("uid") || MASTER;
    const th = readJson(path.join(DATA, "thoughts_all.json"), {});
    return { uid, thoughts: (th[uid] || []).slice().reverse() };
  },
  "GET /api/notes": async (q) => {
    const uid = q.get("uid") || MASTER;
    const safe = String(uid).replace(/[^A-Za-z0-9_-]/g, "_");
    let text = "";
    try { text = fs.readFileSync(path.join(DATA, "memories", safe + ".md"), "utf-8"); } catch (e) { text = "（暂无长期记忆）"; }
    return { uid, text };
  },
  "GET /api/memes": async () => {
    let text = "";
    try { text = fs.readFileSync(path.join(DATA, "memes.md"), "utf-8"); } catch (e) { text = "（梗图鉴为空）"; }
    return { text };
  },
  "GET /api/session": async (q) => {
    const uid = q.get("uid") || MASTER;
    return { uid, session: readJson(jf(uid, "session"), {}) };
  },
  // 开关面板数据（conf=全局开关，friends=按用户开关原始表，users=用户列表：主人排最前）
  "GET /api/switches": async () => {
    const friends = readJson(path.join(DATA, "friends_all.json"), {});
    const hist = readJson(path.join(DATA, "history_all.json"), {});
    const names = readJson(path.join(DATA, "names_all.json"), {});
    // 用户列表 = 聊天记录键 ∪ friends_all 键 ∪ {主人}，每项 {uid, name, master}，主人排最前
    const uids = Array.from(new Set([MASTER].concat(Object.keys(hist), Object.keys(friends))));
    const users = uids
      .map((uid) => ({ uid, name: names[uid] || "", master: uid === MASTER }))
      .sort((a, b) => (b.master ? 1 : 0) - (a.master ? 1 : 0));
    const conf2 = readJson(path.join(DATA, "dsh_soul_conf.json"), {});
    return {
      conf: conf2,
      conf_keys: SWITCH_KEYS,
      friends,
      user_keys: USER_KEYS,
      users,
      // 积分系统：points_all 全量 + 全局默认（points_daily 数值 / points_enabled 布尔，缺省 30/true）
      points: readJson(path.join(DATA, "points_all.json"), {}),
      points_daily: typeof conf2.points_daily === "number" ? conf2.points_daily : 30,
      points_enabled: conf2.points_enabled !== false,
      blocked: readJson(path.join(DATA, "blocked_all.json"), []),
      silence: readJson(path.join(DATA, "silence_all.json"), {}),
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
const LAUNCHER = DSH + "\\start-astrbot-launcher.cmd";
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
  const child = spawn("cmd", ["/d", "/c", LAUNCHER], { detached: true, stdio: "ignore", windowsHide: true });
  child.unref();
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

const post = {
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

  // 功能开关（写 dsh_soul_conf.json，插件每轮热读）
  "/api/switch": async (b) => {
    if (!SWITCH_KEYS.includes(b.key)) return { ok: false, error: "未知开关" };
    const file = path.join(DATA, "dsh_soul_conf.json");
    const conf = readJson(file, {});
    conf[b.key] = !!b.value;
    writeJson(file, conf);
    return { ok: true, conf };
  },
  // 按用户功能开关（写 friends_all.json，十键，全用户含主人通用）
  "/api/user": async (b) => {
    if (!b.uid || !USER_KEYS.includes(b.key)) return { ok: false, error: "参数错误" };
    const file = path.join(DATA, "friends_all.json");
    const friends = readJson(file, {});
    friends[b.uid] = friends[b.uid] || {};
    friends[b.uid][b.key] = !!b.value;
    writeJson(file, friends);
    return { ok: true, friends };
  },
  // 用户备注名（写 names_all.json，键 uid → 字符串；QQ 官方 bot 拿不到昵称，备注名为主标识）
  "/api/name": async (b) => {
    const uid = String(b.uid || "").trim();
    if (!uid) return { ok: false, error: "缺 uid" };
    const file = path.join(DATA, "names_all.json");
    const names = readJson(file, {});
    const name = String(b.name == null ? "" : b.name).trim().slice(0, 30);
    if (name) names[uid] = name; else delete names[uid]; // 空备注 = 删除备注
    writeJson(file, names);
    return { ok: true, names };
  },
  // 积分：改余额 {uid, mode:"add"|"set", value}
  "/api/points": async (b) => {
    const uid = String(b.uid || "").trim();
    const val = parseInt(b.value, 10);
    if (!uid || isNaN(val) || !["add", "set"].includes(b.mode)) return { ok: false, error: "参数错误" };
    const file = path.join(DATA, "points_all.json");
    const all = readJson(file, {});
    const ent = all[uid] || { balance: 0, grant: null, last: "", spent: 0, notified: "" };
    ent.balance = Math.max(0, b.mode === "add" ? (parseInt(ent.balance, 10) || 0) + val : val);
    all[uid] = ent;
    writeJson(file, all);
    return { ok: true, entry: ent };
  },
  // 积分：每日赠送覆盖 {uid, value}（value=null 恢复跟随全局 points_daily）
  "/api/points/grant": async (b) => {
    const uid = String(b.uid || "").trim();
    if (!uid) return { ok: false, error: "缺 uid" };
    const file = path.join(DATA, "points_all.json");
    const all = readJson(file, {});
    const ent = all[uid] || { balance: 0, grant: null, last: "", spent: 0, notified: "" };
    if (b.value === null || b.value === "" || b.value === undefined) ent.grant = null;
    else {
      const v = parseInt(b.value, 10);
      if (isNaN(v) || v < 0) return { ok: false, error: "赠送值无效" };
      ent.grant = v;
    }
    all[uid] = ent;
    writeJson(file, all);
    return { ok: true, entry: ent };
  },
  // 积分：全局配置 {daily, enabled}（写 dsh_soul_conf.json 的 points_daily / points_enabled）
  "/api/points/conf": async (b) => {
    const file = path.join(DATA, "dsh_soul_conf.json");
    const conf = readJson(file, {});
    if (b.daily !== undefined) {
      const v = parseInt(b.daily, 10);
      if (isNaN(v) || v < 0) return { ok: false, error: "每日赠送值无效" };
      conf.points_daily = v;
    }
    if (b.enabled !== undefined) conf.points_enabled = !!b.enabled;
    writeJson(file, conf);
    return { ok: true, points_daily: conf.points_daily, points_enabled: conf.points_enabled !== false };
  },
  // 移出黑名单
  "/api/unblock": async (b) => {
    const file = path.join(DATA, "blocked_all.json");
    let list = readJson(file, []);
    const before = list.length;
    list = list.filter((u) => u !== b.uid);
    writeJson(file, list);
    return { ok: true, removed: before - list.length, blocked: list };
  },
  // 解除休眠
  "/api/unsilence": async (b) => {
    const file = path.join(DATA, "silence_all.json");
    const sil = readJson(file, {});
    delete sil[b.uid];
    writeJson(file, sil);
    return { ok: true, silence: sil };
  },
  // 清空某 uid 聊天记录（先备份）
  "/api/history/clear": async (b) => {
    if (!b.uid) return { ok: false, error: "缺 uid" };
    const file = path.join(DATA, "history_all.json");
    const hist = readJson(file, {});
    const n = (hist[b.uid] || []).length;
    if (n === 0) return { ok: true, cleared: 0 };
    fs.copyFileSync(file, file + ".bak-console-" + Date.now());
    hist[b.uid] = [];
    writeJson(file, hist);
    return { ok: true, cleared: n };
  },
  // 删除某 uid 一个念头
  "/api/thought/del": async (b) => {
    const file = path.join(DATA, "thoughts_all.json");
    const th = readJson(file, {});
    const arr = th[b.uid] || [];
    if (typeof b.index === "number" && arr[b.index]) {
      arr.splice(b.index, 1);
      th[b.uid] = arr;
      writeJson(file, th);
      return { ok: true, thoughts: arr };
    }
    return { ok: false, error: "下标无效" };
  },
  // 管理员直发指定用户（不写入记忆）
  "/api/admin_send": async (b) => {
    const uid = String(b.uid || "").trim();
    const text = String(b.text || "").trim();
    if (!uid || !text) return { ok: false, error: "缺 uid 或内容" };
    const token = await qqToken();
    const r = await qqC2C(token, uid, text.slice(0, 2000));
    return { ok: r.status < 300, status: r.status, resp: r.body, sent_to: uid, note: "管理员直发，不写入记忆" };
  },
  // 管理员广播全部已知用户（主人 + umo_all 里有过来往的 uid）
  "/api/admin_broadcast": async (b) => {
    const text = String(b.text || "").trim();
    if (!text) return { ok: false, error: "缺内容" };
    const umo = readJson(path.join(DATA, "umo_all.json"), {});
    const targets = Array.from(new Set([MASTER].concat(Object.keys(umo))));
    const token = await qqToken();
    const results = [];
    for (const uid of targets) {
      try {
        const r = await qqC2C(token, uid, text.slice(0, 2000));
        results.push({ uid, ok: r.status < 300, status: r.status, resp: r.status >= 300 ? r.body : "" });
      } catch (e) {
        results.push({ uid, ok: false, error: String(e && e.message || e) });
      }
      await new Promise((r2) => setTimeout(r2, 400));
    }
    return { ok: results.every((x) => x.ok), count: results.length, results, note: "管理员广播，不写入记忆" };
  },
};

// ---- 管理员发信（直连 QQ 官方 API，绕过插件 → 不写入任何记忆/历史） ----
let _tokenCache = { token: null, exp: 0 };
function qqCreds() {
  const cfg = readJson(CMD_CONFIG, {});
  const plat = (cfg.platform || []).find((p) => p.type === "qq_official" || String(p.id || "").startsWith("qqbot-")) || {};
  if (!plat.appid || !plat.secret) throw new Error("cmd_config.json 缺少 qq_official 平台凭据（appid/secret）");
  return plat;
}
async function qqToken() {
  if (_tokenCache.token && Date.now() < _tokenCache.exp) return _tokenCache.token;
  const plat = qqCreds();
  const r = await fetch("https://bots.qq.com/app/getAppAccessToken", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ appId: plat.appid, clientSecret: plat.secret }),
  });
  const j = await r.json();
  if (!j.access_token) throw new Error("getAppAccessToken 失败：" + JSON.stringify(j).slice(0, 200));
  _tokenCache = { token: j.access_token, exp: Date.now() + (parseInt(j.expires_in || "7000", 10) - 300) * 1000 };
  return _tokenCache.token;
}
async function qqC2C(token, openid, text) {
  const r = await fetch("https://api.sgroup.qq.com/v2/users/" + encodeURIComponent(openid) + "/messages", {
    method: "POST",
    headers: { "content-type": "application/json", Authorization: "QQBot " + token },
    body: JSON.stringify({ content: text, msg_type: 0, msg_seq: Math.floor(Math.random() * 10000) + 1 }),
  });
  return { status: r.status, body: (await r.text()).slice(0, 300) };
}

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
    if (!inRoot || !MEDIA_TYPES[ext]) { res.writeHead(403); res.end("forbidden"); return; }
    const st = fs.statSync(rp);
    const type = MEDIA_TYPES[ext];
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
    if (req.method === "GET" && api["GET " + u.pathname]) {
      send(res, 200, await api["GET " + u.pathname](u.searchParams));
      return;
    }
    if (req.method === "POST" && post[u.pathname]) {
      send(res, 200, await post[u.pathname](await readBody(req)));
      return;
    }
    send(res, 404, { error: "not found" });
  } catch (e) {
    send(res, 500, { error: String(e && e.message || e) });
  }
});

server.listen(PORT, HOST, () => {
  console.log("[dsh-console] listening on http://" + HOST + ":" + PORT);
});
