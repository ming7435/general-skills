"""Build one timeline, SRT and chapter markers from measured PCM WAV takes."""
import argparse
import json
import math
import tempfile
import wave
from fractions import Fraction
from pathlib import Path


def stamp(milliseconds):
    seconds, ms = divmod(milliseconds, 1000)
    mins, sec = divmod(seconds, 60)
    return f"{mins//60:02}:{mins%60:02}:{sec:02},{ms:03}"


def frame_count(value):
    if type(value) is not int or value < 0:
        raise ValueError(f"Expected non-negative integer frames, got {value!r}")
    return value


def build(manifest, output, fps, target=None):
    if fps <= 0:
        raise ValueError("fps must be positive")
    spec = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(spec, list) or not spec:
        raise ValueError("Expected a non-empty array of takes")
    clips, captions, chapters = [], [], []
    ids = set()
    cursor = 0
    for row in spec:
        key = row["id"]
        if not key or key in ids:
            raise ValueError(f"Missing or duplicate id: {key!r}")
        ids.add(key)
        with wave.open(str(manifest.parent / row["wav"]), "rb") as audio:
            seconds = Fraction(audio.getnframes(), audio.getframerate())
        if seconds <= 0:
            raise ValueError(f"Empty voice clip: {key}")
        voice_frame = cursor + frame_count(row.get("pre_frames", 0))
        end_frame = voice_frame + math.ceil(seconds * fps) + frame_count(row.get("post_frames", 0))
        cues = row.get("cues")
        if cues is None:
            cues = [dict(start=0, end=seconds, text=row["text"])]
        if not cues:
            raise ValueError(f"Provide captions or text for {key}")
        last = Fraction(0)
        for c in cues:
            a, b = Fraction(str(c["start"])), Fraction(str(c["end"]))
            # A subtitle file ordinarily rounds a measured endpoint to milliseconds.
            if seconds < b <= seconds + Fraction(1, 1000):
                b = seconds
            text = c["text"].strip()
            if not text or not last <= a < b <= seconds:
                raise ValueError(f"Invalid cue in {key}: {c}")
            origin = Fraction(voice_frame, fps)
            start_ms, end_ms = round((origin+a)*1000), round((origin+b)*1000)
            if start_ms >= end_ms:
                raise ValueError(f"Sub-millisecond cue in {key}")
            captions.append((start_ms, end_ms, text))
            last = b
        chapter = row.get("chapter", "").strip()
        if chapter and (not chapters or chapter != chapters[-1]["title"]):
            chapters.append(dict(title=chapter, start_frame=cursor))
        clips.append(dict(id=key, wav=row["wav"], start_frame=cursor, voice_frame=voice_frame,
                          voice_seconds=float(seconds), end_frame=end_frame))
        cursor = end_frame
    if target is not None:
        if target < cursor:
            raise ValueError(f"Audio and holds need {cursor} frames, {cursor-target} over the {target}-frame budget. Shorten the script or revise holds.")
        clips[-1]["end_frame"] = cursor = target
    if output.exists():
        raise ValueError(f"Output exists: {output}. Choose a new directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "timeline"
        stage.mkdir()
        data = dict(fps=fps, frames=cursor, duration=cursor/fps, clips=clips, chapters=chapters)
        (stage / "timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        srt = "\n\n".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{txt}" for i,(a,b,txt) in enumerate(captions,1))
        (stage / "captions.srt").write_text(srt + "\n", encoding="utf-8-sig")
        meta = [";FFMETADATA1"]
        for i, ch in enumerate(chapters):
            end = chapters[i+1]["start_frame"] if i+1 < len(chapters) else cursor
            name = " ".join(ch["title"].splitlines())
            for char in ("\\", "=", ";", "#"):
                name = name.replace(char, "\\" + char)
            meta.extend(["[CHAPTER]", f"TIMEBASE=1/{fps}", f"START={ch['start_frame']}", f"END={end}", "title="+name])
        (stage / "chapters.ffmeta").write_text("\n".join(meta)+"\n", encoding="utf-8")
        stage.rename(output)
    print(f"{cursor} frames, {cursor/fps:.3f}s, {len(captions)} captions")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest",type=Path)
    p.add_argument("out",type=Path)
    p.add_argument("--fps",type=int,default=30)
    p.add_argument("--target-frames",type=int)
    a=p.parse_args()
    build(a.manifest,a.out,a.fps,a.target_frames)
