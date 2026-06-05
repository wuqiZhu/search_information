# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

嵌入式物联网(IoT)智慧环境监控系统，基于 NXP i.MX6ULL ARM Cortex-A7 平台。五层分层架构：驱动层 → HAL硬件抽象层 → RPC服务层 → 应用客户端层 → 云端层。

**开发板硬件**：LED(GPIO131), DHT11(GPIO115), PIR人体红外(GPIO116), 烟雾传感器DO(GPIO117), 继电器1风扇(GPIO118), 继电器2 LED灯(GPIO119), 光敏ADC(ch3), USB摄像头(/dev/video1)

**云端**：阿里云服务器，已部署 MQTT Broker + InfluxDB + Grafana (Docker)，Telegraf 采集数据。云上已运行 `/opt/iot_mqtt_to_influx/mqtt_to_influxdb.py.bak` 脚本。

## Build Commands

- **RPC Server** (ARM交叉编译): `cd lesson5/rpc_server && make clean && make`
- **MQTT Bridge** (Release): `cd lesson6 && make clean && make`
- **MQTT Bridge** (Debug): `cd lesson6 && make clean && make debug`
- **RPC Client**: `cd lesson5/rpc_client && make clean && make`
- **单元测试** (本地gcc): `cd lesson6 && gcc -DTEST_MAIN -o test test_cases.c error.c config.c cJSON.c -lm -I. && ./test && rm -f test`
- **一键检查**: `bash check_all.sh`
- **静态分析**: `cd lesson6 && make cppcheck` / `make clang-tidy` / `make valgrind`
- **快照管理**: `./snapshot.sh save "备注"` — 改代码前先拍快照，出错 `./snapshot.sh restore <编号>` 一键恢复
- **共享库编译**: `cd shared_lib && make` — 编译公共模块为静态库 libshared.a
- **SDK路径**: `/home/book/100ask_imx6ull-sdk/` (主机开发环境)
- **工具链**: `arm-buildroot-linux-gnueabihf-gcc/g++ 7.5.0`
- **编译选项**: `-Wall -Wextra -Werror`

## Key Architecture

### System Layers

```
硬件外设 → 内核驱动(.ko) → rpc_server(端口1234) → 客户端(Qt/MQTT/命令行)
                                                        → Web管理界面(HTTP 8080)
                                                        → MQTT Broker → Python脚本 → InfluxDB
```

### RPC Server (`lesson5/rpc_server/`) — 9 个方法
- 基于 jsonrpc-c + libev 事件循环，端口 1234
- 集成 HAL 硬件抽象层 (`hal.h/c`)、HTTP 服务器 (`http_server.h/c`)、看门狗 (`watchdog.h/c`)
- 方法: `led_control`, `dht11_read`, `pir_read`, `light_read`, `relay_control/read`, `relay2_control/read`, `smoke_digital_read`
- **所有硬件操作必须通过 HAL 接口**，禁止在 rpc_server.c 中直接操作 sysfs

### MQTT Bridge (`lesson6/mqtt_bridge.cpp`) — 智能网关
- 订阅 `device/control`，发布到 `device/response`, `device/telemetry`, `device/alert`, `device/heartbeat`, `device/image_upload`
- 事件驱动上报（状态变化/阈值变化才上报），每5分钟强制全量上报
- 边缘智能自动控制：烟雾联动（含拍照上传）、温度联动（滞后控制）、光照+PIR联动（延时关灯）
- RPC客户端库 (`rpc_client.h/cpp`) 线程安全，带超时(3s)和自动重连
- **图片传输**: 烟雾报警时通过 **HTTP POST** 直传JPEG到云端 `http://8.140.232.52:9090/upload`，失败时回退到 MQTT base64。不再依赖 MQTT 传输大 payload。

### Web Management (`lesson5/rpc_server/`)
- HTTP 服务器端口 8080，前端 `www/index.html`
- API 端点: `/api/sensors`, `/api/relay/1|2`, `/api/led/control`, `/api/system`, `/api/sensor_status`, `/api/device_info`, `/api/camera/capture|list`, `/api/ota/*`, `/api/config/*`, `/api/logs`, `/api/auth/*`, `/api/export`
- 登录认证: Token 机制，有效期24h，默认 admin/admin

### Cloud (`cloud/` + 阿里云)
- `cloud/mqtt_to_influxdb.py.bak` — 运行在阿里云上，订阅MQTT主题写入InfluxDB，含钉钉告警通知
- 内置 HTTP 服务器（端口 9090）：`GET /images/` 提供图片访问（钉钉用），`POST /upload` 接收开发板上传的JPEG
- 配置方式：**环境变量**（INFLUXDB_TOKEN, MQTT_PASS, DINGTALK_WEBHOOK 等），禁止硬编码
- 启动命令: `cd /opt/iot_mqtt_to_influx && nohup python3 -u mqtt_to_influxdb.py.bak > mqtt_to_influxdb.log 2>&1 &`
- Grafana 仪表板在 `grafana/`，docker-compose 部署

