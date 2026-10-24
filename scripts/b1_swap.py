#!/usr/bin/env python3
"""B1 最小对调测试：验证写入通道是否真的生效（任何正式施工前必跑）。

把某一主屏页上前两个松散 App 交换位置，单次写入，等待 5 秒读回比对。
- 读回 == 预期：通道可用，可以继续。
- 读回 == 写前：写入被静默忽略 —— 绝大多数情况是设备锁屏/熄屏，
  先解锁并关闭「自动锁定」，不要猜测协议不兼容。

用法: python3 b1_swap.py [--page N]   # 默认自动挑第一个有 ≥2 个松散 App 的主屏页
对调只是位置互换，之后随分类施工归位即可；也可再跑一次换回来。
"""
import argparse, asyncio, copy
from common import (connect, key_of, name_of, is_app, state_fingerprint,
                    save_backup, save_json, ts_now)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, default=None, help="主屏页序号（1 起，1 = 第一主屏页）")
    args = ap.parse_args()

    _, svc = await connect("iconstate-b1")
    before = await svc.get_icon_state("2")
    save_backup(before, "pre_b1")

    idx = args.page
    if idx is None:
        for i in range(1, len(before)):
            if sum(1 for it in before[i] if is_app(it)) >= 2:
                idx = i
                break
    if idx is None or idx < 1 or idx >= len(before):
        print("❌ 找不到有 ≥2 个松散 App 的主屏页，中止")
        return
    page = before[idx]
    apps = [it for it in page if is_app(it)]
    if len(apps) < 2:
        print(f"❌ 页 {idx} 松散 App 不足 2 个，中止")
        return

    a, b = apps[0], apps[1]
    ia, ib = page.index(a), page.index(b)
    after = copy.deepcopy(before)
    after[idx][ia], after[idx][ib] = after[idx][ib], after[idx][ia]

    hb, ha = state_fingerprint(before), state_fingerprint(after)
    print(f"对调: 页{idx} 位置{ia}({name_of(a)}) <-> 位置{ib}({name_of(b)})")

    await svc.set_icon_state(after)
    await asyncio.sleep(5)
    settled = await svc.get_icon_state("2")
    hs = state_fingerprint(settled)

    def order(s):
        return [(name_of(it), key_of(it)) for it in s[idx]]
    so, ao, bo = order(settled), order(after), order(before)
    if so == ao:
        conclusion = "✅ B1 通过：写入真实生效，通道可用。"
    elif so == bo:
        conclusion = "❌ B1 未生效：读回与写前一致，写入被静默忽略。多半是设备锁屏/熄屏——请解锁、关闭自动锁定、停在主屏后重试，不要猜协议问题。"
    else:
        conclusion = "⚠️ B1 异常：读回既非写前也非预期，需人工排查，不要继续施工。"
    print(conclusion)
    save_json({"ts": ts_now(), "stage": "B1", "page": idx,
               "swap": [{"name": name_of(a), "bid": key_of(a)}, {"name": name_of(b), "bid": key_of(b)}],
               "hash_before": hb, "hash_expected": ha, "hash_settled": hs,
               "conclusion": conclusion}, f"b1_report_{ts_now()}.json")


if __name__ == "__main__":
    asyncio.run(main())
