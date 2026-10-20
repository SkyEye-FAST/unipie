# UniPie

从 Unifont Utils 拆分的独立 GNU Unifont 终端字形编辑器，参考 UniCucumber 的
编辑与文档历史行为。需要 Python 3.10 或更新版本，建议终端至少为 80×24。

```shell
uv sync --locked
uv run --locked unipie
uv run --locked unipie font.hex --code-point 4E2D
uv run --locked unipie --code-point 0041 --width 8
```

同时开发核心库时使用 `uv run --with-editable ../unifont_utils unipie`。
安装到独立工具环境可在本目录执行 `uv tool install .`。

支持画笔、橡皮、填充、线条、空心/实心矩形、选区剪切复制粘贴、反色、翻转、
平移、8/16 像素宽度切换；拖绘、批量导入和批量删除均可一次撤销/重做。
字形库可按代码点、字符、Unicode 名称或位图搜索，支持新增、复制、删除与分页。

支持 `.hex` 和版本化 JSON 备份的导入导出、明确的导入冲突策略、任意图像的
适应/裁切与阈值处理，以及单字形 PNG/BMP/SVG 缩放导出。模板替换可预览、
逐个或全部应用，确认前不会改变文档。

方向键/WASD 移动，空格绘制；图形工具在两个端点各按一次空格。鼠标左键拖绘，
右键或 Ctrl+左键擦除。画布聚焦时 1–7 切换工具，Y/X/V 复制/剪切/粘贴，
Ctrl+方向键平移，Ctrl+Z/Y 撤销/重做。Ctrl+S 保存，Ctrl+Shift+S 另存，
Ctrl+O 打开，Ctrl+I/E 导入/导出，Ctrl+N/D 新增/复制，Ctrl+Q 退出，F1 帮助。

工作文档保存为 `.hex`；图片和 JSON 导出不会清除文档的未保存标记。打开新文档
或退出前会提示保存、丢弃或取消。每两秒原子写入独立会话草稿，下次启动可选择
恢复、保留或删除；无法识别的草稿不会自动删除。强制终止时可能丢失最后两秒的
操作。保存前检测外部修改，但同时编辑同一个文件仍需自行协调。

Windows 草稿目录为 `%LOCALAPPDATA%\UniPie\drafts`；其他系统为
`${XDG_STATE_HOME:-~/.local/state}/unipie/drafts`。

完整功能、快捷键、格式语义和开发说明见 [English README](README.md)。
协议为 [GPL-3.0-or-later](LICENSE)。