### Kernel Drivers (`驱动库源码/`)
- `dht11_drv.ko` — 设备节点 `/dev/mydht11`，中断+定时器解析单总线协议
- `led_drv.ko` — 设备节点 `/dev/100ask_led`，GPIO控制
- **高风险模块，禁止AI直接修改**（时序、中断错误会导致系统崩溃）

## Configuration

配置加载优先级：**环境变量 > 配置文件 > 默认值**

- 环境变量: MQTT_HOST/PORT/USERNAME/PASSWORD, INFLUXDB_*, RPC_HOST/PORT 等
- 配置文件: `config.json` (GPIO引脚、阈值、间隔等)
- HAL引脚在 `hal.h` 中宏定义 (`HAL_PIR_PIN`, `HAL_RELAY1_PIN` 等)
- **敏感信息必须从环境变量读取，禁止硬编码**（包括 INFLUXDB_TOKEN、MQTT_PASS、DINGTALK_WEBHOOK）
- `.env.example` 为模板，按需复制为 `/root/.env`（开发板）或 `/root/.env.cloud`（阿里云）

## Key Modules (lesson6/)

| 模块 | 文件 | 说明 |
|------|------|------|
| 配置管理 | `config.h/c` | JSON解析 + 环境变量，组合加载 |
| 日志系统 | `log.h/c` | DEBUG/INFO/WARN/ERROR/FATAL，文件轮转 |
| 错误处理 | `error.h/c` | 统一错误码，CHECK_ERROR宏 |
| 数据缓存 | `data_cache.h/c` | 环形缓冲区，断网缓存，恢复重传 |
| 系统监控 | `system_monitor.h/c` | CPU/内存/负载/运行时间，`/proc`采集 |
| 设备认证 | `device_auth.h/c` | MAC地址ID + Token，自动注册 |
| 消息队列 | `msg_queue.h/c` | 线程安全，支持优先级，已集成到mqtt_bridge |
| 传感器管理器 | `sensor_manager.h/c` | 即插即用，统一管理，已集成 |
| OTA升级 | `ota_manager.h/c` | 异步下载、校验、备份、回滚 |
| 摄像头管理 | `camera_manager.h/c` | V4L2+MJPG，Base64编码 |
| 安全审计 | `security_audit.h/c` | 事件记录、IP锁定、证书检查 |
| 数据安全 | `crypto_utils.h/c` | SHA-256、XOR加密、数据脱敏 |
| 内存池 | `memory_pool.h/c` | 固定大小池、泄漏检测 |
| 性能监控 | `perf_monitor.h/c` | 监控点、快照、阈值告警 |
| 插件管理器 | `plugin_manager.h/c` | dlopen动态加载 |
| 设备发现 | `device_discovery.h/c` | UDP广播发现 |

## Important Design Patterns

- **HAL层**: 所有硬件操作经过 `hal.h/c`，换开发板只需重写 hal.c
- **线程安全**: RPC客户端使用 `pthread_mutex` 保护 socket 操作
- **传感器故障恢复**: 连续5次失败标记离线，每60秒自动重试
- **数据滤波**: 滑动平均（温度3次、湿度3次、光照5次）
- **烟雾防抖**: HAL层连续3次读取同一状态才确认变化
- **共享库**: cJSON 和 watchdog 已抽离到 `shared_lib/`，所有模块统一从 `shared_lib/src/` 编译，头文件从 `shared_lib/include/` 引用
- **ARM char类型**: ARM平台 `char` 默认 unsigned (0~255)，不要与 `-1` 比较

## Test & Debug

- `curl http://<开发板IP>:8080/api/sensors` — 验证传感器数据
- `mosquitto_pub -h <BROKER> -t "device/control" -m '{"method":"led_control","params":[1]}'` — 远程控制
- `mosquitto_sub -h <BROKER> -t "device/telemetry"` — 订阅遥测
- `journalctl -u rpc_server -f` — 查看rpc_server日志
- `journalctl -u mqtt_bridge -f` — 查看mqtt_bridge日志
- `cat /sys/class/gpio/gpio116/value` — 直接查看GPIO状态
- `v4l2-ctl --list-formats-ext -d /dev/video1` — 查看摄像头格式
- `ping -c 3 8.140.232.52` — 测试到阿里云服务器的网络连通性
- `./snapshot.sh diff <编号>` — 对比当前代码与某次快照的差异

## Known Issues

1. **MQTT连接不稳定** (待验证): `mqtt_connect failed: -4` (TCP连接失败)，可能因网络或MQTT Broker离线。图片传输已改为HTTP直传，不依赖MQTT。
2. **Web摄像头抓拍失败** (待板端调试): 点击Web"抓拍"按钮返回失败，但开发板手动执行 `v4l2-ctl` 正常。
3. **摄像头设备节点**: 默认 `/dev/video1` (罗技C270)，需确认实际设备节点。
4. **共享库已抽离**: cJSON 和 watchdog 已移到 `shared_lib/`，删除重复副本。后续新增公共模块也放 `shared_lib/`。
5. **`.snapshots/` 目录不提交**: 快照是本地开发用，`.gitignore` 中应排除 `.snapshots/`。
