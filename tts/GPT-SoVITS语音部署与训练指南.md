# GPT-SoVITS 语音部署与训练指南

> 本包**不含**任何语音权重与录音（版权原因，见《版权与隐私说明.md》）。
> 请用你拥有合法权利的语音数据，按下文自行训练或用参考音频克隆。

## 一、架构

ds娘的语音链路：`「动作：语音」标记 → AstrBot gsv_tts_selfhost 供应商 → 本脚本（127.0.0.1:18765）→ GPT-SoVITS 推理 → 音频发出`。

`tts_server.py` 是一个通用 FastAPI 常驻推理服务（207 行，无任何特定音色绑定）：

- 启动时加载底模（默认 v2 final GPT + v2Pro SoVITS）；
- `POST /tts {text, ref_audio?, ref_text?, language?, format?}` → 返回 mp3/wav；
- 所有路径可用环境变量覆盖：`GS_GPT_PATH` / `GS_SOVITS_PATH` / `GS_REF_AUDIO` / `GS_REF_TEXT` / `TTS_HOST` / `TTS_PORT`。

## 二、环境安装（WSL2 + NVIDIA GPU，约 30~60 分钟）

```bash
# 1. 拉 GPT-SoVITS 官方源码（MIT 许可）
git clone https://github.com/RVC-Boss/GPT-SoVITS ~/.dsh/gpt-sovits
cd ~/.dsh/gpt-sovits

# 2. conda 环境（Python 3.10）
conda create -n gpt-sovits python=3.10 -y && conda activate gpt-sovits
pip install -r requirements.txt
pip install fastapi uvicorn soundfile

# 3. PyTorch（按你的 CUDA 版本选，50 系显卡需 cu128）
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# 4. 按 GPT-SoVITS 官方文档下载预训练底模（v2Pro），放到
#    GPT_SoVITS/pretrained_models/ 下，另需中文 G2PWModel 与 ffmpeg
```

把本目录的 `tts_server.py` 放到 `~/.dsh/gpt-sovits/` 根下。

## 三、音色方案（二选一）

### 方案 A：免训练，参考音频克隆（zero-shot，最快）

不加载训练权重（用官方预训练底模），`tts_server.py` 默认就走这条路：放好你自己的参考音频与对应文字稿即可模仿音色。

```bash
cp your_voice.wav ~/.dsh/gpt-sovits/default_ref.wav   # 3~10 秒清晰人声，自备
export GS_REF_TEXT="你参考音频里说的那句话"
python tts_server.py   # 监听 0.0.0.0:18765
curl "http://127.0.0.1:18765/health"   # ok:true 即成功
```

### 方案 B：微调训练专属音色（效果最好，数据须合规）

用 GPT-SoVITS WebUI（`python webui.py`）完成：数据集格式化（音频切分+ASR 标注）→ SoVITS 训练 → GPT 训练，产出自有权重后：

```bash
export GS_GPT_PATH=/path/to/your.ckpt
export GS_SOVITS_PATH=/path/to/your.pth
python tts_server.py
```

训练数据要求：**你拥有合法使用权的人声录音**，单人、干净、10 分钟以上效果更佳。严禁使用游戏/动画/影视等第三方版权音频。

## 四、常驻与自启（WSL2 systemd 用户服务）

```ini
# ~/.config/systemd/user/gpt-sovits-tts.service
[Unit]
Description=GPT-SoVITS TTS Server
[Service]
WorkingDirectory=%h/.dsh/gpt-sovits
ExecStart=%h/.miniconda3/envs/gpt-sovits/bin/python tts_server.py
Restart=always
[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now gpt-sovits-tts
```

## 五、接入 AstrBot

cmd_config.json 的 provider 加（模板已含）：

```json
{"id": "gsv_ds", "type": "gsv_tts_selfhost", "enable": true,
 "api_base": "http://127.0.0.1:18765", "timeout": 120,
 "gpt_weights_path": "", "sovits_weights_path": "", "gsv_default_parms": {}}
```

验证：QQ 里对她说"发个语音"，应收到一条语音消息。
