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

依赖固定为 OCP `8.0.1.1.0`、PyQt6 `6.7.1`、Qt `6.7.3`、Open3D `0.20.0` 和 NumPy `2.5.4`，使用预编译安装包。
当前 Windows 环境使用 Python `3.14.5`。
PyQt 使用随 Python 包安装的 Qt 运行库，不需要配置系统 Qt 的 CMake 或 MSVC 工具链。

## 当前功能

- 启动时显示 SplashScreen、阶段进度条和百分比；主界面及 CAD 首帧显示完成后淡出。加载失败时显示错误并提供退出入口。
- 同一主窗口内提供 CAD 和点云两个工作台，侧栏切换并保留各页数据及相机状态。
- 点云支持 PLY、PCD、XYZ 导入、RGB / 统一颜色、点大小调整及包围盒信息；尺寸沿用源文件单位。
- 点云左键拖动旋转、右键拖动平移、滚轮缩放、双击适配；读取或预览失败保留原点云。
- 单工作台布局，预览区随窗口高度伸缩，右侧参数区支持独立滚动。
- 使用统一卡片组件及淡入、悬停、弹窗过渡，保留通用统计卡片组件供后续复用。
- 根据尺寸创建长方体；默认尺寸为 `40 × 30 × 10 mm`。
- 支持 `0.01–10000 mm` 范围内的尺寸输入，界面支持两位小数。
- 支持 STEP 导入、颜色显示与导出，并显示操作结果。
- 实体树保留 STEP 装配层级、零件名称与独立实例，支持展开折叠、Ctrl 多选及三维高亮联动。
- 缺少层级或层级无法映射时，自动按几何实体分组；曲面、线框、边等独立几何也会保留。
- 实体树和预览区提供右键菜单：隐藏选中、仅显示选中、显示全部。隐藏项仍保留在树中。
- 显隐只影响预览，STEP 导出始终包含完整模型；右键单击弹出菜单，右键拖动继续平移。
- 只管理当前模型；创建或成功导入新模型后替换当前模型，导入失败恢复原模型。
- 模型仅保存在当前会话内；替换模型或关闭程序前，需要保留的模型请先导出为 STEP。

工作区使用 OCCT 原生三维视口，支持旋转、平移、缩放、适配模型及视图立方体导航。

## MVC 与组件

```text
main.py                                      应用启动、控制器组装及视口注册
app/application/startup_controller.py        启动阶段、首帧等待、失败处理和启动画面生命周期
qml/SplashScreen.qml                        启动画面、阶段进度及过渡动画
app/cad/models/                              CAD 数据、几何及 STEP 导入导出
app/cad/controllers/                         CAD 控制器、实体树适配及后台导入
app/cad/views/                               OCCT 渲染、鼠标输入及视图立方体
app/point_cloud/models/point_cloud_model.py   点云数据和当前文档，无 Qt 依赖
app/point_cloud/models/point_cloud_io.py      Open3D 文件读取、无效点清理和颜色校验
app/point_cloud/controllers/                 点云导入任务、显示设置及失败恢复
app/point_cloud/views/open3d_renderer.py      Open3D 离屏渲染后端和相机计算
app/point_cloud/views/point_cloud_viewport.py QML 视口适配、输入及渲染请求调度
qml/Main.qml                                统一主窗口、导航及公共提示
qml/cad/CadPage.qml                          CAD 页面及 STEP 对话框
qml/cad/components/                          CAD 工具栏、参数面板、实体树和预览卡片
qml/point_cloud/PointCloudPage.qml           点云页面及导入对话框
qml/point_cloud/components/                  点云信息、显示设置及操作按钮
qml/components/                             共享主题、卡片、侧栏、提示和加载弹窗
```

两个业务模块各自遵循 MVC，Python 模型层不依赖界面框架；控制器通过属性和信号提供数据，QML 负责显示与交互。
CAD 使用 OCCT，点云使用 Open3D；两种视口复用同一主窗口，分别管理渲染资源。
点云 GPU 渲染使用独立后台进程，视口通过后台线程传输图像；按需更新并合并交互请求，隐藏页面暂停绘制。离屏图像回传有额外开销，大规模点云的速度和内存占用需按实际数据与显卡评估。
函数和变量遵循 `snake_case`，组件类名使用首字母大写的驼峰形式。

## 命令行示例与界面截图

原来的几何入门示例继续保留：

```powershell
.\.venv\Scripts\python.exe .\demo.py
```

启动进度代表真实初始化阶段；点云渲染后端在导入点云时按需启动。

生成工作台截图并退出（等待启动画面关闭及主界面就绪）：

```powershell
.\.venv\Scripts\python.exe .\main.py --screenshot out\workbench-preview.png
```

预览截图为生成文件，`out/`、虚拟环境和缓存不会加入 Git。

## 回归检查

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

覆盖装配名称与嵌套位置、重复实例、无名称与无层级回退、曲面和边、选择显隐、BREP 显示映射，以及导入失败后恢复选择和显隐状态。

点云测试覆盖 ASCII / 二进制文件、RGB、无效坐标、单点和面状点云，以及导入 / 预览失败恢复。

在有桌面 GPU 的 Windows PowerShell 中运行实际渲染检查：

```powershell
.\.venv\Scripts\python.exe .\tests\test_splash_screen.py --render-check
.\.venv\Scripts\python.exe .\tests\test_splash_screen.py --failure-check
.\.venv\Scripts\python.exe .\tests\test_point_cloud_workspace.py --render-check
.\.venv\Scripts\python.exe .\tests\test_viewport_visibility.py --render-check
```

点云检查会验证页面切换、鼠标导航、颜色、点大小、窗口缩放和资源释放，并在 `out/` 生成示例点云 `sample-point-cloud.ply` 及截图 `point-cloud-preview.png`。

启动检查覆盖阶段进度、首帧延迟等待、加载失败及退出；在 `out/` 生成 `splash-preview.png`、`startup-ready-preview.png` 和 `splash-error-preview.png`。
