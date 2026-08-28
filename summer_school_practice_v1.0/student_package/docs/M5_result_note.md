# M5 异常结果说明 (M5-3)

## 1. 实验基础配置与运行情况
- **统一批次时间**：`batch_time = 1710000120`（当前态势批次处理基准时间）。
- **四类必做规则运行情况**：已全部实现并针对 `student_package/data/m5/anomaly_cases.csv`（6条测试用例）全量运行：
  - **R1: `POSITION_MISSING` (HIGH)** —— 经度或纬度为空检测；
  - **R2: `DATA_DELAYED` (MEDIUM)** —— `batch_time - record_time > 60秒` 延迟检测；
  - **R3: `DUPLICATE_RECORD` (MEDIUM)** —— `(target_id, timestamp)` 联合键重复检测；
  - **R4: `HEADING_OUT_OF_RANGE` (MEDIUM)** —— 航向角越界 `heading < 0` 或 `heading >= 360` 检测。

---

## 2. 告警统计与严重性分布

### 2.1 告警总数及按类型统计
本次检查共生成 **5 条告警**，详细分布如下：
- **`POSITION_MISSING`**：1 条（目标 `780def`，纬度为空）；
- **`DATA_DELAYED`**：1 条（目标 `000001`，时间戳为 1710000000，延迟 120 秒，超过 60 秒阈值）；
- **`DUPLICATE_RECORD`**：2 条（目标 `780aaa` 在时间戳 1710000100 出现 2 次，分别记录实例告警）；
- **`HEADING_OUT_OF_RANGE`**：1 条（目标 `780bbb`，航向为 360.0°，超出 `[0, 360)` 范围）。

### 2.2 严重性等级分布与态势合成
- **HIGH 级别**：1 项（对应 `POSITION_MISSING`，合成显示状态 `display_status = ERROR`）；
- **MEDIUM 级别**：4 项（对应延迟、重复、航向越界，合成显示状态 `display_status = WARNING`）；
- **NONE 级别 / 无告警**：1 项（目标 `780abc` 为完全正常的标准记录，合成显示状态 `display_status = NORMAL`）。

---

## 3. 核心机制自检与验证结论

### 3.1 正常记录误报检查
- **目标 `780abc`**（用例第 1 行）：经纬度完整合法、延迟 10 秒（$\le 60$s）、无重复、航向 88.0°，**未触发任何告警**，`anomaly_level = NONE`, `display_status = NORMAL`，证明规则引擎不会对正常记录产生误报。

### 3.2 `heading = 360.0` 与 `heading = null` 的精准区分处理
- **`heading = 360.0`（用例 `780bbb`）**：
  由于课程规则要求航向角必须满足半开区间 $[0^\circ, 360^\circ)$，因此 `heading = 360.0` 应直接判定为越界，不能通过取模方式静默修正。用例中出现 360.0° **准确触发 R4 `HEADING_OUT_OF_RANGE` 告警**，`heading_valid = False`。
- **`heading = null`（空值）**：
  若某记录的航向字段缺失，其为合法的可空字段，**不会错误触发 R4 越界告警**，`heading_valid` 保持为 True（不视为越界），严格保证了可空字段的独立性。

---

## 4. 关键概念辨析：字段缺失 vs 帧验证失败 vs 来源真实性

在数据链路工程与态势融合体系中，必须严格区分以下三个层次的判定：

1. **字段缺失（Field Missing / Nullability）**：
   - *定义*：单个业务属性（如呼号、高度、速度）未被传感器测得或在当前帧中未填写（`validity_flags` 对应位置 0）。
   - *影响*：**不影响整帧合法性**。只要必需字段（`icao24`, `timestamp`, `on_ground`）健全，该记录依然是一条有效的态势记录，并可正常进入航迹与当前态势。
2. **帧验证失败（Frame Validation Error / `message_valid = False`）**：
   - *定义*：物理传输或格式层面的违规（如帧长不是 41 字节、魔数错误、Checksum 不符、保留位非 0、标志位与占位符冲突）。
   - *影响*：说明报文已受信道噪声损毁或协议解析错乱，**整帧不可接受**，必须丢弃并记录入 `validation_log.csv`，严禁进入态势库。
3. **来源真实性（Source Authenticity & Trustworthiness）**：
   - *定义*：回答“该报文是否由真实可信的实体发射、是否被敌方欺骗或重放”。
   - *区别*：`message_valid = True` 仅代表**报文格式与校验和符合技术规范**，绝不等于数据内容反映了真实战场物理态势，更不代表信源具备防重放或防伪鉴别能力。真实性需要由密码学认证（如签名、数字证书）或多传感器交叉验证共同保证。
