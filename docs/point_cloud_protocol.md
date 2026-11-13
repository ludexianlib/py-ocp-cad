# 点云接入协议 v1

本协议将设备驱动与工作台显示分离。发送端负责调用品牌 SDK、完成坐标转换并组帧；工作台接收统一数据，不加载品牌 SDK。第一版支持一个活动 TCP 数据源，每帧替换上帧，不进行累积建图或多坐标系融合。

## 启动和示例

启动工作台，在点云页面填写监听地址和端口，点击“开始接收”。默认 `127.0.0.1:8765`。跨机器接入时填写本机可用的网卡地址，发送端连接该地址。

在 Windows PowerShell 运行示例：

```powershell
.\.venv\Scripts\python.exe .\examples\point_cloud_sender.py --mode xyz
.\.venv\Scripts\python.exe .\examples\point_cloud_sender.py --mode rgb --unit m
.\.venv\Scripts\python.exe .\examples\point_cloud_sender.py --mode intensity --fps 10
```

每次运行一个示例，Ctrl+C 停止；也可用 `--frames 100` 限制帧数。三个示例使用同一几何尺寸。`--unit m` 只改变发送单位，查看端包围盒仍以毫米显示。接收服务启动期间禁用文件导入，停止接收后保留最后成功显示的帧。

适配器可直接复用客户端：

```python
import numpy as np
from app.point_cloud.services.point_cloud_client import PointCloudClient

with PointCloudClient("127.0.0.1", 8765, stream_id="my_lidar") as client:
    client.send_frame(
        points=np.array([[1.25, 0.0, 0.5], [2.0, 0.1, 0.6]], dtype=np.float32),
        unit="m",
        coordinate_frame="lidar",
        # colors=np.array([[255, 0, 0], [0, 255, 0]], dtype=np.uint8),
        # intensity=np.array([40, 180], dtype=np.float32),
        # intensity_range=(0, 255),
        # timestamp_ns=time.time_ns(), time_base="unix",
    )
```

客户端按连接从 0 自动生成递增序号。客户端是同步接口，应在设备采集线程或进程中使用，同一客户端不并发调用。连接失败或发送异常会抛出异常；需要重连时重新进入连接，序号重新从 0 开始。发送成功表示数据交给 TCP，并不代表查看端已显示；协议第一版没有逐帧确认。

## 单位和坐标系

- 每帧必须声明 `unit="mm"` 或 `unit="m"`，不根据坐标大小猜单位。接收端以 float64 将输入换算到毫米；米乘 1000，毫米不缩放。
- 毫米坐标仍为浮点数，允许如 `0.01 mm`。换算单位不提高设备测量精度。
- 统一为右手坐标系：X 向前、Y 向左、Z 向上。适配器负责坐标轴转换。
- `coordinate_frame` 是坐标系名称，不包含坐标变换。不同名字的坐标系不会自动配准。
- 同一 TCP 连接的 `stream_id` 和 `coordinate_frame` 不允许改变；更换源或坐标系应重新连接。每帧可声明自己的单位，接收端统一换算。
- 接收端保留一份最新待显示帧。渲染跟不上时替换旧的待显示帧，不保证每一帧都被显示，也不提供完整数据录制。

## TCP 报文

一个报文由以下部分连续组成，多帧可直接连续发送。TCP 的一次读取不等于一帧，接收端按长度拆包。

| 部分 | 字节数 | 编码 |
| --- | --- | --- |
| Magic | 4 | ASCII `PCV1`，十六进制 `50 43 56 31` |
| 帧头长度 | 4 | 小端无符号 uint32，不含固定前缀 |
| 数据长度 | 4 | 小端无符号 uint32，不含帧头和固定前缀 |
| 帧头 | 帧头长度 | UTF-8 JSON 对象 |
| 数据 | 数据长度 | 字段描述指定的二进制数组 |

固定前缀相当于 Python `struct.pack("<4sII", b"PCV1", header_length, payload_length)`。帧头限制为 1–65536 字节，二进制数据限制为 64 MiB，每帧最多 1000000 个点。

最小帧头示例，两个 XYZ 点，不带颜色和强度：

```json
{
  "protocol_version": 1,
  "stream_id": "lidar_01",
  "sequence": 0,
  "coordinate_frame": "lidar",
  "unit": "mm",
  "point_count": 2,
  "fields": {
    "points": {"dtype": "<f4", "shape": [2, 3], "offset": 0}
  }
}
```

此示例的数据长度为 `2 × 3 × 4 = 24` 字节，顺序为 `x0,y0,z0,x1,y1,z1`，C 行主序。JSON 空白不影响解析，长度按 UTF-8 编码后的字节数计算。

