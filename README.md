# MusicProfiler

面向校园广播和音乐素材管理的桌面应用。它提供本地曲库管理、NCM 解密导入、批量音频处理、Demucs 人声/伴奏分离、歌单编排，以及广播文件导出。

## 功能

- 导入和检索本地音频：MP3、FLAC、WAV、M4A、Ogg
- 内置 Python NCM 解密导入
  - 不依赖 Unlock Music / UM 可执行文件
  - 解密后的音频保存到工作区，可直接用于后续处理
- 标签管理与曲库筛选
- 批量转码和 EBU R128 响度标准化
- Demucs 人声与伴奏分离
  - 分离完成后自动登记人声和伴奏轨道
  - 可将伴奏单独加入歌单
- 歌单创建、排序、原曲/伴奏混合编排
- 默认歌单
  - 在“歌单管理”中选择一个歌单并设为默认
  - 在素材库右键歌曲即可添加原曲或伴奏到默认歌单
  - 素材库底部显示默认歌单总时长
- 广播文件导出
  - 依次转码、可选响度标准化，再拼接为单个输出文件
  - 自动忽略输入文件中的封面图片流，损坏封面不会阻断音频导出
- 单 worker 任务队列与任务监视器

## 环境要求

- Python 3.12+
- FFmpeg 和 FFprobe（必需）
- Demucs（可选，仅人声/伴奏分离需要）

NCM 解密使用 Python 内置实现（特此感谢[unlock-music](https://github.com/unlock-music)以及他们的[um-cli](https://git.unlock-music.dev/um/cli)！）。

## 安装

建议在虚拟环境中安装依赖：

```bash
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\Activate.ps1
pip install cryptography ttkbootstrap pytest
```

macOS / Linux：

```bash
source .venv/bin/activate
pip install cryptography ttkbootstrap pytest
```

也可以根据 `pyproject.toml` 安装运行依赖：

```bash
pip install .
```

## 启动

```bash
python main.py
```

首次启动会打开工具配置向导：

- 配置 **FFmpeg** 和 **FFprobe** 的可执行文件路径；
- 如需使用分离功能，再配置 **Demucs**；
- 启动后仍可通过菜单 **设置 → 配置工具** 修改路径。

配置保存在：

```text
~/.musicprofiler/config.json
```

## 常用流程

### 1. 导入歌曲

在“素材库”点击“导入文件”，可选择普通音频或 `.ncm` 文件。

导入 `.ncm` 时：

1. 应用在进程内解密；
2. 明文文件保存到 `workspace/imported/ncm/`；
3. 曲库记录保存原始 NCM 来源路径，同时后续处理使用明文文件。

暂时只支持 NCM 加密格式；QMC、KGM、KWM 等格式不会显示为可导入格式。

### 2. 分离人声和伴奏

在“去伴奏”页选择歌曲并创建任务。完成后：

- 人声和伴奏输出至 `workspace/demucs_output/`；
- 两条分离轨自动登记到曲库；
- 在素材库中，已分离歌曲会显示轨道数量；
- 可以在歌单中加入该歌曲的伴奏版本。

重复分离同一首歌时，旧的分离轨记录会被替换。

### 3. 设置默认歌单并快速添加

1. 打开“歌单管理”；
2. 选择一个歌单；
3. 点击“设为默认歌单”。

默认歌单会标记为 `★`。之后在素材库中右键歌曲，可以选择：

- 添加原曲到默认歌单；
- 添加伴奏到默认歌单（该歌曲必须已有已登记的 instrumental 分离轨）。

素材库底部会显示当前默认歌单的总时长。删除默认歌单时，该设置会自动清除。

### 4. 导出广播文件

在“导出”页选择歌单和输出参数后创建导出任务。导出会：

1. 读取歌单顺序；
2. 转码每一条原曲或伴奏；
3. 可选执行两遍 loudnorm 响度标准化；
4. 拼接输出到 `workspace/export/`。

输入音频若带有封面图片流，导出只处理第一条音频流，不会因损坏封面而失败。

## 工作区

默认工作区是项目目录下的 `workspace/`，也可以在配置文件中修改。

```text
workspace/
├── demucs_output/  # 人声和伴奏分离结果
├── export/         # 广播导出文件
├── imported/
│   └── ncm/        # NCM 解密后的持久音频
├── processed/      # 批量处理输出
└── temp/           # 临时转码和导出文件
```

## 测试

```bash
pytest -q
```

## 项目结构

```text
core/       # 数据模型、枚举、异常、国际化
ui/         # Tkinter 界面
services/   # 业务逻辑、任务调度与执行器
database/   # SQLite 仓储和迁移
tools/      # FFmpeg、FFprobe、Demucs、NCM 解密工具封装
tests/      # 自动化测试
```

依赖方向：

```text
UI → Services → Repository → SQLite
              → Tools
```
