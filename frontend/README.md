# 前端界面

前端现在按用途拆成两个独立版本：

- `personal/`：个人版，保留番茄发布、番茄同步、小说处理、网页抓取、角色素材、当前剧情。
- `release/`：发布版，只保留番茄发布、番茄同步。

默认启动和打包都使用发布版：

```bash
python main.py
python tools/build_exe.py --frontend release
```

需要本地打开个人版时，可以设置环境变量：

```bash
FANQIE_FRONTEND_VARIANT=personal python main.py
```
