#!/usr/bin/env python3
"""只读全量核查：拉取设备真实布局（或离线读已存结构），精确统计并输出结构化结论。

严禁任何 set_icon_state 写入。

用法:
  python3 live_verify.py                              # 在线读设备
  python3 live_verify.py --from-file raw_state_X.json # 离线读已存结构
  python3 live_verify.py --expect-tiles 200 --expect-dedup 198   # 可选：与预期数字核对

统计口径：
  - 磁贴总数 = Dock + 主屏松散 App + Widget + 全部文件夹成员
  - 去重数以 bundleId 集合计；重复 bundleId 会被单列（有些是设备原有的，不要擅自“修复”）
  - page_breakdown 里文件夹 / 松散 App / Widget 分列计数
"""
import argparse, asyncio, datetime, json, os
from collections import Counter
from common import WORKDIR, key_of, name_of, is_folder, is_widget, save_json, ts_now


def analyze(state):
    page_breakdown, dock, loose, widgets, folders, all_tiles = [], [], [], [], {}, []
    for pi, page in enumerate(state):
        fcount = lcount = wcount = 0
        for it in page:
            if is_folder(it):
                fcount += 1
                members = [(name_of(m), key_of(m)) for r in it.get("iconLists", []) for m in r]
                folders[it.get("displayName")] = members
                all_tiles.extend(members)
            elif is_widget(it):
                wcount += 1
                widgets.append((name_of(it), key_of(it)))
                all_tiles.append((name_of(it), key_of(it)))
            else:
                if pi == 0:
                    dock.append((name_of(it), key_of(it)))
                else:
                    lcount += 1
                    loose.append((name_of(it), key_of(it)))
                all_tiles.append((name_of(it), key_of(it)))
        page_breakdown.append({"page": pi, "type": "Dock" if pi == 0 else f"主屏页{pi}",
                               "folders": fcount, "loose_apps": lcount, "widgets": wcount,
                               "tiles_on_page": len(page)})
    bids = [b for _, b in all_tiles]
    return {
        "pages_total": len(state), "page_breakdown": page_breakdown,
        "dock": dock, "loose_homescreen": loose, "widgets": widgets,
        "folders": folders,
        "folder_member_total": sum(len(v) for v in folders.values()),
        "tile_total": len(all_tiles), "dedup_count": len(set(bids)),
        "dups": {b: c for b, c in Counter(bids).items() if c > 1},
    }


def print_report(rep, expect_tiles=None, expect_dedup=None):
    print("\n===== 只读核查结论 =====")
    print(f"总页数(含 Dock): {rep['pages_total']}")
    for pb in rep["page_breakdown"]:
        print(f"  页{pb['page']} [{pb['type']}]: 文件夹 {pb['folders']}，松散 App {pb['loose_apps']}，Widget {pb['widgets']}，本页磁贴 {pb['tiles_on_page']}")
    print(f"\nDock ({len(rep['dock'])}): " + "、".join(n for n, _ in rep["dock"]))
    print(f"主屏松散 ({len(rep['loose_homescreen'])}): " + "、".join(n for n, _ in rep["loose_homescreen"]))
    print(f"Widget ({len(rep['widgets'])}): " + "、".join(n for n, _ in rep["widgets"]))
    print(f"\n文件夹 ({len(rep['folders'])}):")
    for fn, members in rep["folders"].items():
        print(f"  📁 {fn} ({len(members)}): " + "、".join(n for n, _ in members))
    print(f"\n文件夹成员合计: {rep['folder_member_total']}")
    print(f"磁贴总数: {rep['tile_total']}（Dock {len(rep['dock'])} + 松散 {len(rep['loose_homescreen'])} + Widget {len(rep['widgets'])} + 成员 {rep['folder_member_total']}）")
    print(f"去重 bundleId: {rep['dedup_count']}")
    print(f"重复 bundleId: {rep['dups'] or '无'}")
    if expect_tiles is not None:
        print(f"与预期磁贴数 {expect_tiles} 的差额: {rep['tile_total'] - expect_tiles}")
    if expect_dedup is not None:
        print(f"与预期去重数 {expect_dedup} 的差额: {rep['dedup_count'] - expect_dedup}")


async def run_online(expect_tiles, expect_dedup):
    from common import connect
    ld, svc = await connect("iconstate-verify")
    dev = await ld.get_value(None, None)
    state = await svc.get_icon_state("2")
    ts = ts_now()
    save_json(state, f"raw_state_{ts}.json")
    rep = analyze(state)
    rep["device"] = dev.get("DeviceName") if dev else None
    rep["ios"] = dev.get("ProductVersion") if dev else None
    rep["generated"] = datetime.datetime.now().isoformat()
    print_report(rep, expect_tiles, expect_dedup)
    p = save_json(rep, f"live_verify_{ts}.json")
    print(f"\n结构化结论已存: {p}")


def run_offline(path, expect_tiles, expect_dedup):
    state = json.load(open(path))
    rep = analyze(state)
    rep["generated"] = datetime.datetime.now().isoformat()
    rep["source"] = f"offline: {path}"
    print_report(rep, expect_tiles, expect_dedup)
    p = save_json(rep, f"live_verify_{ts_now()}.json")
    print(f"\n结构化结论已存: {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file", default=None)
    ap.add_argument("--expect-tiles", type=int, default=None)
    ap.add_argument("--expect-dedup", type=int, default=None)
    args = ap.parse_args()
    if args.from_file:
        run_offline(args.from_file, args.expect_tiles, args.expect_dedup)
    else:
        asyncio.run(run_online(args.expect_tiles, args.expect_dedup))
