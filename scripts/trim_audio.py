#!/usr/bin/env python3
"""
trim_audio.py — 按 SRT 切分音频、去除静音、输出整段紧凑音频 + 重映射 SRT
"""

import subprocess
import sys
import re
import argparse
from pathlib import Path

TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def time_to_seconds(s: str) -> float:
    m = TIME_RE.match(s)
    if not m:
        return 0.0
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000


def seconds_to_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = round((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    pat = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"
        r"(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    entries = []
    for m in pat.finditer(content):
        entries.append(
            {
                "index": int(m[1]),
                "start": time_to_seconds(m[2]),
                "end": time_to_seconds(m[3]),
                "text": m[4].strip(),
            }
        )
    return entries


def detect_silences(audio_path: str, noise_db: float = -30, min_duration: float = 0.3) -> list[tuple]:
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    output = r.stderr  # silencedetect writes to stderr, not stdout

    starts: list[float] = []
    ends: list[float] = []
    for line in output.split("\n"):
        if m := re.search(r"silence_start:\s*([\d.]+)", line):
            starts.append(float(m[1]))
        elif m := re.search(r"silence_end:\s*([\d.]+)", line):
            ends.append(float(m[1]))

    return list(zip(starts, ends[: len(starts)]))


def compute_bounds(entry: dict, silences: list[tuple]) -> tuple[float, float]:
    es, ee = entry["start"], entry["end"]
    overlap = [(max(s, es), min(e, ee)) for s, e in silences if s < ee and e > es]

    if not overlap:
        return es, ee

    speech_start = overlap[0][1] if overlap[0][0] <= es + 0.15 else es
    speech_end = overlap[-1][0] if overlap[-1][1] >= ee - 0.15 else ee

    if speech_end - speech_start < 0.2:
        return es, ee

    return speech_start, speech_end


def generate_srt(entries: list[dict], durations: list[float], path: str, gap: float = 0.0):
    with open(path, "w", encoding="utf-8") as f:
        t = 0.0
        for i, e in enumerate(entries):
            d = durations[i]
            display = d + gap if gap > 0 else d
            f.write(f"{i + 1}\n")
            f.write(f"{seconds_to_time(t)} --> {seconds_to_time(t + display)}\n")
            f.write(f"{e['text']}\n\n")
            t += display


def build_concat_filter(bounds: list[tuple], gap: float = 0.0) -> str:
    parts = []
    for i, (start, end) in enumerate(bounds):
        filter_str = f"[0:a]atrim={start:.6f}:{end:.6f},asetpts=PTS-STARTPTS"
        if gap > 0:
            filter_str += f",apad=pad_dur={gap:.3f}"
        parts.append(f"{filter_str}[s{i}]")
    labels = "".join(f"[s{i}]" for i in range(len(bounds)))
    parts.append(f"{labels}concat=n={len(bounds)}:v=0:a=1[out]")
    return ";".join(parts)


def export_merged(audio_path: str, bounds: list[tuple], output_path: str, gap: float = 0.0):
    filter_complex = build_concat_filter(bounds, gap)
    subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path,
         "-filter_complex", filter_complex,
         "-map", "[out]",
         "-c:a", "libmp3lame", "-q:a", "2",
         str(output_path)],
        capture_output=True,
    )


def export_segments(audio_path: str, bounds: list[tuple], segments_dir: Path, gap: float = 0.0):
    segments_dir.mkdir(parents=True, exist_ok=True)
    for i, (ss, se) in enumerate(bounds):
        seg_path = segments_dir / f"{i + 1:03d}.wav"
        dur = se - ss
        if gap > 0:
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", audio_path,
                 "-af", f"atrim={ss:.6f}:{se:.6f},apad=pad_dur={gap:.3f}",
                 str(seg_path)],
                capture_output=True,
            )
        else:
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", audio_path,
                 "-af", f"atrim={ss:.6f}:{se:.6f}",
                 str(seg_path)],
                capture_output=True,
            )


