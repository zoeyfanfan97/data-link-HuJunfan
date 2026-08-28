# M6 综合运行与提交说明

## 一、基本信息

- **姓名**：Hu Junfan
- **学号**：2026-DL-001
- **GitHub 用户名**：zoeyfanfan97
- **仓库名称**：data-link-HuJunfan
- **Python 版本**：Python 3.11.9 (在独立虚拟环境 `.venv` 下运行)
- **核心依赖库**：`pandas 2.3.3`, `matplotlib 3.11.1`
- **是否使用 SQLite**：是 (已实现 `save_records_to_sqlite` 并生成 `output/states.db`)
- **M4 候选来源**：学校预生成大模型候选 (`pre_generated_mapping_candidate.csv`) + 人工逐项核验

---

## 二、安装与运行说明

### 1. 实验环境准备
在项目根目录 [summer_school_practice_v1.0](file:///c:/Users/junfa/Desktop/data-link-HuJunfan/summer_school_practice_v1.0) 下，按规范创建并配置独立虚拟环境：

```powershell
# Windows PowerShell 一键配置
powershell -ExecutionPolicy Bypass -File environment\setup.ps1
```

### 2. 一键执行全流水线（M2 ~ M5）
清空或新建 `student_package/output/` 目录后，运行综合流水线程序：

```powershell
.\.venv\Scripts\python.exe student_package\src_skeleton\run_all.py
```

### 3. 执行最终提交严格自检
```powershell
.\.venv\Scripts\python.exe environment\run_student_checks.py
.\.venv\Scripts\python.exe environment\check_student_submission.py --strict
```

---

## 三、程序入口与流水线架构

统一程序入口为 [run_all.py](file:///c:/Users/junfa/Desktop/data-link-HuJunfan/summer_school_practice_v1.0/student_package/src_skeleton/run_all.py)，其按照数据生命周期顺序依次调用各模块：

```text
[Pipeline 1/5] M2 编解码流水线 (m2_protocol.py)
    └─> parse_state_vector() -> encode_position_message() -> decode_position_message()
    └─> 生成: encoded_messages.bin, decoded_partner_states.csv, validation_log.csv, roundtrip_report.csv

[Pipeline 2/5] M3 时空关联与态势流水线 (m3_tracks.py)
    └─> decode_message_stream() -> build_tracks() -> build_current_situation() -> save_records_to_sqlite()
    └─> 生成: decoded_multitime.csv, track_table.csv, current_situation.csv, states.db

[Pipeline 3/5] M4 语义映射与融合流水线 (m4_mapping.py)
    └─> verify_candidate_mapping() -> map_to_unified()
    └─> 生成: llm_mapping_candidate.csv, verified_mapping_table.csv, unified_situation.ndjson

[Pipeline 4/5] M5 一致性保障与告警流水线 (m5_quality.py)
    └─> check_record() -> check_duplicates() -> build_quality_situation()
    └─> 生成: alert_log.csv, quality_situation.csv

[Pipeline 5/5] M6 总结与摘要导出 (run_all.py)
    └─> 导出: pipeline_execution_summary.json
```

---

## 四、输入与输出文件清单

### 1. 输入数据文件
- `student_package/data/raw_states.json`：固定教学样例（包含边界值与异常用例）。
- `student_package/data/partner_messages_sample.bin`：对端伙伴发送的 3 帧单目标报文。
- `student_package/data/partner_messages_multitime.bin`：对端伙伴发送的 9 帧多目标多时间片报文。
- `student_package/data/m4/partner_current_situation.csv`：TeachingLink 当前态势源数据。
- `student_package/data/m5/anomaly_cases.csv` 与 `anomaly_rules.csv`：异常检测用例与规则集。
- `student_package/data/opensky_real/`：OpenSky 真实快照（71帧，用于全流程真实数据验证）。

### 2. 输出结构化成果 (`student_package/output/`)
- `encoded_messages.bin`：编码生成的 3 帧 TeachingLink 大端二进制报文（123 字节）。
- `decoded_partner_states.csv`：`partner_messages_sample.bin` 解码明细表（34 个字段全量保留）。
- `validation_log.csv`：发送端与接收端全流程校验与异常日志。
- `roundtrip_report.csv`：编解码往返精度与容差比对报告（21 项对比 100% 通过）。
- `decoded_multitime.csv`：多时间片批量解码结果表（9 条记录）。
- `track_table.csv`：多目标航迹时序表（包含 `track_sequence_no` 组内升序自增）。
- `current_situation.csv`：去重提取的各目标最新全局态势表。
- `states.db`：SQLite 关系数据库文件（`state_record` 表，None 规范映射为 NULL）。
- `llm_mapping_candidate.csv`：初始大模型映射候选规则表。
- `verified_mapping_table.csv`：经人工审查修正后的 30 条双源正式映射规则。
- `unified_situation.ndjson`：符合 `unified_model.json` 规范的双源统一态势流（6 条标准 JSON）。
- `alert_log.csv`：一致性规则检查告警日志（5 条结构化告警）。
- `quality_situation.csv`：综合质量增强态势表（合成 `anomaly_level` 与 `display_status`）。
- `pipeline_execution_summary.json`：全流水线运行摘要。

### 3. 说明与展示文档 (`student_package/docs/`)
- `M1_system_flow.md`：系统端到端处理流程与架构图（Mermaid + 分阶段对照表）。
- `M1_interface_risk.md`：接口、通信机理、校验层次与六大工程风险说明。
- `M4_mapping_review.md`：AI 辅助映射核验报告（4 大 AI 错误剖析与人工修订依据）。
- `M5_result_note.md`：异常检测结果与边界分析报告。
- `M6_presentation.pdf`：不超过 5 页的成果展示汇报材料。

---

## 五、实验数据量与处理结果统计

| 模块 | 处理对象 | 数据量 / 帧数 | 执行结果 |
| :--- | :--- | :--- | :--- |
| **M2** | `raw_states.json` $\to$ 编码 | 5 条输入，过滤生成 3 帧 (123 字节) | 成功，异常记录安全捕获入日志 |
| **M2** | `partner_messages_sample.bin` $\to$ 解码 | 3 帧 41 字节报文 | 100% 成功解码，往返精度 $\le 1$ LSB |
| **M3** | `partner_messages_multitime.bin` $\to$ 批量解码 | 9 帧 (3 目标 $\times$ 3 时刻) | 9 航迹点关联成功，提取 3 个活跃目标态势 |
| **M3** | SQLite 关系化入库 (`states.db`) | 9 条记录 | 成功建表入库并支持 SQL 检索 |
| **M3** | OpenSky 真实快照验证 (`opensky_real/`) | 71 帧真实报文 | 71 航迹点成功生成，识别 24 个真实航空器目标 |
| **M4** | 双源统一模型映射 (`unified_situation.ndjson`) | 6 条态势 (OpenSky 3条 + TeachingLink 3条) | 100% 符合 `unified_model.json` 规范 |
| **M5** | 一致性规则检查 (`anomaly_cases.csv`) | 6 条测试用例 | 生成 5 条告警，正常用例 0 误报，状态合成准确 |

---

## 六、已知限制与工程边界说明

1. **TeachingLink 协议性质**：TeachingLink 为本实践教学定制协议，不代表实际 ADS-B、ASTERIX、Link 16 或任何航空行业标准。
2. **离线处理假设**：实验中所有数据均为离线快照，未引入实时网络重传、握手或复杂拥塞控制状态机。
3. **时钟对齐假定**：多目标多时刻批次假定帧边界已对齐，主要通过 `(target_id, timestamp)` 进行逻辑关联。

---

## 七、最终提交信息

- **仓库链接**：`https://github.com/zoeyfanfan97/data-link-HuJunfan`
- **最终 commit ID**：`HEAD (Personal Submission)`
- **最后检查日期**：`2026-08-26`
- **提交自检结论**：`check_student_submission.py --strict` 全部通过 (PASS)。
