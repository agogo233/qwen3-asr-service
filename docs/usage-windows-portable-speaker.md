# Qwen3-ASR Service 使用文档（Windows AMD64 + NVIDIA GPU · 便携版）

> 适用：Windows 10/11 x64 + NVIDIA 显卡（≥6GB 显存）+ 便携式 Python（免安装）
> 模型：Qwen3-ASR-1.7B（FunASR 后端）+ CAM++ 说话人分离 + 声纹库
> 模型源：ModelScope（国内直连）；全部功能走内置 WebUI，无需 curl

## 目录

- [概述与架构](#概述与架构)
- [快速开始（30 秒）](#快速开始30-秒)
- [部署准备](#部署准备)
- [安装（三种方式任选其一）](#安装三种方式任选其一)
- [配置详解](#配置详解)
- [启动与验证](#启动与验证)
- [WebUI 使用指南](#webui-使用指南)
- [API 参考](#api-参考)
- [声纹库使用详解](#声纹库使用详解)
- [显存与性能](#显存与性能)
- [常见问题排错](#常见问题排错)
- [更新与回滚](#更新与回滚)
- [合规与数据](#合规与数据)

---

## 概述与架构

Qwen3-ASR Service 是本地语音转写服务，内置 WebUI（无需命令行操作）：

```
浏览器 ── /web-ui（离线转写） /web-ui/stream（实时转写）
          /web-ui/speakers（说话人管理） /web-ui/docs（文档中心）
                  │
        FastAPI 服务（默认 127.0.0.1:8765）
                  │
   ┌──────────────┼──────────────┐
 Qwen3-ASR 1.7B  CAM++ 说话人分离  声纹库（SQLite 落盘）
  （CUDA 推理）    （CPU 推理）      （Voiceprint DB）
```

核心能力：

- **离线转写**：上传音频文件 → 中文识别 + 标点恢复 + 词级时间戳 + 说话人分离/识别
- **实时转写**：麦克风推流或文件模拟推流
- **声纹库**：说话人登记（多样本）、1:N 识别、自动登记、改名、删除（被遗忘权）
- **双语言 WebUI**：中文/英文一键切换，明暗主题

## 快速开始（30 秒）

> 使用现成便携包（含 Python 3.12 + PyTorch 2.6.0 cu124 + 全部依赖）时：

```powershell
# 1. 下载并解压便携包到 asr-service 目录（见「安装」）
# 2. 首次运行一键安装
.\setup.ps1
# 3. 启动服务
.\start.ps1
# 4. 浏览器打开
http://127.0.0.1:8765/web-ui
```

首次启动自动从 ModelScope 下载 Qwen3-ASR-1.7B 模型（约 3.5GB），等待片刻即可使用。

## 部署准备

### 硬件要求

| 项 | 要求 |
|----|------|
| CPU | x64，4 核及以上 |
| 内存 | ≥16GB（推荐 32GB） |
| 显卡 | NVIDIA，显存 **≥6GB**（1.7B 全功能约 6-8GB） |
| 磁盘 | ≥20GB 空闲（模型 + 便携 Python + 依赖约 10GB） |

> 4-6GB 显存：用 0.6B 模型 + 关闭对齐；<4GB：同时关闭标点恢复
> 说话人分离（CAM++）为 CPU 推理（仅 28MB），不占用显存

### 系统前置

- **显卡驱动**：NVIDIA 驱动 ≥ 535（`nvidia-smi` 可在 PowerShell 中直接运行）
- **VC++ 运行库**：安装 Microsoft Visual C++ 2015-2022 Redistributable x64
  （下载：https://aka.ms/vs/17/release/vc_redist.x64.exe）
- **浏览器**：Chrome / Edge 最新版（WebUI 依赖现代浏览器）

### 便携包内容

```
asr-service/
├── bin/                     # 便携可执行目录
│   ├── python/              # 便携 Python 3.12（python.exe 及完整 stdlib）
│   │   └── python312._pth   # 已修改：加载 lib/site-packages
│   ├── ffmpeg.exe           # 音频解码（ffprobe.exe 一并放入）
│   └── get-pip.py           # 备用：手动装 pip
├── lib/site-packages/       # 所有 Python 第三方依赖（torch cu124 等）
├── setup.ps1                # 一键安装脚本
├── start.ps1                # 启动脚本
├── manage.ps1               # 管理菜单（安装/启动/停止/日志/便携打包）
└── config.yaml              # 服务配置（首次启动自动生成）
```

**便携包下载**（百度网盘）：

- `qwen3-asr-service-python3.12-pytorch2.6-cu124-bin.7z`
- https://pan.baidu.com/s/1ahqW1mxIoNJTG2k6b4PkkA?pwd=6cth 提取码 `6cth`

## 安装（三种方式任选其一）

### 方式一：现成便携包（推荐）

1. 下载便携包（见「部署准备」），解压后确认目录结构
2. `bin\python\python.exe` 与 `lib\site-packages` **两者必须存在**（setup.ps1 的检测条件）
3. 运行 `.\setup.ps1`（安装/升级依赖、生成 config.yaml、下载模型）

### 方式二：自配便携 Python（官方 Embeddable 包）

适合已有 Python 3.12 或想自行管理的用户：

1. 下载 **Python 3.12**（勿用 3.13，PyTorch 2.6.0 无对应 wheel）Windows embeddable 包
   → https://www.python.org/downloads/windows/
2. 解压，将目录改名为 `python`，整体放入 `asr-service\bin\`
3. `python312._pth` 无需手动处理：**setup.ps1 / setup.bat 会自动检查并修复**（备份原文件为 `.bak`，写入以下 5 行，同时解决 pip 可见性、依赖路径与 `app` 模块导入）：
   ```
   python312.zip
   .
   ../..
   ../../lib/site-packages
   import site
   ```
4. 手动创建空目录 `asr-service\lib\site-packages`
5. 下载 ffmpeg.exe（+ ffprobe.exe）放入 `asr-service\bin\`
   → https://www.gyan.dev/ffmpeg/builds/（选 essentials，解压后取 bin 下两个 exe）
6. 下载 get-pip.py 放入 `asr-service\bin\`（备用：https://bootstrap.pypa.io/get-pip.py）
7. 运行 `.\setup.ps1` 或 `setup.bat`（内部用 `bin\python\python.exe -m pip` 安装依赖；pip 安装、依赖、torch 均默认走国内镜像）
8. 若便携 Python 无 pip，脚本会用 `bin\get-pip.py` 兜底安装（同样走清华镜像）

> 注意：若手动编辑过 `python312._pth`，请保持上述 5 行结构；`import site` 必须启用、`../../lib/site-packages` 必须存在（否则 pip 不可见），且 `../..` 必须存在（否则 `start.bat` 报 `No module named 'app'`）。

### 方式三：系统 Python（已有完整环境）

系统已装 Python 3.10-3.12 的用户，可直接：

1. 安装依赖：`pip install -r requirements.txt`（含 torch==2.6.0 默认 CPU 版）
2. **Windows + N 卡用户改装 CUDA 版**（wheel 内嵌 CUDA DLL，无需额外 nvidia pip 包）：
   ```powershell
   pip install --no-deps torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 `
     --index-url https://download.pytorch.org/whl/cu124
   ```
3. `pip install ffmpeg` 或确保系统 PATH 有 ffmpeg
4. `python start.py` 或 `python -m app.main`

> **国内镜像**：setup.ps1 / setup.bat / manage.ps1 已默认使用清华 PyPI（普通依赖）；torch cu124 按 上交大 → 阿里云 → PyTorch 官方 顺序逐源尝试，每源失败自动重试一次。
> 自定义镜像：设置环境变量 `$env:PIP_INDEX_URL`（PyPI 源）与 `$env:TORCH_INDEX_URL`（torch 源，最优先尝试）后运行脚本即可覆盖。

## 配置详解

配置文件 `config.yaml`（首次启动自动生成，无则用内置默认值）。

**配置优先级**：命令行显式参数 > config.yaml > 环境变量 > 内置默认值。

### 推荐配置（1.7B + 声纹库 + WebUI）

```yaml
# 服务
host: 127.0.0.1        # 仅本机访问；局域网共享改 0.0.0.0
port: 8765
api_key: "请改成自己的密钥"   # ★ 声纹库强制要求非空（生物识别安全）
web: true              # 启用 WebUI

# 模型（FunASR 后端）
model_source: modelscope   # 国内直连下载
model_size: 1.7b           # 显存紧张改 0.6b
device: cuda               # N 卡必须 cuda；无卡改 cpu（慢）

# 能力开关
enable_align: true     # 词级时间戳（对齐）
use_punc: true         # 标点恢复
enable_speaker: true   # 说话人分离引擎（CAM++）
enable_speaker_db: true  # 声纹库

# 声纹库
speaker_auto_enroll: true  # 转写时未知说话人自动登记（需簇语音 ≥10s）
speaker_id_threshold: 0.75 # 识别阈值（余弦 0-1）
speaker_id_margin: 0.15    # 区分余量（防近邻打架）
```

### 关键开关说明

| 配置 | 默认 | 说明 |
|------|------|------|
| `enable_speaker_db` | false | 声纹库总开关；需 `enable_speaker=true` **且** `api_key` 非空，否则自动降级关闭并打 ERROR 日志 |
| `speaker_auto_enroll` | true | 转写识别时自动登记新说话人；手动登记单样本 ≥3 秒有效语音，自动登记需 ≥10 秒 |
| `model_source` | modelscope | 国内网络首选；也可 `hf`（HuggingFace） |
| `device` | cuda | `nvidia-smi` 可用才有效；启动日志会显示实际设备 |

## 启动与验证

### 启动

```powershell
.\start.ps1            # 前台运行（关窗口即停）
# 或
.\manage.ps1           # 管理菜单：2) 启动 / 3) 停止 / 4) 日志
```

### 验证

1. 启动日志出现 `Qwen3-ASR Service 就绪 ... 监听 127.0.0.1:8765` 与 `Web UI 已启用`
2. 浏览器打开 `http://127.0.0.1:8765/web-ui`
3. 右上角状态点应为绿色「服务就绪」，页面显示模型信息（1.7b / cuda / speaker_db on）

### 健康检查

```powershell
curl.exe http://127.0.0.1:8765/v2/health
# → {"status":"ready","mode":"offline",...,"speaker_db_enabled":true,...}
```

## WebUI 使用指南

### 页面一览

| 页面 | 地址 | 功能 |
|------|------|------|
| 离线转写 | `/web-ui` | 上传音频转写、说话人识别、任务历史 |
| 实时转写 | `/web-ui/stream` | 麦克风/文件模拟推流实时识别 |
| 说话人管理 | `/web-ui/speakers` | 声纹库：登记、识别、改名、删除 |
| 文档中心 | `/web-ui/docs` | 内置全部文档（含本页） |

### 通用操作

- **API Key**：右上角钥匙图标 → 输入服务端 `api_key` → 保存（存浏览器 localStorage）
- **语言**：右上角中/EN 切换；**主题**：亮/暗/自动循环
- 说话人页在未配置 Key / Key 无效 / 声纹库未启用 / 模型版本失配时，显示对应降级指引 alert

### 离线转写页（/web-ui）

1. 拖拽或点击上传音频（wav/mp3/flac/m4a/aac/ogg/wma/amr/opus，≤1024MB）
2. 勾选「声纹识别」→ 输出中已知说话人显示真名，未知说话人自动登记（占位名「说话人_NN」）
3. 可选高级设置：输出内容、标点、词级时间戳、说话人分离、识别阈值等（留空=服务端默认）
4. 点击「开始识别」→ 任务队列轮询显示进度；右侧任务历史可回看/删除

### 说话人管理页（/web-ui/speakers）

页面顶部三个按钮（未启用声纹库时自动隐藏，仅显示降级指引）：

| 按钮 | 功能 |
|------|------|
| **登记说话人** | 打开登记弹窗（见下） |
| **识别说话人** | 上传单条音频做 1:N 识别（见下） |
| 刷新 | 重新加载列表 |

**登记说话人**：

1. 点「登记说话人」→ 输入显示名称（必填）、备注（可选）
2. **勾选同意声明**（必勾：确认样本音频已获数据主体知情同意；未勾无法提交）
3. 拖拽/点击上传**单人音频样本**（可多选多个文件，每个样本为同一人的清晰语音）
4. 点「登记」→ 成功提示（含模板数，必要时含质量提示）→ 列表即时刷新

> 登记样本建议：3-10 秒清晰人声、无背景噪音、单人独白；多文件登记可提升识别鲁棒性。
> 登记时需服务端 `enable_speaker_db=true` 且模型版本与库一致，否则弹窗报错/按钮隐藏。

**识别说话人**：

1. 点「识别说话人」→ 上传单条音频
2. 点「识别」→ 内联显示结果：匹配到「姓名（相似度 0.xxx）」或「未匹配（相似度不足）」

**列表操作**：

- 改名/备注：行内「改名/备注」→ 保存后**立即**在后续转写中生效
- 删除：行内「删除」→ 二次确认（硬删除不可恢复：模板+留存音频一并清除，说话人退回匿名）
- 来源标记：「自动登记」来自转写识别，「手动登记」来自本页登记

### 实时转写页（/web-ui/stream）

- 麦克风模式：授权后实时识别（说话人分离/识别开关同离线页）
- 文件模拟模式：选择音频文件模拟流式输入

## API 参考

> 全部 `/v2/*` 端点需请求头 `Authorization: Bearer <api_key>`；PowerShell 用 `curl.exe`（`curl` 是 Invoke-WebRequest 别名，不是 curl！）

### 转写

```powershell
# 离线转写（表单 multipart）
curl.exe -X POST http://127.0.0.1:8765/v2/asr `
  -H "Authorization: Bearer 你的key" `
  -F "file=@录音.wav" -F "identify_speakers=true" -F "with_punc=true"

# 任务状态
curl.exe http://127.0.0.1:8765/v2/tasks/<task_id> -H "Authorization: Bearer 你的key"
```

### 声纹库

```powershell
# 登记（多文件 files + consent=true 必须）
curl.exe -X POST http://127.0.0.1:8765/v2/speakers `
  -H "Authorization: Bearer 你的key" `
  -F "name=张三" -F "consent=true" -F "files=@样本1.wav" -F "files=@样本2.wav"

# 列表 / 详情
curl.exe http://127.0.0.1:8765/v2/speakers -H "Authorization: Bearer 你的key"
curl.exe http://127.0.0.1:8765/v2/speakers/<id> -H "Authorization: Bearer 你的key"

# 改名 / 备注（PATCH）
curl.exe -X PATCH http://127.0.0.1:8765/v2/speakers/<id> `
  -H "Authorization: Bearer 你的key" -H "Content-Type: application/json" `
  -d '{"name":"李四","note":"产品部"}'

# 单文件 1:N 识别
curl.exe -X POST http://127.0.0.1:8765/v2/speakers/identify `
  -H "Authorization: Bearer 你的key" -F "file=@待识别.wav"

# 删除（硬删除，不可恢复）
curl.exe -X DELETE http://127.0.0.1:8765/v2/speakers/<id> -H "Authorization: Bearer 你的key"
```

### 错误码约定

| 状态码 | 含义 |
|--------|------|
| 400 | 参数/质量门槛（如未 consent、样本过短、格式不支持） |
| 401 | 鉴权失败（Key 缺失或错误） |
| 404 | 说话人不存在 |
| 413 | 文件超过 1024MB |
| 503 | `speaker_db_disabled`（模块未启用）或 `model_tag_mismatch`（模型版本失配，登记/识别禁用，查看/删除保留） |

## 声纹库使用详解

### 工作流程

```
登记（本页/API/自动）→ 模板入库（SQLite + 质心向量）
    ↓
转写时 identify_speakers=true → 分段声纹提取 → 1:N 比对
    ↓
命中（阈值+余量）→ 显示真名；未命中 → 「匿名说话人」
```

### 三种登记途径

| 途径 | 触发 | 名称 | 说明 |
|------|------|------|------|
| WebUI 手动登记 | 说话人管理页「登记说话人」 | 自填 | 单文件/多文件均可 |
| API 手动登记 | `POST /v2/speakers` | 自填 | 需 `consent=true` |
| 自动登记 | 转写勾选声纹识别 | 「说话人_NN」占位名 | 需簇语音 ≥10s；可在管理页改名 |

### 识别阈值（余弦相似度）

- `speaker_id_threshold`（默认 0.75）：低于此值判未命中
- `speaker_id_margin`（默认 0.15）：最高分与次高分差距小于此值判未命中（近邻打架）
- 开集识别：库外说话人 → `matched=false`，不会误报

### 模型版本一致性

声纹模板与生成引擎的 `model_tag` 绑定。更换模型版本（升级/降级）后：

- 管理页显示「声纹模型版本不一致」：登记/识别禁用，**列表与删除保留**（被遗忘权不受影响）
- 处理：删除库文件重建，或回退到登记时的引擎版本

### 数据位置

- 声纹库数据库与留存音频在服务数据目录（`UPLOADS_DIR` 及 DB 文件），删除说话人即级联清除
- 数据**永不自动清理**，删除需手动操作（页面或 API）

## 显存与性能

| 显存 | 推荐配置 |
|------|----------|
| ≥8GB | 1.7B 全功能（对齐+标点+说话人+声纹库） |
| 6-8GB | 1.7B + 关对齐（`enable_align: false`） |
| 4-6GB | 0.6B + 关对齐 |
| <4GB | 0.6B + 关对齐/标点（或 CPU 模式，显著变慢） |

- 说话人分离 CAM++ 走 CPU（28MB），不占显存
- 转写为任务队列模式，并发请求排队处理；长时间运行建议关注显存占用

## 常见问题排错

| 现象 | 原因与处理 |
|------|-----------|
| 运行 ps1 报 `SecurityError` / `UnauthorizedAccess`（无法加载脚本·未签名） | 执行策略限制 → `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`（一次即可），或临时用 `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1`；或直接用 `setup.bat`（不受策略限制） |
| 运行 ps1 报 `ParserError` / `UnexpectedToken "}"` | 文件被破坏或编码被编辑器转换（如保存成 UTF-16/全角引号）→ 从仓库重新下载原始文件覆盖，勿用记事本保存 ps1 |
| `python.exe -m pip` 报 `No module named pip` | Embeddable Python 的 `python312._pth` 未启用 `import site`（get-pip 虽装成功但 pip 不可见）→ 新版 setup.ps1/setup.bat 会自动修复（备份 `.bak` 后写入 5 行） |
| `setup.bat` 第一行报 `'锘緻echo off' 不是内部或外部命令` | 旧版 bat 带 UTF-8 BOM → 使用新版 `setup.bat`（已去 BOM） |
| `setup.bat` 显示 Setup Complete 但依赖没装上 | 旧版 bat 无错误检查 → 使用新版（torch/依赖失败会提示并退出） |
| 启动报错找不到 python.exe | `bin\python\python.exe` 与 `lib\site-packages` 缺失或位置不对（见自配便携步骤 2/4） |
| 依赖安装到错误位置 | `python312._pth` 未启用 `import site` 或缺少 `../../lib/site-packages` 行（脚本会自动修复；手动修改须保持 5 行结构） |
| 服务起不来：CUDA 相关错误 | 驱动过旧 → 升级 ≥535；未装 VC++ 运行库 → 安装 vc_redist.x64.exe；torch 装成 CPU 版 → 按方式三重装 cu124 wheel |
| 模型下载超时 | 网络问题 → 确认 `model_source: modelscope`；或手动下载模型放入缓存目录 |
| 依赖/torch 下载慢或超时 | torch cu124 按 上交大 → 阿里云 → 官方 顺序逐源尝试（每源重试一次）；可设 `$env:PIP_INDEX_URL` / `$env:TORCH_INDEX_URL` 自定义 |
| WebUI 打不开 | 服务未就绪（等日志「就绪」）；端口被占 → 改 config `port`；防火墙拦截（本机访问一般无碍） |
| 说话人页显示「需要 API Key」 | 右上角钥匙图标配置 `api_key`（与服务端一致）后刷新 |
| 说话人页显示「声纹库未启用」 | 服务端需同时 `enable_speaker: true` + `enable_speaker_db: true` + `api_key` 非空；日志有 ERROR 说明原因 |
| 说话人页显示「模型版本不一致」 | 升级/降级过模型 → 删除库重建或回退版本（见声纹库-模型版本一致性） |
| 登记报 400 未同意 | 需勾选同意声明 / API 传 `consent=true` |
| 登记报 400 质量不足 | 样本过短/静音/多人声 → 换 3-10 秒清晰单人样本 |
| 识别全部未匹配 | 阈值过高 → 调低 `speaker_id_threshold`；或样本与登记音色差异大 → 补登样本 |
| 任务一直排队 | 前序任务占用 GPU；`max_queue_size` 队列满则新任务 503 |
| 日志乱码/无日志 | 用 `.\manage.ps1` 的日志菜单查看滚动日志 |

## 更新与回滚

### 更新

```powershell
git pull                 # 拉取最新代码
.\setup.ps1              # 重跑安装（增量安装依赖）
.\start.ps1              # 重启生效
```

> 若升级涉及模型版本变化，注意声纹库 model_tag 一致性。

### 回滚

```powershell
git log --oneline -5     # 查看历史提交
git checkout <旧提交>    # 回退代码
.\setup.ps1              # 重装对应依赖
```

> 声纹库数据独立于代码，回滚代码不影响库数据；但模型版本回退需与库 tag 匹配。

### 备份

- 声纹库：备份数据库文件（或直接用页面逐个导出说话人信息）
- 配置：备份 `config.yaml`
- 模型：保留 `models` 目录可离线复用

## 合规与数据

- **声纹属生物识别信息**：服务端强制要求配置 `api_key` 才启用声纹库；WebUI 登记必须勾选「已获数据主体知情同意」
- **被遗忘权**：删除说话人 = 硬删除（模板 + 留存音频级联清除，不可恢复），且不受模型版本失配影响（删除永远可用）
- **数据不出本机**：默认 `host: 127.0.0.1`，模型下载完成后完全离线可用（音频、声纹模板、转写结果均存本地）
- **留存音频**：转写上传的音频按服务端留存策略保存于本地数据目录，删除任务记录不会自动删除留存音频（如需清除请手动处理）