def main():
    parser = argparse.ArgumentParser(
        description="去除音频静音间隔，输出紧凑音频 + 对齐的 SRT"
    )
    parser.add_argument("audio", help="输入 MP3 文件路径")
    parser.add_argument("srt", help="输入 SRT 文件路径")
    parser.add_argument("-o", "--output", default="output", help="输出目录 (默认: output)")
    parser.add_argument("-n", "--noise", type=float, default=-30,
                        help="静音阈值 dB (默认: -30)")
    parser.add_argument("-d", "--min-silence", type=float, default=0.3,
                        help="最短静音持续时间秒数 (默认: 0.3)")
    parser.add_argument("-g", "--gap", type=float, default=0.4,
                        help="段间停顿时长秒数 (默认: 0.4，设为 0 则无停顿)")
    parser.add_argument("-m", "--merged", action="store_true",
                        help="输出整段拼接 MP3（默认开启，加 --no-merged 关闭）")
    parser.add_argument("-s", "--segments", action="store_true",
                        help="输出分段 WAV（每条字幕一个文件）")
    args = parser.parse_args()

    do_merged = args.merged
    do_segments = args.segments
    if not do_merged and not do_segments:
        do_merged = True

    if not Path(args.audio).exists():
        print(f"错误: 找不到音频文件 {args.audio}")
        sys.exit(1)
    if not Path(args.srt).exists():
        print(f"错误: 找不到 SRT 文件 {args.srt}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = parse_srt(args.srt)
    if not entries:
        print("错误: SRT 文件为空或格式无法识别")
        sys.exit(1)
    print(f"解析到 {len(entries)} 条字幕")
    modes = []
    if do_merged:
        modes.append("整段 MP3")
    if do_segments:
        modes.append("分段 WAV")
    print(f"输出模式: {' + '.join(modes)}")
    if args.gap > 0:
        print(f"段间停顿: {args.gap}s")

    print(f"正在检测静音 (阈值: {args.noise}dB, 最短: {args.min_silence}s)...")
    silences = detect_silences(args.audio, args.noise, args.min_silence)
    print(f"检测到 {len(silences)} 段静音")

    bounds = []
    durations = []
    trimmed_count = 0
    for i, e in enumerate(entries):
        ss, se = compute_bounds(e, silences)
        bounds.append((ss, se))
        dur = se - ss
        durations.append(dur)
        if dur < e["end"] - e["start"] - 0.1:
            trimmed_count += 1

    print(f"裁剪 {trimmed_count}/{len(entries)} 段静音")

    srt_out = output_dir / (Path(args.srt).stem + "_trimmed.srt")

    if do_merged:
        audio_out = output_dir / (Path(args.audio).stem + "_trimmed.mp3")
        print("正在生成紧凑音频...")
        export_merged(args.audio, bounds, audio_out, args.gap)
    if do_segments:
        segments_dir = output_dir / "segments"
        print(f"正在导出 {len(entries)} 个分段音频到 {segments_dir} ...")
        export_segments(args.audio, bounds, segments_dir, args.gap)

    generate_srt(entries, durations, str(srt_out), args.gap)

    total_orig = sum(e["end"] - e["start"] for e in entries)
    total_trim = sum(durations)
    total_gap = args.gap * len(entries) if args.gap > 0 else 0
    saved = total_orig - total_trim

    print(f"\n{'='*50}")
    print(f"原始总时长: {seconds_to_time(total_orig)} ({total_orig:.1f}s)")
    print(f"语音时长:   {seconds_to_time(total_trim)} ({total_trim:.1f}s)")
    print(f"裁掉静音:   {seconds_to_time(saved)} ({saved:.1f}s)")
    if args.gap > 0:
        print(f"段间停顿:   {len(entries)} x {args.gap}s = {total_gap:.1f}s")
        print(f"最终总时长: {seconds_to_time(total_trim + total_gap)} ({total_trim + total_gap:.1f}s)")
    print(f"新 SRT:    {srt_out}")
    if do_merged:
        print(f"紧凑音频:  {output_dir / (Path(args.audio).stem + '_trimmed.mp3')}")
    if do_segments:
        print(f"分段音频:  {output_dir / 'segments'}/ (001.wav ~ {len(entries):03d}.wav)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
