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

- 工作台 / 模型库导航、模型统计、统一卡片组件及淡入、悬停、弹窗过渡。
- 根据实际 OCP 几何计算长方体体积与表面积；默认尺寸为 `40 × 30 × 10 mm`。
- 支持 `0.01–10000 mm` 范围内的尺寸输入，界面支持两位小数。
- 创建多个模型、切换当前模型、导出为 STEP，并显示操作结果。
- 模型仅保存在当前会话内；关闭前需要保留的模型请导出为 STEP。

**工作区当前是根据模型尺寸绘制的二维投影示意**，提供等轴测、正视、俯视切换。
这不是 OCCT 原生三维视口，真实三维旋转和选面仍留待后续接入。

## MVC 与组件

```text
main.py                            应用启动、字体及 QML 加载
app/models/cad_model.py             无 Qt 依赖的几何与会话模型
app/controllers/cad_controller.py   建模、选模型、导出与界面状态接口
qml/Main.qml                       工作台布局与组件连接
qml/components/Theme.qml            颜色、字体、圆角及数字格式
qml/components/Card.qml             通用卡片与入场动画
qml/components/MetricCard.qml       统计卡片
qml/components/Sidebar.qml          左侧导航
qml/components/CadToolbar.qml       页面标题与操作
qml/components/BoxPanel.qml         参数输入
qml/components/ViewportPanel.qml    尺寸投影预览
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
