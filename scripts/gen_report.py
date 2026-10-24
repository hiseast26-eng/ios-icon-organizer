#!/usr/bin/env python3
"""报告生成：把 live_verify 的结构化结论 (+ 可选的 build_report) 汇成一份 Markdown 报告。

用法:
  python3 gen_report.py --verify live_verify_YYYYMMDD_HHMMSS.json [--build build_report_YYYYMMDD_HHMMSS.json]
文件名可在 $ICONSTATE_DIR 下或写完整路径。产物: report_<ts>.md
"""
import argparse, json, os
from common import WORKDIR, save_json, ts_now


def resolve(p):
    return p if os.path.exists(p) else os.path.join(WORKDIR, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", required=True)
    ap.add_argument("--build", default=None)
    args = ap.parse_args()

    v = json.load(open(resolve(args.verify)))
    lines = ["# iPhone 主屏分类整理报告", ""]
    lines.append(f"- 生成时间：{ts_now()}")
    if v.get("device"):
        lines.append(f"- 设备：{v['device']} / iOS {v.get('ios', '?')}")
    lines.append(f"- 磁贴总数：{v['tile_total']}，去重 bundleId：{v['dedup_count']}")
    lines.append("")

    if args.build:
        b = json.load(open(resolve(args.build)))
        lines.append("## 施工步骤")
        for s in b.get("steps", []):
            lines.append(f"- 📁 {s.get('folder')}: {s}")
        lines.append("")

    lines.append("## 每页构成")
    for pb in v["page_breakdown"]:
        lines.append(f"- 页{pb['page']} [{pb['type']}]: 文件夹 {pb['folders']} / 松散 {pb['loose_apps']} / Widget {pb['widgets']} / 磁贴 {pb['tiles_on_page']}")
    lines.append("")
    lines.append("## 文件夹成员")
    for fn, members in v["folders"].items():
        lines.append(f"### 📁 {fn}（{len(members)}）")
        lines.append("、".join(n for n, _ in members))
        lines.append("")
    lines.append("## Dock")
    lines.append("、".join(n for n, _ in v["dock"]))
    lines.append("")
    lines.append("## 主屏松散 App（按裁定保留）")
    lines.append("、".join(n for n, _ in v["loose_homescreen"]) or "（无）")
    lines.append("")
    if v.get("dups"):
        lines.append("## 重复 bundleId（须确认是否为设备原有，勿擅自处理）")
        for b, c in v["dups"].items():
            lines.append(f"- {b} ×{c}")
        lines.append("")

    out = os.path.join(WORKDIR, f"report_{ts_now()}.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"✅ 报告已写入: {out}")


if __name__ == "__main__":
    main()
