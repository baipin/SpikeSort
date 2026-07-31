# ESP32-S3 ↔ 笔记本 带宽波动测量与实时监控系统计划

## 整体架构

```
ESP32-S3  ──(WiFi/TCP)──>  笔记本(Python接收端)  ──(HTTP/WS)──>  实时仪表盘
 [发送端]                   [采集+计算]                          [可视化]
```

核心思路：ESP32-S3 以固定 20fps 发送带时间戳的数据包，笔记本记录到达时间并计算实际带宽、抖动、丢帧率等指标，再推送到前端实时展示。

---

## 阶段零：开发环境搭建（VSCode + ESP-IDF）

ESP32-S3 固件统一使用 **VSCode + ESP-IDF 官方插件** 开发，直接基于 ESP-IDF 原生框架（非 Arduino），可获得对 S3 双核、FreeRTOS、WiFi/ lwIP 协议栈的最完整控制。

### 安装 ESP-IDF 插件

1. 安装 [VSCode](https://code.visualstudio.com/)
2. 扩展商店搜索 **Espressif IDF**（插件 ID: `espressif.esp-idf-extension`）并安装
3. 按 `Ctrl+Shift+P`（macOS: `Cmd+Shift+P`）→ 输入 `ESP-IDF: Configure ESP-IDF Extension`
4. 选择 **Express**（快速安装）或 **Advanced**（自定义路径）：
   - ESP-IDF 版本：建议 **v5.2 LTS** 或更新
   - 工具链、Python 虚拟环境由插件自动下载配置
5. 配置完成后底部状态栏出现 Build / Flash / Monitor 图标

### 创建项目

1. `Cmd+Shift+P` → `ESP-IDF: Create project from extension template` → 选 `template-app`
2. 项目名：`esp32s3-bandwidth-sender`
3. 项目结构如下：

```
esp32s3-bandwidth-sender/
├── CMakeLists.txt              # 顶层 CMake
├── sdkconfig.defaults          # 默认配置（可覆盖）
├── main/
│   ├── CMakeLists.txt
│   ├── main.c                  # 程序入口
│   └── sender.c / sender.h     # 发送逻辑
├── components/                 # 可选自定义组件
└── partitions.csv              # 分区表（如需自定义）
```

### 关键 sdkconfig 配置

在 `sdkconfig.defaults` 中写入以下内容（首次 `idf.py set-target esp32s3` 后生效）：

```
# CPU 频率
CONFIG_ESP32S3_DEFAULT_CPU_FREQ_240=y

# Flash / PSRAM（按板子选，N8R8 表示 8MB Flash + 8MB PSRAM）
CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_OCT=y

# WiFi
CONFIG_ESP_WIFI_STA_SUPPORT=y

# FreeRTOS 节拍（1ms tick → 1000Hz）
CONFIG_FREERTOS_HZ=1000

# SNTP（用于 NTP 时间同步）
CONFIG_LWIP_SNTP_MAX_SERVERS=3

# USB CDC（通过 USB 虚拟串口输出日志）
CONFIG_ESP_CONSOLE_USB_CDC=y
```

### 串口与烧录

- USB 连接 ESP32-S3，macOS 下设备名为 `/dev/cu.usbmodem*`
- 在 VSCode 底部状态栏选择对应串口和 Flash 方法（USB / UART）
- 构建流程：`Build` → `Flash` → `Monitor`（底部图标一键三连）
- 日志通过 `ESP_LOGI(TAG, ...)` 输出，Monitor 中自动着色

### 开发环境校验

1. 用 `template-app` 自带的 hello_world 烧录，确认 Monitor 看到 `Hello world!`
2. 烧录 Blink 点灯程序，验证 GPIO 控制
3. 确认 WiFi 初始化能扫描到 SSID（验证射频链路）

### ESP-IDF 与 Arduino 语法对照（本项目用到的）

| 功能 | Arduino 写法 | ESP-IDF 写法 |
|------|-------------|-------------|
| 获取毫秒时间戳 | `millis()` | `esp_timer_get_time() / 1000` |
| 获取微秒时间戳 | `micros()` | `esp_timer_get_time()` |
| WiFi 连接 | `WiFi.begin()` | `esp_wifi_init()` + `esp_wifi_connect()` |
| TCP 发送 | `WiFiClient.write()` | `send()` / `lwip_send()` |
| NTP 同步 | `configTime()` | `esp_sntp_setoperatingmode()` + `esp_sntp_setservername()` |
| 串口日志 | `Serial.println()` | `ESP_LOGI(TAG, fmt, ...)` |
| 延时 | `delay()` | `vTaskDelay(pdMS_TO_TICKS(ms))` |

---

## 阶段一：传输链路（WiFi + TCP）

确定使用 **WiFi + TCP** 作为唯一传输链路。TCP 提供可靠交付，但"可靠"不等于"不丢帧"——需要区分几个层面：

**TCP 链路特性与本项目的关系**：

- TCP 保证字节流有序到达、不丢失（靠重传），但重传会引入**延迟抖动**和**瞬时带宽跌落**
- 当 WiFi 物理层丢包严重时，TCP 拥塞控制会主动降速，表现为带宽波动
- 若发送端写缓冲满 / 连接中断，应用层 `send()` 可能阻塞或失败 → **应用层丢帧**

**丢帧的三种来源**（本项目需要分别处理）：

| 类型 | 原因 | 检测方式 | 处理策略 |
|------|------|----------|----------|
| 物理丢包 | WiFi 干扰/距离远 | TCP 重传统计（可选） | 记录为延迟抖动，不丢帧 |
| 拥塞降速 | TCP 拥塞窗口收缩 | 观察带宽曲线跌落 | 记录带宽波动 |
| 应用层丢帧 | `send()` 阻塞超时/缓冲满 | 序号断裂 | **重点监控**，计入丢帧率 |

**应用层防丢帧机制**（ESP32 发送端）：

- 发送 task 用非阻塞 `send()` + `MSG_DONTWAIT`，设发送超时（如 100ms）
- 若超时未发完，**丢弃当前帧**（跳过序号），保证 20fps 节拍不被拖慢
- 每帧序号依然递增，笔记本端通过序号断裂即可统计丢帧
- 可选：记录丢弃帧的序号和时间戳到本地缓冲，连接恢复后补发（仅用于离线分析）

**笔记本端丢帧检测**：

- 维护 `expected_seq`，每收到一帧检查是否连续
- 序号断裂 → 记录缺失区间 `[expected_seq, recv_seq - 1]`，计入丢帧计数
- 序号回退/重复 → 记录为乱序异常（理论上 TCP 不会发生，用于校验）

---

## 阶段二：ESP32-S3 发送端固件

**职责**：每 50ms（20fps）发送一帧，帧结构包含：

```
[序号(4B)][发送时间戳(8B)][载荷(payload, 可配置大小)][CRC(2B)]
```

**关键点**：

- 用 `esp_timer_get_time()` 获取微秒级时间戳（精度远高于 Arduino `millis()`）
- NTP 同步用 `esp_sntp` API，对齐两端时钟后可算端到端延迟
- 载荷大小可调（如 1KB / 4KB / 16KB），用于测试不同目标带宽
- WiFi 通过 `esp_wifi` 初始化，TCP 用 lwIP `socket()` API 连接到笔记本监听端口
- 帧序号严格递增，便于笔记本端检测丢帧/乱序
- 发送任务放在独立 FreeRTOS task 中，避免阻塞主任务
- **防丢帧设计**：`send()` 使用 `MSG_DONTWAIT` 非阻塞模式 + 100ms 超时，超时则跳过当前帧（序号继续递增），保证 20fps 节拍稳定
- 发送缓冲区大小通过 `lwip_setsockopt(SO_SNDBUF)` 可调，避免缓冲堆积导致延迟膨胀

**目标带宽示例**：20fps × 4KB = 80 KB/s ≈ 640 Kbps

---

## 阶段三：笔记本接收端（Python）

**职责**：接收、打到达时间戳、计算指标、转发到监控。

**核心模块**：

1. `socket` 监听 TCP，循环读取完整帧（按长度前缀拆包）
2. 每帧记录：`seq, send_ts, recv_ts, payload_size`
3. 滑动窗口（如 1 秒）计算：
   - **瞬时带宽** = 窗口内总字节 / 窗口时长
   - **带宽波动（抖动）** = 相邻窗口带宽差的标准差
   - **端到端延迟** = recv_ts − send_ts（需 NTP 对齐）
   - **丢帧率** = 缺失序号数 / 期望帧数
   - **帧间隔抖动** = 实际到达间隔的标准差

**输出**：写入 SQLite/CSV 存档 + 通过 WebSocket 推送实时指标。

---

## 阶段四：实时监控仪表盘

按投入程度，三档可选：

- **轻量档（最快上手）**：Python + `matplotlib` 动态刷新折线图，单机本地看
- **中档（推荐）**：Python 后端 + Flask/FastAPI + WebSocket，前端用 ECharts/Chart.js 画实时曲线，浏览器即可查看
- **专业档**：接收端把指标写入 **InfluxDB**，用 **Grafana** 做仪表盘，支持告警、历史回放、多指标叠加

推荐先用中档，后期若需长期监控再升级到 Grafana。

**建议展示的图表**：

- 瞬时带宽时序曲线（含目标带宽参考线）
- 延迟时序曲线
- 丢帧率柱状图
- 带宽波动（滚动标准差）曲线

---

## 阶段五：时钟同步与校准

端到端延迟测量依赖两端时钟对齐：

- ESP32-S3 通过 `esp_sntp` API 连 NTP 服务器同步系统时间（`esp_sntp_setoperatingmode(SNTP_OPMODE_POLL)`）
- 笔记本同样确保 NTP 同步
- 校准阶段：先跑 USB Serial 对照测试，确立基线波动，作为 WiFi 测量的参照

---

## 阶段六：测试与报告

- 变量扫描：不同 payload 大小、不同距离/信号强度
- 丢帧专项测试：逐步拉开距离 / 人为制造 WiFi 干扰，观察应用层丢帧率与 TCP 重传的关系
- 长时间稳定性测试（如 30 分钟持续运行）
- 输出统计报告：平均带宽、P50/P95/P99 延迟、最大波动幅度、丢帧率分布、丢帧连续长度统计

---

## 里程碑与建议顺序

0. 搭建 VSCode 开发环境 + 烧录 Blink 验证（0.5 天）
1. 先用 USB Serial 跑通"发送→接收→画图"全链路（1 天，验证流程）
2. 切到 WiFi TCP，加入时间戳与指标计算（1 天）
3. 搭建 Web 实时仪表盘（1 天）
4. NTP 时钟同步 + 端到端延迟测量（0.5 天）
5. 变量扫描与报告（1 天）

---

## 待确认项

- [x] 传输方式：**WiFi + TCP**（已确定）
- [ ] 目标 payload 大小（1KB / 4KB / 16KB …）
- [ ] 监控档位选择（轻量 / 中档 / 专业）
- [ ] 是否需要记录 TCP 重传统计（需开启 lwip 统计选项）
