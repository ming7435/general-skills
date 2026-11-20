# 导出与验收

在 Skill 根目录运行下列命令。第一个参数是编辑后的 HTML，第二个参数是本次交付的 PNG。脚本截取页面中的 `#poster`，等待字体和图片就绪，遇到缺失图片或已有同名输出时报告错误。

```sh
python -m pip install playwright
python -m playwright install chromium
python scripts/export_poster.py assets/system/layout.html poster.png
```

已有 Chrome 或 Edge 时可用 `--browser-path` 指向其可执行文件，跳过浏览器下载。使用 `--scale 2` 可将默认 941 × 1672 画布导出为 1882 × 3344。需要复用同一输出文件名时可加 `--overwrite`。若使用其他截图工具，按同样的画布边界导出。

## 交付前查看

- 在完整 PNG 中逐一核对主标题、栏目、节点、升级说明与时间。若修改仅针对卡片内的“决策”，检查系统名称中的“质量门”是否保留。
- 切换到小旗时按左至右阅读节点，在手机宽度查看编号是否压线，决策名称能否一眼对应。移动模块后检查相邻标题、卡片边框和底部光环有无相碰。
- 缩至约 375 像素宽查看主标题与节点，再以原尺寸检查细字、缺图和裁切。按用户要求把完整 PNG 直接展示在对话中。

## 回归验证

已安装上述依赖时运行 `python -m unittest discover -s tests -v`。使用本机浏览器执行测试时，用环境变量 `POSTER_BROWSER_PATH` 指定浏览器路径。
