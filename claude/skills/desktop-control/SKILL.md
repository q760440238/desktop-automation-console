---
name: desktop-control
description: 在 Windows 桌面上「看屏幕并动手」——截图理解界面、按坐标或控件点击、输入文字、发快捷键、启动应用、等待界面变化。当用户要求操作本机上的任意桌面程序（微信、QQ、Office、资源管理器、浏览器窗口、安装向导等），或需要 computer-use / 电脑操控能力时使用。
---

# Windows 桌面操控（computer use）

你通过 `windows-desktop` 这个 MCP 服务获得了一台真实 Windows 电脑的鼠标、键盘和屏幕。
把它当成「远程协助」：先看，再想，再动，动完再看一次。

## 工具地图

> 在 Claude Code 里这些工具的实际名字带 MCP 前缀：`mcp__windows-desktop__Snapshot`、
> `mcp__windows-desktop__Click`……下表用的是短名，按后缀对应即可。

| 目的 | 工具 | 关键参数 |
|---|---|---|
| 看屏幕 | `Snapshot` | `use_vision=true` 返回带标注的截图；`use_ui_tree=true` 返回控件树 |
| 找窗口/应用 | `App` | `mode="list"` 列出；`mode="open"` 启动 |
| 点击 | `Click` | `loc=[x,y]` 或 `label="控件名"`；`button="left/right"`、`clicks=2` 双击 |
| 输入 | `Type` | `text=...`，`clear=true` 先清空，`press_enter=true` 回车提交 |
| 快捷键 | `Shortcut` | `"ctrl+c"`、`"alt+f4"`、`"win+d"` |
| 滚动 | `Scroll` | `type="vertical"`、`direction="down"`、`wheel_times=3` |
| 拖拽 | `Move` | `drag=true`，`from_loc` → `loc` |
| 剪贴板 | `Clipboard` | `mode="set"/"get"`，**中文输入优先用这个** |
| 等待 | `Wait` / `WaitFor` | `duration=2`；`WaitFor(condition="text_visible", text="发送")` |
| 读网页 | `Scrape` | `url=...` |
| 进程 | `Process` | `mode="list"/"kill"` |

## 标准循环

1. **定位**：`App(mode="list")` 找目标窗口；必要时 `App(mode="open", name="...")`。
2. **观察**：`Snapshot(use_vision=true, use_annotation=true)`。优先用截图上的标注编号/控件名点击，
   而不是自己估坐标——估坐标在缩放、双屏、DPI 变化下必错。
3. **动作**：一次只做一个动作（一个点击 / 一段输入）。
4. **复核**：再 `Snapshot` 一次，确认界面真的变了。**没变化就是没成功**，不要假设成功。
5. **留证**：关键步骤把截图路径写进结论，方便用户回看。

## 中文与特殊字符

`Type` 对中文、emoji、长文本不可靠。固定做法：

```
Clipboard(mode="set", text="要输入的中文")
Shortcut("ctrl+v")
```

输入框里已有内容时，先 `Shortcut("ctrl+a")` 再粘贴，避免内容叠加。

## 安全规则（硬性）

- 删除文件、清空回收站、卸载软件、修改注册表、转账支付、发送消息给**第三方**：动手前必须向用户复述
  「即将对谁做什么」，得到明确同意才执行。
- 不要关掉用户没让你关的窗口；不要点广告、弹窗里的「立即升级」。
- 不要在登录界面替用户输密码；需要登录时停下来请用户自己完成。
- 涉及账号批量操作（加好友、群发、关注）时，改用 `social-automation` 技能，走它有审批和限流的那套流程，
  不要用裸鼠标键盘去刷。

## 排错

- **点不中**：先 `Snapshot(use_ui_tree=true)`，用控件名点；仍不行再 `DisplayInventory` 看 DPI 与显示器布局。
- **窗口被挡**：`App(mode="activate")` 或 `Shortcut("alt+tab")`。
- **动作太快**：每次动作后 `Wait(0.4~1)`；界面有动画就等 1.5 秒。
- **进程卡死**：`Process(mode="list")` 找到 PID，确认后再 `kill`。
