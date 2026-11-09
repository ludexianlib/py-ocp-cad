# CAD Studio · Python 几何工作台

使用 **Python + PyQt6 + QML + OCP** 的桌面建模示例，无需本地编译 C++。
界面采用深色侧栏、浅色圆角卡片、紫色主色和黄色重点操作，主题集中在 `qml/components/Theme.qml`。

## Windows 启动

在项目目录的 Windows PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe .\main.py
```

首次创建虚拟环境时也可以运行已有安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
```

依赖固定为 OCP `8.0.1.1.0`、PyQt6 `6.7.1`、Qt `6.7.3`，使用预编译安装包。
PyQt 使用随 Python 包安装的 Qt 运行库，不需要配置系统 Qt 的 CMake 或 MSVC 工具链。

## 当前功能

- 单工作台布局，预览区随窗口高度伸缩，右侧参数区支持独立滚动。
- 使用统一卡片组件及淡入、悬停、弹窗过渡，保留通用统计卡片组件供后续复用。
- 根据尺寸创建长方体；默认尺寸为 `40 × 30 × 10 mm`。
- 支持 `0.01–10000 mm` 范围内的尺寸输入，界面支持两位小数。
- 支持 STEP 导入、颜色显示与导出，并显示操作结果。
- 只管理当前模型；创建或成功导入新模型后替换当前模型，导入失败恢复原模型。
- 模型仅保存在当前会话内；替换模型或关闭程序前，需要保留的模型请先导出为 STEP。

工作区使用 OCCT 原生三维视口，支持旋转、平移、缩放、适配模型及视图立方体导航。

## MVC 与组件

```text
main.py                            应用启动、字体及 QML 加载
app/models/cad_model.py             无 Qt 依赖的几何与当前模型管理
app/models/step_importer.py         STEP 读取与显示网格准备
app/controllers/cad_controller.py   建模、导入导出、失败恢复与界面状态接口
app/controllers/step_import_task.py 后台导入进程与加载线程
app/views/occt_viewport.py          QML 三维视口与输入适配
app/views/occt_renderer.py          OCCT 渲染与显示资源管理
qml/Main.qml                       工作台布局与组件连接
qml/components/Theme.qml            颜色、字体、圆角及数字格式
qml/components/Card.qml             通用卡片与入场动画
qml/components/MetricCard.qml       可复用统计卡片（当前工作台未使用）
qml/components/Sidebar.qml          工作台侧栏与操作指南入口
qml/components/CadToolbar.qml       页面标题与操作
qml/components/BoxPanel.qml         参数输入
qml/components/ViewportPanel.qml    原生三维预览面板
```

Python 模型层不依赖界面框架；控制器通过属性和信号提供数据，QML 负责显示与交互。
函数和变量遵循 `snake_case`，组件类名使用首字母大写的驼峰形式。

## 命令行示例与界面截图

原来的几何入门示例继续保留：

```powershell
.\.venv\Scripts\python.exe .\demo.py
```

生成工作台截图并退出：

```powershell
.\.venv\Scripts\python.exe .\main.py --screenshot out\workbench-preview.png
```

预览截图为生成文件，`out/`、虚拟环境和缓存不会加入 Git。
