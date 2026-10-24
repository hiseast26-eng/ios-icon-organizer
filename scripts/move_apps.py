#!/usr/bin/env python3
"""单步修正：把指定 App 移到目标文件夹（或移出为松散），一次写 + 读回核验。

分类纠错、文件夹合并后的补漏、边界 App 裁定后的归位，都用这个脚本，
不要再为每次修正写一次性脚本。

用法:
  python3 move_apps.py --to 影音娱乐 --apps com.example.a,com.example.b [--create]
  python3 move_apps.py --to-loose --apps com.example.a
  python3 move_apps.py --merge-from 旧文件夹 --to 新文件夹   # 整个文件夹并入另一个（源夹清空后自动消失需人工确认读回）

纪律同 build_folders.py：写前备份、单次写、5 秒读回、全局完整性校验、失败即停。
"""
import argparse, asyncio
from common import (connect, key_of, find_folder, remove_app, remove_folder,
                    folder_add, build_folder, add_tile, save_backup,
                    baseline_of, write_and_verify, folder_map)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default=None, help="目标文件夹名")
    ap.add_argument("--to-loose", action="store_true", help="移到主屏松散区")
    ap.add_argument("--apps", default=None, help="逗号分隔的 bundleId 列表")
    ap.add_argument("--merge-from", default=None, help="把该文件夹全部成员并入 --to 指定的文件夹")
    ap.add_argument("--create", action="store_true", help="目标文件夹不存在时新建")
    args = ap.parse_args()

    if not args.merge_from and not args.apps:
        raise SystemExit("❌ 需要 --apps 或 --merge-from")
    if not args.to_loose and not args.to:
        raise SystemExit("❌ 需要 --to 或 --to-loose")

    _, svc = await connect("iconstate-move")
    try:
        metrics = await svc.get_homescreen_icon_metrics()
        page_cap = int(metrics.get("homeScreenIconColumns", 4)) * int(metrics.get("homeScreenIconRows", 6))
        fpage = int(metrics.get("homeScreenIconFolderColumns", 3)) * int(metrics.get("homeScreenIconFolderRows", 3))
    except Exception:
        page_cap, fpage = 24, 9

    state = await svc.get_icon_state("2")
    base_set, base_dock, base_widgets = baseline_of(state)
    save_backup(state, "pre_move")

    if args.merge_from:
        src = find_folder(state, args.merge_from)
        if src is None:
            raise SystemExit(f"❌ 找不到源文件夹「{args.merge_from}」")
        bids = [key_of(m) for r in src.get("iconLists", []) for m in r]
    else:
        bids = [b.strip() for b in args.apps.split(",") if b.strip()]

    dicts = []
    for b in bids:
        d = remove_app(state, b)
        if d is None:
            raise SystemExit(f"❌ 找不到 App {b}，已中止（未写入）")
        dicts.append(d)

    if args.merge_from:
        remove_folder(state, args.merge_from)

    if args.to_loose:
        for d in dicts:
            add_tile(state, d, page_cap)
        target_desc = "松散区"
    else:
        target = find_folder(state, args.to)
        if target is None:
            if not args.create:
                raise SystemExit(f"❌ 目标文件夹「{args.to}」不存在，加 --create 才新建（未写入）")
            add_tile(state, build_folder(args.to, dicts, fpage), page_cap)
        else:
            for d in dicts:
                folder_add(target, d, fpage)
        target_desc = f"文件夹「{args.to}」"

    settled, ok, detail = await write_and_verify(svc, state, base_set, base_dock, base_widgets)
    if args.to_loose:
        loose_bids = {key_of(it) for p in settled[1:] for it in p if not isinstance(it, dict) or it.get("listType") != "folder"}
        landed = all(b in loose_bids for b in bids)
    else:
        landed = set(bids) <= set(folder_map(settled).get(args.to, []))
    print(f"移动 {len(bids)} 个 App -> {target_desc}：到位={landed}，全局完整={ok}")
    if not (ok and landed):
        print("❌ 核验未通过。不要重试同样的写入，先只读核查设备实际状态。")
    else:
        print("✅ 完成")


if __name__ == "__main__":
    asyncio.run(main())
