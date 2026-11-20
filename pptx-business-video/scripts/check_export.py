"""Decode the delivered video and report stream specs, subtitle bounds and near-black frames."""
import argparse
import json
import re
import subprocess
from fractions import Fraction
from pathlib import Path


def check_srt(path, duration):
    data = path.read_text(encoding="utf-8-sig").strip()
    fmt = r"(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})"
    previous = 0
    count = 0
    for count, block in enumerate(re.split(r"\n\s*\n", data), 1):
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError(f"Malformed SRT block {count}")
        match = re.fullmatch(fmt + r"\s+-->\s+" + fmt, lines[1].strip())
        if not match:
            raise ValueError(f"Invalid SRT timecode in block {count}")
        vals = [int(t) for t in match.groups()]
        def ms(h, m, s, frac):
            return ((h*60+m)*60+s)*1000+frac
        start, end = ms(*vals[:4]), ms(*vals[4:])
        if start < previous or end <= start or end > round(duration*1000)+1:
            raise ValueError(f"Overlapping or out-of-range SRT block {count}")
        previous = end
    return count


def run(args):
    proc = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace")
    if proc.returncode:
        raise RuntimeError(proc.stderr[-2200:])
    return proc


def audit(opt):
    meta = json.loads(run([opt.ffprobe, "-v", "error", "-show_streams", "-show_format",
                           "-show_chapters", "-of", "json", str(opt.video)]).stdout)
    v = next((s for s in meta["streams"] if s["codec_type"] == "video" and
              not s.get("disposition",{}).get("attached_pic")), None)
    a = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise ValueError("No video stream")
    rate = Fraction(v["avg_frame_rate"])
    if rate <= 0:
        raise ValueError("Video has no usable average frame rate")
    duration = float(v.get("duration") or meta["format"]["duration"])
    problems = []
    if v["codec_name"] != opt.video_codec or not a or a["codec_name"] != opt.audio_codec:
        problems.append("Unexpected video or audio codec, or missing audio")
    if opt.size and opt.size != f"{v['width']}x{v['height']}":
        problems.append("Frame dimensions differ from requested dimensions")
    if opt.fps and rate != Fraction(opt.fps):
        problems.append("Average fps differs from requested fps")
    if opt.duration is not None and abs(duration-opt.duration) > .001:
        problems.append("Video duration differs from target by more than 1 ms")
    command = [opt.ffmpeg, "-nostdin", "-hide_banner", "-nostats", "-xerror", "-i", str(opt.video),
               "-map", f"0:{v['index']}", "-vf", "scale=192:-2:flags=area,blackframe=amount=98:threshold=48"]
    if a:
        command += ["-map", f"0:{a['index']}", "-af", "volumedetect"]
    command += ["-vsync", "0", "-progress", "pipe:1", "-f", "null", "-"]
    decoded = run(command)
    counter = re.findall(r"^frame=(\d+)\s*$", decoded.stdout, re.M)
    if not counter:
        raise ValueError("No decoded frames reported")
    frames = int(counter[-1])
    if opt.fps and opt.duration is not None and frames != round(Fraction(opt.fps)*Fraction(str(opt.duration))):
        problems.append("Decoded frame count differs from the requested frame budget")
    ranges = []
    for match in re.finditer(r"\bframe:(\d+)\s+pblack:\d+\s+pts:\S+\s+t:([-\d.]+)",decoded.stderr):
        n, t = int(match[1]), float(match[2])
        if ranges and n == ranges[-1]["last_frame"]+1:
            ranges[-1].update(last_frame=n,last_s=t)
        else:
            ranges.append(dict(first_frame=n,last_frame=n,first_s=t,last_s=t))
    volume = re.findall(r"max_volume:\s+([-\w.]+) dB", decoded.stderr)
    audio_duration = float(a["duration"]) if a and a.get("duration") not in (None, "N/A") else None
    if audio_duration is not None and abs(duration-audio_duration) > max(.05, 1/float(rate)):
        problems.append("Video and audio stream lengths differ; inspect the tail")
    if volume and float(volume[-1]) <= -90:
        problems.append("Audio is at or below -90 dBFS throughout")
    captions = None
    if opt.srt:
        try:
            captions = check_srt(opt.srt,duration)
        except ValueError as exc:
            problems.append(str(exc))
    return dict(video=opt.video.name, video_codec=v["codec_name"], audio_codec=a["codec_name"] if a else None,
                size=[v["width"],v["height"]],average_fps=str(rate),duration_s=duration,audio_duration_s=audio_duration,
                decoded_frames=frames,chapter_count=len(meta.get("chapters",[])),srt_cues=captions,
                audio_peak_dbfs=volume[-1] if volume else None,near_black_ranges=ranges,problems=problems)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("video",type=Path)
    p.add_argument("--srt",type=Path)
    p.add_argument("--fps",help="Expected integer or rational frame rate")
    p.add_argument("--size",help="Expected WIDTHxHEIGHT")
    p.add_argument("--duration",type=float,help="Expected exact video duration in seconds")
    p.add_argument("--video-codec",default="h264")
    p.add_argument("--audio-codec",default="aac")
    p.add_argument("--ffmpeg",default="ffmpeg")
    p.add_argument("--ffprobe",default="ffprobe")
    args=p.parse_args()
    report=audit(args)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(1 if report["problems"] else 2 if report["near_black_ranges"] else 0)
