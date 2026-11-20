# 工具与导出说明

| 当前能力 | 可以交付什么 | 如何确认 |
| --- | --- | --- |
| 本地 Codex，能运行 Python、Playwright 和 Chromium 系浏览器 | 编辑 HTML 母版，导出完整 PNG | 在工作副本上执行下方命令并打开结果。本库的本地回归测试覆盖两种流程排法。 |
| 能在浏览器中按元素截图 | 从可编辑稿导出 PNG | 等待字体和图片加载，截取 `#poster` 整个画布，核对尺寸与底部内容。 |
| 只有原图，且有图像编辑能力 | 在用户选中的原图上局部改字或移动，再交付整图 | 放大核对目标文字，同时缩看完整海报与选中原图的布局。 |
| 飞书 Aily 或其他运行环境 | 根据该环境实际支持的文件读取、图像编辑、渲染和附件能力选择交付方式 | Aily 导入、脚本执行和附件展示需在目标租户实测。包内 HTML 和图片可作为素材读取。 |

若浏览器当前不能使用，已有图像编辑能力且有底稿时可走原图编辑路径；若只能生成文件，则交付实际生成的可编辑稿、素材及预览所需条件。发布到群聊或仓库属于另外的操作，以用户当次请求为准。

## 本地导出

以下命令用于含 `scripts/` 的 Codex 完整包或仓库中的 Skill 目录。将 `layout.html` 换成实际工作副本的路径。初次使用且本地缺少依赖时，安装 Playwright 及 Chromium。

```sh
python -m pip install playwright
python -m playwright install chromium
python scripts/export_poster.py assets/system/layout.html poster.png
```

使用已安装的 Chrome 或 Edge 时，加 `--browser-path` 并给出浏览器可执行文件的路径，可省去 Chromium 下载。默认画布为 941 × 1672，`--scale 2` 可导出 1882 × 3344。明确要替换已有文件时可用 `--overwrite`。

在完整包根目录执行 `python -m unittest discover -s tests -v` 可重跑回归测试。使用本机浏览器时，以环境变量 `POSTER_BROWSER_PATH` 指定浏览器路径。
