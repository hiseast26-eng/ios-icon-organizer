# ios-icon-organizer

**让 AI 帮你整理 iPhone 主屏：手机里几十上百个 App，不用你一个一个拖，它按用途分进文件夹。**

版本：1.0.0
许可：MIT（见文末）

## 这是什么

你的 iPhone 装了几十上百个 App，主屏翻五六页都找不到想用的那个——这个 skill 就是解决这件事的。

你告诉 AI 一声“帮我整理主屏”，它会：

1. **先给你的桌面拍个快照备份**，万一不满意随时能还原；
2. **把 App 按实际用途分进文件夹**，比如视频类进“影音娱乐”、银行类进“金融”、打车外卖进“出行”，而不是按名字瞎猜；
3. **一次只动一个文件夹，每动完一步都回头检查**：有没有 App 弄丢、底部的 Dock 和桌面小组件还在不在——有任何不对立刻停手，绝不整盘重写。

整理完，你的主屏从散落的五六页，变成一页按用途分好的文件夹，Dock 和小组件原封不动。

> 懂技术的话一句话：它通过 pymobiledevice3 直接读写 SpringBoard 图标布局（`get/set_icon_state`），协议级操作，不模拟点击、不拖拽。完整流程见 SKILL.md。

## 它解决什么问题

- 主屏 App 太多、翻页找不到：一次性按用途分进文件夹，并给出可复查的分类清单。
- 手动拖拽建夹慢且易错：一次一个文件夹，每步写后读回核验。
- 担心把桌面弄乱：施工前全量备份，任何一步失败立即停，Dock 与小组件有专门的保护。

## 实测范围

- 已实测：iPhone + iOS 27（icon state format 2），160+ App 全流程整理通过。
- iOS 26 及更早版本理论适用但未实测：脚本内置 B1 对调测试先行验证通道，不通过不施工。

## 环境要求

- macOS（需 USB 连接 iPhone / iPad），设备已信任此电脑
- Python 3.10+
- pymobiledevice3：`pip install pymobiledevice3`
- 施工时设备保持解锁，并在 `设置 → 显示与亮度 → 自动锁定` 设为「永不」

> ⚠️ 头号大坑：设备锁屏/熄屏时写入会被系统**静默忽略**（接口返回成功但布局不变）。本 skill 的全部流程都围绕「先验证通道、每步读回核验」设计，就是为了防这个坑。

## 快速上手

```bash
cd scripts
cp categories.example.json categories.json   # 按你自己的 App 修改分类配置

python3 read_state.py        # 阶段0：只读拉取当前布局并备份
python3 b1_swap.py           # B1：最小对调测试，验证写入通道（不通过先查锁屏）
python3 plan_layout.py       # 离线规划：生成分类预览 + 硬校验（不碰设备）
python3 build_folders.py --plan preview_时间戳.json          # 增量施工：一夹一写、读回核验
python3 live_verify.py       # 最终全量只读核查
python3 gen_report.py --verify live_verify_时间戳.json       # 生成 Markdown 报告
```

纠错/微调（单步移动，同样带核验）：

```bash
python3 move_apps.py --to 影音娱乐 --apps com.example.video
python3 move_apps.py --merge-from 旧文件夹 --to 新文件夹
```

所有备份与产物默认落在 `~/.iconstate/`，可用环境变量 `ICONSTATE_DIR` 修改。

## 安全与纪律（摘要，详见 SKILL.md）

- 单次写、等 5 秒、读回内容级核验；失败即停，绝不整盘重写、绝不无变化重试。
- 离线校验硬断言：bundleId 集合不变、Dock 不变、Widget 节点不变。
- 分类按真实功能，不凭名字/感觉；拿不准的 App 列清单交机主裁定。
- 操作他人设备前必须取得机主明确授权。

## 文件结构

```
ios-icon-organizer/
├── SKILL.md                  # 技能正文（流程、禁令、分类原则）
├── README.md
└── scripts/
    ├── common.py             # 公共库（结构操作/备份/写后核验）
    ├── read_state.py         # 只读拉取布局
    ├── b1_swap.py            # 通道验证（最小对调）
    ├── plan_layout.py        # 离线规划与硬校验
    ├── build_folders.py      # 增量施工
    ├── move_apps.py          # 单步移动/合并
    ├── live_verify.py        # 只读全量核查
    ├── gen_report.py         # 报告生成
    └── categories.example.json
```

## 免责声明

本工具直接修改设备的图标布局数据。使用前请务必完成阶段 0 备份；因使用不当造成的布局错乱，作者不承担责任。恢复方法：将任一 `backup_*.json` 的结构用 pymobiledevice3 写回即可还原。

## 作者

hello-seast

## License

MIT
