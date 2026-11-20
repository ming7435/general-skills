#!/usr/bin/env python3
"""爆款文案长度与时长校验工具。

功能：
1. 统计文案各段（开头钩子/中间内容/结尾总结）的中文字数与预计时长
2. 与对标参数逐项比对，计算偏差，标出超出 ±5% 的项

用法：
    python length_check.py --file copy.txt
    python length_check.py --file copy.txt --benchmark '{"total":300,"hook":45,"body":210,"end":45,"duration":75}'
    python length_check.py --file copy.txt --rate 4.5 --benchmark '{"total":300,"duration":75}'

文案文件用标记分段：
    [开头钩子]
    ……
    [中间内容]
    ……
    [结尾总结]
    ……
未标记的内容计入总字数，但不计入任何分段。
"""

import argparse
import json
import re
import sys

SEGMENT_MARKERS = {
    "hook": "开头钩子",
    "body": "中间内容",
    "end": "结尾总结",
}


def count_chinese_chars(text: str) -> int:
    """统计中文字符数（标点、空白、emoji 不计入）。"""
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def parse_segments(text: str) -> dict:
    """按 [开头钩子]/[中间内容]/[结尾总结] 标记切分文案。"""
    result = {"hook": "", "body": "", "end": "", "unmarked": ""}
    # 标记行允许前后空白与全角/半角括号
    pattern = re.compile(r"^\s*[\[【]\s*(开头钩子|中间内容|结尾总结)\s*[\]】]\s*$")
    current = "unmarked"
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            label = m.group(1)
            current = next(k for k, v in SEGMENT_MARKERS.items() if v == label)
            continue
        result[current] += line + "\n"
    return result


def estimate_duration(chars: int, rate: float) -> float:
    """按语速估算时长（秒）。"""
    return round(chars / rate, 1) if rate > 0 else 0.0


def deviation(actual, target):
    """返回偏差百分比；目标为 0 或缺失时返回 None。"""
    if target in (None, 0, ""):
        return None
    return (actual - target) / target * 100


def fmt_dev(d):
    if d is None:
        return "—"
    sign = "+" if d >= 0 else ""
    flag = " ⚠" if abs(d) > 5 else ""
    return f"{sign}{d:.1f}%{flag}"


def build_rows(segments, rate, benchmark):
    counts = {k: count_chinese_chars(v) for k, v in segments.items()}
    total = counts["hook"] + counts["body"] + counts["end"] + counts["unmarked"]
    duration = estimate_duration(total, rate)

    rows = []
    checks = [
        ("总字数", "total", total),
        ("开头字数", "hook", counts["hook"]),
        ("中间字数", "body", counts["body"]),
        ("结尾字数", "end", counts["end"]),
        ("预计时长(秒)", "duration", duration),
    ]
    for label, key, actual in checks:
        target = benchmark.get(key) if benchmark else None
        dev = deviation(actual, target)
        rows.append((label, actual, target, dev))

    return rows, counts, total, duration


def print_report(rows, counts, total, duration, rate):
    print("=" * 60)
    print("爆款文案长度校验报告")
    print("=" * 60)
    print(f"分段字数：开头 {counts['hook']} / 中间 {counts['body']} / 结尾 {counts['end']}"
          + (f" / 未标记 {counts['unmarked']}" if counts["unmarked"] else ""))
    print(f"总字数：{total}　口播语速：{rate} 字/秒　预计时长：{duration} 秒")
    print()
    print(f"{'参数':<14}{'实际':>8}{'对标':>8}{'偏差':>12}")
    print("-" * 60)
    over = []
    for label, actual, target, dev in rows:
        t = "—" if target in (None, "") else (f"{target}" if not isinstance(target, float) else f"{target:g}")
        print(f"{label:<14}{actual:>8}{t:>8}{fmt_dev(dev):>12}")
        if dev is not None and abs(dev) > 5:
            over.append(label)
    print("-" * 60)
    if over:
        print("⚠ 以下项超出 ±5% 对标范围：" + "、".join(over))
        print("处理建议：精简或扩充对应段落，或调整布局，不要靠缩字号/压语速硬塞。")
    else:
        print("✅ 所有可比项均在 ±5% 对标范围内（未设对标的项不参与判定）。")


def main():
    parser = argparse.ArgumentParser(description="爆款文案字数与时长 ±5% 校验")
    parser.add_argument("--file", required=True, help="文案文件路径（含分段标记）")
    parser.add_argument("--benchmark", help="对标参数 JSON，如 '{\"total\":300,\"hook\":45,\"body\":210,\"end\":45,\"duration\":75}'")
    parser.add_argument("--rate", type=float, default=4.0, help="口播语速（字/秒），默认 4.0")
    args = parser.parse_args()

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"读取文件失败：{e}", file=sys.stderr)
        sys.exit(1)

    benchmark = {}
    if args.benchmark:
        try:
            benchmark = json.loads(args.benchmark)
        except json.JSONDecodeError as e:
            print(f"对标参数 JSON 解析失败：{e}", file=sys.stderr)
            sys.exit(1)

    segments = parse_segments(text)
    rows, counts, total, duration = build_rows(segments, args.rate, benchmark)
    print_report(rows, counts, total, duration, args.rate)

    # 存在超差项时以非零码退出，便于流水线拦截
    if any(d is not None and abs(d) > 5 for _, _, _, d in rows):
        sys.exit(2)


if __name__ == "__main__":
    main()