## 帧头字段

| 字段 | 要求 | 说明 |
| --- | --- | --- |
| `protocol_version` | 必填 | 整数 `1`，其他版本拒绝 |
| `stream_id` | 必填 | 1–128 字符非空字符串 |
| `sequence` | 必填 | 0–2^63−1 整数，同一连接严格递增；允许跳号 |
| `coordinate_frame` | 必填 | 1–128 字符非空字符串 |
| `unit` | 必填 | `mm` 或 `m` |
| `point_count` | 必填 | 0–1000000 整数 |
| `fields` | 必填 | 点属性描述，至少包含 `points` |
| `intensity_range` | 有强度时必填 | `[最小值, 最大值]`，有限数且最小值小于最大值，跨度也必须有限 |
| `timestamp_ns` | 可选 | 0–2^63−1 整数，采集时间，不是接收时间 |
| `time_base` | 有采集时间时必填 | `unix`、`device` 或 `monotonic` |

没有采集时间时，同时省略 `timestamp_ns` 和 `time_base`，接收端不伪造设备采集时间。`device` 和 `monotonic` 只在发送端自己的时间基准内有意义，不能据此直接计算跨设备时间差。时间戳和序号进入 QML 时转为字符串，避免 JavaScript 数字丢失 64 位整数精度。

`fields` 每项包含 `dtype`、`shape`、`offset`。偏移相对于二进制数据起始位置，单位为字节。

| 字段 | dtype | shape | 含义 |
| --- | --- | --- | --- |
| `points` | `<f4` 或 `<f8` | `[N, 3]` | 小端 float32 / float64 XYZ |
| `colors` | uint8，字节顺序无关 | `[N, 3]` | RGB，0–255 |
| `intensity` | `<f4` 或 `<f8` | `[N]` | 逐点有限强度值 |

`colors` 的 dtype 字符串为 `|u1`。有颜色和 float32 强度时，一种合法布局为：

```json
{
  "points": {"dtype": "<f4", "shape": [1000, 3], "offset": 0},
  "colors": {"dtype": "|u1", "shape": [1000, 3], "offset": 12000},
  "intensity": {"dtype": "<f4", "shape": [1000], "offset": 15000}
}
```

此布局数据长度为 19000 字节。数组分别连续存放，无行填充；字段不能重叠，不能留下空隙或未描述的尾部数据。零长度字段也必须有合法偏移。第一版拒绝未知点属性；后续新增属性需定义兼容规则或升级协议版本。未知帧头元数据可忽略，不能据此改变 v1 的字段含义。

## 数据校验和显示

- 无某属性时省略整个字段，不能使用 `null` 数组代替。零颜色表示黑色，零强度表示有效零值。
- 每项逐点属性长度必须与 `point_count` 一致。
- 非有限 XYZ 点被清理，对应 RGB 和强度同步移除。非空帧清理后没有有效坐标，则拒绝整帧。Python 客户端也会预先清理，因此通过它发送的数据通常不再包含无效点。
- RGB 必须为 uint8；接收后转为 0–1 的内部颜色。强度必须全部有限，不假设不同品牌具有相同范围。
- 强度按声明的 `intensity_range` 映射颜色，超出范围的值在显示时裁剪。建议同一测量模式使用固定范围，避免逐帧颜色变化。
- `point_count=0` 是合法空帧，`points.shape=[0,3]`，可以发送零字节数据。空帧清空画面并保留相机；与断线不同，断线保留最后成功显示的帧。
- 首个非空帧适配视角，后续保留相机和局部原点。可手动适配或重置；新连接视为新采集会话。
- 统一颜色、RGB、按高度、按强度属于查看端设置。缺少 RGB 或强度时对应选项禁用，已有设置缺少对应数据时退回统一颜色绘制。

## 异常与生命周期

完整报文中出现错误版本、字段、单位、序号等问题时，拒绝该帧，计入错误统计，继续读取下一帧。无效固定前缀、超限长度、部分报文超时或连接中途断开时，关闭当前连接并继续监听。开始收到一个报文后，每个读取阶段最多等待 10 秒；完全空闲的连接允许持续等待。停止服务会中断等待并释放监听端口。

界面统计中的“接收”表示通过校验的帧数，“跳过待显示帧”表示缓冲被新帧覆盖的次数，“拒绝”表示坏帧或连接报文错误次数，不等于传感器丢包数。界面保留最近的接收错误，建立新连接时清除。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\tests\test_point_cloud_workspace.py --render-check
```

协议和 TCP 测试不需要雷达或 GPU。实际渲染检查需要桌面 GPU，覆盖文件导入和实时 TCP 点云、颜色、相机、空帧以及资源释放。
