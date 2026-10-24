#!/usr/bin/env python3
"""离线规划（不碰设备）：按 categories.json 把现有布局重排成目标布局并做硬校验。

输入：read_state.py 存的 raw_state_*.json + metrics_*.json（或用 --state/--metrics 指定）。
输出：preview_<ts>.json（分类结果、待裁定清单）与 target_state_<ts>.json（目标布局）。

硬校验（任一不过就报错，不产出目标布局）：
  - 写前 bundleId 集合 == 目标布局 bundleId 集合（零丢失零新增）
  - Dock 页逐项与原状态一致
  - Widget 节点逐项与原状态一致（bundleId 集合相等护不住 Widget，必须单独断言）

分类优先级：keep_loose > apps 精确映射 > keywords 关键词兜底 > unmatched（列出交用户裁定，
按“未分类”处理为保持松散，并在报告里显式列出，绝不自作主张塞进某个文件夹）。
"""
import argparse, json, os
from common import WORKDIR, key_of, name_of, is_folder, is_widget, save_json, ts_now


def load_latest(pattern):
    import glob
    files = sorted(glob.glob(os.path.join(WORKDIR, pattern)))
    if not files:
        raise SystemExit(f"❌ 在 {WORKDIR} 找不到 {pattern}，先跑 read_state.py")
    with open(files[-1]) as f:
        return json.load(f)


def classify(key, name, cfg):
    if key in cfg.get("keep_loose", []):
        return None
    apps = cfg.get("apps", {})
    if key in apps:
        return apps[key]
    t = (key + " " + (name or "")).lower()
    for cat, kws in cfg.get("keywords", {}).items():
        for k in kws:
            if k.lower() in t:
                return cat, True  # True = 关键词兜底，需人工核查
    return None, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=None)
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "categories.json"))
    args = ap.parse_args()

    state = json.load(open(args.state)) if args.state else load_latest("raw_state_*.json")
    metrics = {}
    if args.metrics:
        metrics = json.load(open(args.metrics))
    else:
        try:
            metrics = load_latest("metrics_*.json")
        except SystemExit:
            pass
    page_cap = int(metrics.get("homeScreenIconColumns", 4)) * int(metrics.get("homeScreenIconRows", 6))
    fpage = int(metrics.get("homeScreenIconFolderColumns", 3)) * int(metrics.get("homeScreenIconFolderRows", 3))

    if not os.path.exists(args.config):
        raise SystemExit(f"❌ 找不到分类配置 {args.config}，先把 categories.example.json 改名为 categories.json 并按自己的 App 修改")
    cfg = json.load(open(args.config))

    dock = state[0]
    categories, loose, unmatched, fallback_hits = {}, [], [], []
    orig_keys = set(key_of(i) for i in dock)
    widget_keys = []

    def visit(it, in_folder=False):
        if is_widget(it):
            widget_keys.append(key_of(it))
            orig_keys.add(key_of(it))
            loose.append(it)  # Widget 永远原样透传，保持松散
            return
        k, nm = key_of(it), name_of(it)
        orig_keys.add(k)
        r = classify(k, nm, cfg)
        if r is None:
            loose.append(it)
        elif isinstance(r, tuple):
            cat, via_kw = r
            if cat is None:
                loose.append(it)
                unmatched.append({"bid": k, "name": nm})
            else:
                categories.setdefault(cat, []).append(it)
                if via_kw:
                    fallback_hits.append({"bid": k, "name": nm, "category": cat})
        else:
            categories.setdefault(r, []).append(it)

    for page in state[1:]:
        for it in page:
            if is_folder(it):
                for row in it.get("iconLists", []):
                    for m in row:
                        visit(m, in_folder=True)
            else:
                visit(it)

    def clean(d):
        d = dict(d)
        d.pop("iconModDate", None)
        return d

    order = cfg.get("folder_order", [])
    cats_sorted = [c for c in order if c in categories] + [c for c in sorted(categories) if c not in order]
    folder_tiles = []
    for cat in cats_sorted:
        members = [clean(d) for d in categories[cat]]
        folder_tiles.append({"displayName": cat, "listType": "folder",
                             "iconLists": [members[s:s + fpage] for s in range(0, len(members), fpage)]})

    new_pages = [list(dock)]
    tiles = [clean(d) for d in loose] + folder_tiles
    for t in tiles:
        if len(new_pages) < 2 or len(new_pages[-1]) >= page_cap:
            new_pages.append([])
        new_pages[-1].append(t)

    # ---- 硬校验 ----
    new_keys = set()
    for p in new_pages:
        for it in p:
            if is_folder(it):
                for r in it.get("iconLists", []):
                    for m in r:
                        new_keys.add(key_of(m))
            else:
                new_keys.add(key_of(it))
    assert new_keys == orig_keys, f"❌ 集合不一致 缺失={orig_keys - new_keys} 多余={new_keys - orig_keys}"
    assert [key_of(i) for i in new_pages[0]] == [key_of(i) for i in dock], "❌ Dock 被改动"
    new_widgets = [key_of(it) for p in new_pages for it in p if is_widget(it)]
    assert new_widgets == widget_keys, "❌ Widget 节点被改动"

    print("✅ 校验通过：bundleId 集合一致、Dock 不变、Widget 不变")
    print(f"文件夹 {len(folder_tiles)} 个，松散 {len(loose)} 个（含 Widget {len(widget_keys)}）")
    for cat in cats_sorted:
        print(f"  📁 {cat} ({len(categories[cat])}): " + "、".join(name_of(d) for d in categories[cat]))
    if fallback_hits:
        print("\n⚠️ 关键词兜底分类（请逐个核对，错了就把 bundleId 写进 categories.json 的 apps 精确映射）：")
        for h in fallback_hits:
            print(f"   {h['name']} <{h['bid']}> -> {h['category']}")
    if unmatched:
        print("\n⚠️ 未能分类（保持松散，请裁定后补进配置）：")
        for u in unmatched:
            print(f"   {u['name']} <{u['bid']}>")

    ts = ts_now()
    save_json({"folders": {c: [{"bid": key_of(d), "name": name_of(d)} for d in categories[c]] for c in cats_sorted},
               "loose": [{"bid": key_of(d), "name": name_of(d)} for d in loose],
               "fallback_hits": fallback_hits, "unmatched": unmatched}, f"preview_{ts}.json")
    save_json(new_pages, f"target_state_{ts}.json")
    print(f"\n已存盘: preview_{ts}.json / target_state_{ts}.json（在 {WORKDIR}）")
    print("注意：target_state 只用于预览与核对。正式施工请用 build_folders.py 增量建夹，不要整盘写回。")


if __name__ == "__main__":
    main()
