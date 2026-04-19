---
name: audio-silence-trimmer
description: 去除音频中 SRT 字幕条目之间的静音间隔，输出紧凑音频和重新对齐的 SRT 文件。当用户需要处理配音/TTS 音频与字幕对齐、去除语音片段间的冗余静音、或为视频编辑准备紧凑音频轨时触发此技能。适用于用户提供了音频文件(MP3)和对应 SRT 字幕文件的场景。
---

# Audio Silence Trimmer

去除音频中按 SRT 字幕分段界定的静音间隔，输出无冗余停顿的紧凑音频与时间重映射的 SRT。

## 典型场景

用户先用 TTS/配音生成了与 SRT 字幕对应的音频，但每段语音之间有冗余静音间隔，需要在导入剪映等编辑器前将音频紧凑化，使字幕与音频精确对齐。

## 依赖

- **ffmpeg** — 静音检测 (`silencedetect`)、音频裁剪 (`atrim`)、拼接 (`concat`)
- **Python 3.10+** — 脚本运行环境

## 使用方式

```bash
python scripts/trim_audio.py <input.mp3> <input.srt> [-o output_dir] [-n noise_dB] [-d min_silence_sec] [-s]
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input.mp3` | — | 输入音频文件路径 |
| `input.srt` | — | 输入 SRT 字幕文件路径 |
| `-o / --output` | `output` | 输出目录 |
| `-n / --noise` | `-30` | 静音阈值 (dB)，低于此值视为静音 |
| `-d / --min-silence` | `0.3` | 最短静音持续时间 (秒) |
| `-g / --gap` | `0.4` | 段间停顿时长 (秒)，设为 0 则无停顿 |
| `-m / --merged` | 开启 | 输出整段拼接 MP3 |
| `-s / --segments` | 关闭 | 输出分段 WAV（每条字幕一个文件） |

三个开关可自由组合，均不指定时默认仅输出整段 MP3。

### 示例

```bash
# 仅整段 MP3（默认，段间 0.4s 停顿）
python scripts/trim_audio.py audio.mp3 subs.srt

# 仅分段 WAV，停顿 0.6s
python scripts/trim_audio.py audio.mp3 subs.srt -s -g 0.6

# 两种都输出，无停顿（紧密拼接）
python scripts/trim_audio.py audio.mp3 subs.srt -m -s -g 0
```

## 工作流程

1. 解析 SRT 文件，获取每条字幕的起止时间范围
2. 对整段音频运行 `silencedetect`，检测所有静音区间
3. 对每条字幕，根据静音区间计算实际语音的起止时间（裁掉首尾静音）
4. 使用 `filter_complex` 将所有语音片段一次性拼接为紧凑音频（单次编码，仅一次 MP3 encoder delay）
5. 根据每段语音的理论时长生成时间戳首尾相接的新 SRT

## 输出

`-m` 和 `-s` 两个开关独立控制，可自由组合：

| 组合 | 效果 |
|------|------|
| （默认） | 仅 `<output_dir>/<音频文件名>_trimmed.mp3` + SRT |
| `-s` | 仅 `<output_dir>/segments/001.wav ~ NNN.wav` + SRT |
| `-m -s` | 整段 MP3 + 分段 WAV + SRT，三者同时输出 |

## 调参建议

- 音频环境安静（录音棚）：`-n -40`（更激进的静音检测）
- 音频有底噪（环境音）：`-n -25`（更保守）
- 语音中自然停顿较长：`-d 0.5`（避免把自然停顿当静音裁掉）
- 语音中自然停顿较短：`-d 0.2`（更精细的裁剪）
