# Audio Silence Trimmer

OpenCode Skill — 去除配音音频中字幕间的冗余静音，输出紧凑音频与重新对齐的 SRT 字幕文件。

## 背景

使用剪映完成 TTS 配音后，导出的 MP3 音频中每段语音之间会留下冗余的静音间隔（通常 1~2 秒）。手动逐段裁剪对齐非常繁琐，尤其是长视频。这个 Skill 自动完成整个流程：检测静音 → 裁掉冗余 → 输出紧凑音频 + 对齐字幕。

## 功能

- 自动检测音频中的静音区间
- 根据字幕时间窗口精确裁剪每段语音的首尾静音
- 两种输出模式可自由组合：整段 MP3 / 分段 WAV
- 每段音频末尾可配置停顿（默认 0.4s，让音频更像真人说话）
- 生成时间重映射的 SRT，字幕与音频时长精确匹配（误差 < 10ms）
- 字幕之间严丝合缝，导入剪映即可直接使用

## 依赖

- [ffmpeg](https://ffmpeg.org/) — 静音检测、音频裁剪、拼接
- Python 3.10+

## 使用

```bash
python scripts/trim_audio.py <input.mp3> <input.srt> [-o output_dir] [options]
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-o / --output` | `output` | 输出目录 |
| `-n / --noise` | `-30` | 静音阈值 (dB) |
| `-d / --min-silence` | `0.3` | 最短静音持续时间 (秒) |
| `-g / --gap` | `0.4` | 段间停顿时长 (秒)，设为 0 则无停顿 |
| `-m / --merged` | 开启 | 输出整段拼接 MP3 |
| `-s / --segments` | 关闭 | 输出分段 WAV |

### 示例

```bash
# 默认：整段 MP3，段间 0.4s 停顿
python scripts/trim_audio.py audio.mp3 subs.srt

# 仅分段 WAV
python scripts/trim_audio.py audio.mp3 subs.srt -s

# 两种都输出
python scripts/trim_audio.py audio.mp3 subs.srt -m -s

# 自定义停顿时长
python scripts/trim_audio.py audio.mp3 subs.srt -m -s -g 0.6
```

## 工作流程

1. **解析 SRT** — 提取每条字幕的时间窗口
2. **全轨静音检测** — 扫描音频找出所有静音区间
3. **计算语音边界** — 对每条字幕裁掉首尾冗余静音，得到精确语音区间
4. **输出音频** — 整段 MP3（concat 拼接）和/或分段 WAV，末尾补停顿
5. **生成新 SRT** — 字幕时长 = 音频时长，严丝合缝

## 输出

| 模式 | 文件 |
|------|------|
| 默认（`-m`） | `<name>_trimmed.mp3` + `<name>_trimmed.srt` |
| 分段（`-s`） | `segments/001.wav ~ NNN.wav` + `<name>_trimmed.srt` |
| 两者（`-m -s`） | MP3 + WAV + SRT |

## 调参建议

- 音频环境安静（录音棚）：`-n -40`
- 音频有底噪（环境音）：`-n -25`
- 语音中自然停顿较长：`-d 0.5`
- 语音中自然停顿较短：`-d 0.2`
- 不要停顿（紧密拼接）：`-g 0`
- 更长的呼吸间隔：`-g 0.6`

## License

MIT
