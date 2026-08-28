from __future__ import annotations

import json
from pathlib import Path

# 导入各模块管道
try:
    from m2_protocol import execute_m2_pipeline
    from m3_tracks import execute_m3_pipeline, validate_opensky_real_data
    from m4_mapping import execute_m4_pipeline
    from m5_quality import execute_m5_pipeline
except ImportError:
    from student_package.src_skeleton.m2_protocol import execute_m2_pipeline
    from student_package.src_skeleton.m3_tracks import execute_m3_pipeline, validate_opensky_real_data
    from student_package.src_skeleton.m4_mapping import execute_m4_pipeline
    from student_package.src_skeleton.m5_quality import execute_m5_pipeline


STUDENT_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = STUDENT_PACKAGE_ROOT / "output"


def prepare_output_directory() -> None:
    """初始化并确保输出目录存在。"""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def parse_and_encode() -> dict:
    """执行 M2 阶段：解析 OpenSky 输入、编码 41 字节帧与解码验证。"""
    print("\n>>> [Pipeline 1/5] 执行 M2 协议编解码与防御校验...")
    return execute_m2_pipeline(STUDENT_PACKAGE_ROOT)


def build_tracks_and_situation() -> dict:
    """执行 M3 阶段：多时间片批量解码、航迹时序关联与最新态势提取。"""
    print("\n>>> [Pipeline 2/5] 执行 M3 多时刻航迹关联与当前态势...")
    res = execute_m3_pipeline(STUDENT_PACKAGE_ROOT)
    validate_opensky_real_data(STUDENT_PACKAGE_ROOT)
    return res


def map_unified_model() -> dict:
    """执行 M4 阶段：双源语义映射与统一 NDJSON 导出。"""
    print("\n>>> [Pipeline 3/5] 执行 M4 统一模型语义映射与融合...")
    return execute_m4_pipeline(STUDENT_PACKAGE_ROOT)


def check_consistency_quality() -> dict:
    """执行 M5 阶段：位置缺失、时钟延迟、联合键重复与航向越界规则检测。"""
    print("\n>>> [Pipeline 4/5] 执行 M5 一致性质量检查与告警生成...")
    return execute_m5_pipeline(STUDENT_PACKAGE_ROOT)


def export_pipeline_summary(summary_data: dict) -> None:
    """执行 M6 阶段：整理流水线运行摘要。"""
    print("\n>>> [Pipeline 5/5] 导出流水线运行摘要...")
    summary_path = OUTPUT_ROOT / "pipeline_execution_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    print(f"流水线执行完成，摘要已保存至 {summary_path.name}")


def run_pipeline() -> None:
    prepare_output_directory()
    m2_res = parse_and_encode()
    m3_res = build_tracks_and_situation()
    m4_res = map_unified_model()
    m5_res = check_consistency_quality()

    summary = {
        "status": "SUCCESS",
        "m2_protocol": m2_res,
        "m3_tracks": m3_res,
        "m4_mapping": m4_res,
        "m5_quality": m5_res,
    }
    export_pipeline_summary(summary)


def main() -> int:
    try:
        run_pipeline()
    except Exception as exc:
        print(f"[ERROR] 流水线执行失败: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
