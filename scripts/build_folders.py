#!/usr/bin/env python3
"""增量施工：按 plan_layout.py 的 preview，把 App 逐个文件夹归位。

纪律（本 skill 的核心）：
  - 一次 set_icon_state 只建/补一个文件夹；写前备份当步状态；
  - 写后等待 5 秒读回，内容级核验（该文件夹成员 == 预期、全局 bundleId 集合不变、
    Dock 不变、Widget 不变）；任一不过立即停，绝不整盘重写、绝不无变化重试；
  - 目标文件夹已存在则把成员并入（去重），不存在则新建。

用法:
  python3 build_folders.py --plan preview_YYYYMMDD_HHMMSS.json [--folders 社交媒体,AI工具] [--dry-run]
不带 --folders 时按 preview 里的全部分类依次施工（仍是一个文件夹一次写）。
preview 路径可为文件名（在 $ICONSTATE_DIR 下）或完整路径。
"""
import argparse, asyncio, glob, json, os
from common import (WORKDIR, connect, key_of, name_of, is_folder, find_app,
                    find_folder, remove_app, build_folder, folder_add, add_tile,
                    save_backup, save_json, ts_now, baseline_of, write_and_verify,
                    folder_map)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--folders", default=None, help="逗号分隔，只建这几个分类")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan_path = args.plan if os.path.exists(args.plan) else os.path.join(WORKDIR, args.plan)
    plan = json.load(open(plan_path))
    plan_folders = plan["folders"]
    want = args.folders.split(",") if args.folders else list(plan_folders.keys())

    _, svc = await connect("iconstate-build")
    try:
        metrics = await svc.get_homescreen_icon_metrics()
        page_cap = int(metrics.get("homeScreenIconColumns", 4)) * int(metrics.get("homeScreenIconRows", 6))
        fpage = int(metrics.get("homeScreenIconFolderColumns", 3)) * int(metrics.get("homeScreenIconFolderRows", 3))
    except Exception:
        page_cap, fpage = 24, 9

    state = await svc.get_icon_state("2")
    base_set, base_dock, base_widgets = baseline_of(state)
    save_backup(state, "pre_build")
    steps = []

    for cat in want:
        members = plan_folders.get(cat)
        if members is None:
            print(f"⏭️ preview 里没有分类「{cat}」，跳过")
            continue
        expect_bids = [m["bid"] for m in members]
        existing = find_folder(state, cat)
        existing_bids = [key_of(m) for r in existing.get("iconLists", []) for m in r] if existing else []
        to_move = [b for b in expect_bids if b not in existing_bids]
        print(f"\n=== 建/补「{cat}」：预期成员 {len(expect_bids)}，已有 {len(existing_bids)}，本次移动 {len(to_move)} ===")
        if args.dry_run:
            print("  dry-run，不写入")
            continue
        if not to_move and existing:
            print("  已齐全，跳过")
            steps.append({"folder": cat, "result": "已齐全跳过"})
            continue

        save_backup(state, f"pre_{cat}")
        if existing:
            for b in to_move:
                d = remove_app(state, b)
                if d is None:
                    print(f"  ⚠️ 找不到 {b}，跳过该成员")
                    continue
                folder_add(existing, d, fpage)
        else:
            dicts = []
            for b in to_move:
                d = remove_app(state, b)
                if d is None:
                    print(f"  ⚠️ 找不到 {b}，跳过该成员")
                    continue
                dicts.append(d)
            add_tile(state, build_folder(cat, dicts, fpage), page_cap)

        settled, ok, detail = await write_and_verify(svc, state, base_set, base_dock, base_widgets)
        got = folder_map(settled).get(cat, [])
        members_ok = set(got) == set(expect_bids)
        rec = {"folder": cat, "moved": len(to_move), "members_ok": members_ok,
               "global_ok": ok, "detail": detail}
        steps.append(rec)
        print(f"  读回：成员 {len(got)}，与预期一致={members_ok}，全局完整={ok}")
        if not (ok and members_ok):
            print(f"❌「{cat}」核验未通过，立即停止。设备当前状态已是最后一次读回结果，请人工检查后再继续。")
            save_json({"steps": steps}, f"build_report_{ts_now()}.json")
            return
        state = settled

    save_json({"steps": steps}, f"build_report_{ts_now()}.json")
    print("\n✅ 本轮施工完成，报告已存盘。建议接着跑 live_verify.py 做全量只读核查。")


if __name__ == "__main__":
    asyncio.run(main())
