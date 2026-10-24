#!/usr/bin/env python3
"""阶段 0（只读）：连接 iPhone，拉取当前图标布局与网格参数，存盘并打印可读清单。

不执行任何写入。产物落在 $ICONSTATE_DIR（默认 ~/.iconstate）：
  raw_state_<ts>.json / metrics_<ts>.json / inventory_<ts>.json
"""
import asyncio, json
from common import (WORKDIR, connect, key_of, name_of, is_folder, is_widget,
                    save_json)


async def main():
    ld, svc = await connect("iconstate-read")
    state = await svc.get_icon_state("2")
    try:
        metrics = await svc.get_homescreen_icon_metrics()
    except Exception as e:
        metrics = {}
        print(f"⚠️ 网格参数读取失败（不影响布局读取）: {e}")
    dev = await ld.get_value(None, None)
    name = dev.get("DeviceName") if dev else "?"
    ios = dev.get("ProductVersion") if dev else "?"

    import common
    ts = common.ts_now()
    save_json(state, f"raw_state_{ts}.json")
    save_json(metrics, f"metrics_{ts}.json")

    print(f"设备: {name}  iOS: {ios}")
    print(f"总页数(含 Dock): {len(state)}")

    dock = state[0]
    print(f"\n[Dock] {len(dock)} 个:")
    for it in dock:
        print(f"   · {name_of(it)} <{key_of(it)}>")

    loose, folders, widgets = [], {}, []
    for page in state[1:]:
        for it in page:
            if is_folder(it):
                folders[it.get("displayName")] = [key_of(m) for r in it.get("iconLists", []) for m in r]
            elif is_widget(it):
                widgets.append((name_of(it), key_of(it)))
            else:
                loose.append((key_of(it), name_of(it)))

    print(f"\n[主屏松散 App] {len(loose)} 个:")
    for k, n in loose:
        print(f"   · {n} <{k}>")
    print(f"\n[Widget] {len(widgets)} 个:")
    for n, k in widgets:
        print(f"   · {n} <{k}>")
    print(f"\n[现有文件夹] {len(folders)} 个:")
    for fn, members in folders.items():
        print(f"   📁 {fn} ({len(members)})")

    all_keys = set()
    for p in state:
        for it in p:
            if is_folder(it):
                for r in it.get("iconLists", []):
                    for m in r:
                        all_keys.add(key_of(m))
            else:
                all_keys.add(key_of(it))
    save_json({"device": name, "ios": ios, "metrics": metrics,
               "dock": [(key_of(i), name_of(i)) for i in dock],
               "loose": loose, "widgets": widgets,
               "folders": folders, "all_keys": sorted(all_keys)},
              f"inventory_{ts}.json")
    print(f"\n全量去重 bundleId: {len(all_keys)}")
    print(f"已存盘到 {WORKDIR}（raw_state / metrics / inventory，时间戳 {ts}）")


if __name__ == "__main__":
    asyncio.run(main())
