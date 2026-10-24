#!/usr/bin/env python3
"""公共 helpers：icon state 结构操作、备份、指纹、连接。

所有脚本共用。icon state 为 format 2 结构：
state[0] 是 Dock 页，其余是主屏页；每页是扁平 tile 列表，
tile 或为 App 字典、或为文件夹字典（listType == "folder"）、或为 Widget 节点。
"""
import asyncio, copy, datetime, hashlib, json, os

WORKDIR = os.path.expanduser(os.environ.get("ICONSTATE_DIR", "~/.iconstate"))
FORMAT = "2"


def ts_now():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def key_of(a):
    if not isinstance(a, dict):
        return None
    return a.get("bundleIdentifier") or a.get("displayIdentifier")


def name_of(a):
    return a.get("displayName") or key_of(a)


def is_folder(it):
    return isinstance(it, dict) and it.get("listType") == "folder"


def is_widget(it):
    return isinstance(it, dict) and (it.get("elementType") == "widget" or "widgetIdentifier" in it)


def is_app(it):
    return isinstance(it, dict) and not is_folder(it) and not is_widget(it)


def clean(d):
    """写回前去掉图标缓存字段，避免格式问题（实测安全）。"""
    d = dict(d)
    d.pop("iconModDate", None)
    return d


def bundle_set(state):
    s = set()
    for p in state:
        for it in p:
            if is_folder(it):
                for r in it.get("iconLists", []):
                    for m in r:
                        s.add(key_of(m))
            else:
                s.add(key_of(it))
    return s


def folder_map(state):
    """文件夹名 -> 成员 bundleId 列表"""
    out = {}
    for p in state:
        for it in p:
            if is_folder(it):
                out[it.get("displayName")] = [key_of(m) for r in it.get("iconLists", []) for m in r]
    return out


def widget_nodes(state):
    return [it for p in state for it in p if is_widget(it)]


def dock_bids(state):
    return [key_of(i) for i in state[0]]


def state_fingerprint(state):
    h = hashlib.sha256()
    for p in state:
        for it in p:
            if is_folder(it):
                h.update(b"F" + (it.get("displayName") or "").encode())
                for r in it.get("iconLists", []):
                    for m in r:
                        h.update((key_of(m) or "?").encode() + b",")
            else:
                h.update((key_of(it) or name_of(it) or "?").encode() + b";")
    return h.hexdigest()


def find_app(state, bid):
    for p in state:
        for it in p:
            if is_folder(it):
                for r in it.get("iconLists", []):
                    for m in r:
                        if key_of(m) == bid:
                            return m
            elif key_of(it) == bid:
                return it
    return None


def find_folder(state, name):
    for p in state:
        for it in p:
            if is_folder(it) and it.get("displayName") == name:
                return it
    return None


def remove_app(state, bid):
    """从任意位置（文件夹内或松散）摘出一个 App 字典并返回；文件夹空页自动剔除。"""
    for p in state:
        for it in p:
            if is_folder(it):
                for r in it.get("iconLists", []):
                    for m in r:
                        if key_of(m) == bid:
                            r.remove(m)
                            it["iconLists"] = [pg for pg in it["iconLists"] if pg]
                            return m
            elif key_of(it) == bid:
                p.remove(it)
                return it
    return None


def remove_folder(state, name):
    for p in state:
        for i, it in enumerate(p):
            if is_folder(it) and it.get("displayName") == name:
                return p.pop(i)
    return None


def folder_add(folder, app_dict, folder_page_size=9):
    members = [m for r in folder.get("iconLists", []) for m in r]
    members.append(clean(app_dict))
    folder["iconLists"] = [members[s:s + folder_page_size] for s in range(0, len(members), folder_page_size)]


def build_folder(name, member_dicts, folder_page_size=9):
    members = [clean(d) for d in member_dicts]
    pages = [members[s:s + folder_page_size] for s in range(0, len(members), folder_page_size)]
    return {"displayName": name, "listType": "folder", "iconLists": pages}


def add_tile(state, tile, page_capacity=24):
    """把一个顶层 tile 放到最后一页（满了就新开一页）。绝不放进 Dock 页（state[0]）。"""
    if len(state) < 2:
        state.append([])
    last = state[-1]
    if len(last) < page_capacity:
        last.append(tile)
    else:
        state.append([tile])


def save_backup(state, tag):
    os.makedirs(WORKDIR, exist_ok=True)
    path = os.path.join(WORKDIR, f"backup_{tag}_{ts_now()}.json")
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, default=str)
    return path


def save_json(obj, name):
    os.makedirs(WORKDIR, exist_ok=True)
    path = os.path.join(WORKDIR, name)
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    return path


async def connect(label="icon-organizer"):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.springboard import SpringBoardServicesService
    ld = await create_using_usbmux(label=label)
    return ld, SpringBoardServicesService(ld)


async def write_and_verify(svc, new_state, base_set, base_dock, base_widgets):
    """单次写入 + 等待 5 秒 + 读回，校验全局完整性。返回 (settled_state, ok, detail)。

    硬校验：bundleId 集合不变、Dock 顺序不变、Widget 节点集合不变。
    注意：set_icon_state 返回成功 != 生效（锁屏时会静默 no-op），只认读回结果。
    """
    # 写前离线断言
    assert bundle_set(new_state) == base_set, "离线校验失败：bundleId 集合发生变化，禁止写入"
    assert dock_bids(new_state) == base_dock, "离线校验失败：Dock 被改动，禁止写入"
    assert widget_nodes(new_state) == base_widgets, "离线校验失败：Widget 节点被改动，禁止写入"

    await svc.set_icon_state(new_state)
    await asyncio.sleep(5)
    settled = await svc.get_icon_state(FORMAT)
    ok = (
        bundle_set(settled) == base_set
        and dock_bids(settled) == base_dock
        and widget_nodes(settled) == base_widgets
    )
    detail = {
        "bundle_intact": bundle_set(settled) == base_set,
        "dock_intact": dock_bids(settled) == base_dock,
        "widget_intact": widget_nodes(settled) == base_widgets,
        "settled_fingerprint": state_fingerprint(settled),
    }
    return settled, ok, detail


def baseline_of(state):
    return bundle_set(state), dock_bids(state), widget_nodes(state)
