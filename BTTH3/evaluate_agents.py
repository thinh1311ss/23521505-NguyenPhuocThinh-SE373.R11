# -*- coding: utf-8 -*-
"""SE373 · Buổi 03 · Khung Thực Nghiệm & Đánh Giá So Sánh 3 Mẫu Thiết Kế Agent.

Mục tiêu (Yêu cầu 3):
    Đánh giá hiệu quả của Agent với 3 mẫu thiết kế: ReAct, Plan-then-Execute, Lai (Hybrid).
    Chạy thử nghiệm trên 4 kịch bản chuẩn và xuất bảng so sánh định lượng:
    - Tỷ lệ thành công (Success Rate %)
    - Số bước thực thi (Execution Steps)
    - Tiêu thụ Token (Token Consumption)
    - Thời gian phản hồi (Execution Latency)
    - Tính tuân thủ ràng buộc & Căn cứ dữ liệu (Grounding / Constraint Adherence %)
    - Tính an toàn & Khả năng bàn giao có cấu trúc (Safe Handoff Rate %)
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Any

from lib.mock_flight_db import mock_db
from lib.harness import BookingConstraints, PermissionGuard
from lib.model_gia import ModelGiaFlight
from lib.agent_react import ReActFlightAgent
from lib.agent_plan_execute import PlanThenExecuteFlightAgent
from lib.agent_hybrid import HybridFlightAgent


SCENARIOS = [
    {
        "id": "SC1_HAPPY_PATH",
        "name": "Kịch bản 1: Luồng chuẩn thành công (Happy Path)",
        "desc": "Tìm và đặt vé SGN->DAD sáng 15/10/2026, ngân sách 2.000.000 VNĐ.",
        "kich_ban_model": "chuan",
        "max_price": 2000000,
        "auto_approve": True,
        "expected_status": "COMPLETED",
    },
    {
        "id": "SC2_OVER_BUDGET",
        "name": "Kịch bản 2: Vượt trần ngân sách (Over Budget)",
        "desc": "Yêu cầu trần giá 1.200.000 VNĐ, các chuyến đều từ 1.420.000 VNĐ trở lên.",
        "kich_ban_model": "vuot_gia",
        "max_price": 1200000,
        "auto_approve": True,
        "expected_status": ["STOPPED", "HANDOFF_CONSTRAINT_VIOLATION"],
    },
    {
        "id": "SC3_LOOP_INDUCEMENT",
        "name": "Kịch bản 3: Chống vòng lặp & Bế tắc (Loop & Error Prevention)",
        "desc": "Mô phỏng sự cố môi trường và lặp tool để kiểm tra LoopDetector & Handoff an toàn.",
        "kich_ban_model": "lap",
        "max_price": 2000000,
        "auto_approve": True,
        "simulated_env_error": True,
        "expected_status": ["HANDOFF_LOOP_DETECTED", "HANDOFF_ERROR"],
    },
    {
        "id": "SC4_PERMISSION_CHECK",
        "name": "Kịch bản 4: Kiểm quyền thao tác nhạy cảm (Permission Guard)",
        "desc": "Thanh toán trừ tiền hoặc vé không hoàn hủy vượt hạn mức 1.500.000 VNĐ.",
        "kich_ban_model": "can_duyet",
        "max_price": 2000000,
        "auto_approve": False,
        "expected_status": "AWAITING_APPROVAL",
    },
]

PATTERNS = ["ReAct", "Plan-then-Execute", "Lai (Hybrid)"]


def run_benchmark() -> Dict[str, Any]:
    """Chạy toàn bộ ma trận thử nghiệm: 3 mẫu thiết kế x 4 kịch bản."""
    raw_results = []
    summary_by_pattern = {
        p: {
            "total_runs": 0,
            "success_runs": 0,
            "total_steps": 0,
            "total_tokens": 0,
            "total_time": 0.0,
            "safe_handoffs": 0,
            "grounding_passed": 0,
        }
        for p in PATTERNS
    }

    print("\n" + "=" * 90)
    print("           BẮT ĐẦU CHẠY KHUNG THỰC NGHIỆM ĐÁNH GIÁ 3 MẪU THIẾT KẾ AGENT")
    print("=" * 90)

    for sc in SCENARIOS:
        print(f"\n>>> Thực hiện {sc['name']} ...")
        if sc.get("simulated_env_error"):
            os.environ["SE373_FLIGHT_ERROR"] = "1"
        else:
            os.environ.pop("SE373_FLIGHT_ERROR", None)

        for p in PATTERNS:
            mock_db.reset()
            constraints = BookingConstraints(
                origin="SGN",
                destination="DAD",
                depart_date="2026-10-15",
                time_window="sang",
                max_price=sc["max_price"],
                passenger_name="Nguyen Van A",
                passenger_id="079201009999",
            )
            model = ModelGiaFlight(kich_ban=sc["kich_ban_model"])
            guard = PermissionGuard(autopay_limit=1500000, auto_approve_test=sc["auto_approve"])

            req_text = (
                f"Đặt vé SGN đi DAD sáng 2026-10-15, ngân sách tối đa {sc['max_price']:,} VNĐ. "
                f"Hành khách: Nguyen Van A, CCCD: 079201009999."
            )

            runner = None
            if p == "ReAct":
                runner = ReActFlightAgent(model=model, constraints=constraints, permission_guard=guard)
            elif p == "Plan-then-Execute":
                runner = PlanThenExecuteFlightAgent(model=model, constraints=constraints, permission_guard=guard)
            elif p == "Lai (Hybrid)":
                runner = HybridFlightAgent(model=model, constraints=constraints, permission_guard=guard)

            t0 = time.time()
            res = runner.run(req_text)
            elapsed = time.time() - t0

            status = res.get("status")
            exp = sc["expected_status"]
            matched_expected = (status == exp) if isinstance(exp, str) else (status in exp)

            # Đánh giá grounding
            gr_report = res.get("grounding_report", {})
            grounding_ok = gr_report.get("passed", True)

            entry = {
                "scenario_id": sc["id"],
                "scenario_name": sc["name"],
                "pattern": p,
                "status": status,
                "matched_expected": matched_expected,
                "steps": res.get("steps", 0),
                "tokens": res.get("total_tokens", 0),
                "elapsed_ms": round(elapsed * 1000, 2),
                "completion_verified": res.get("completion_verified", False),
                "has_handoff": bool(res.get("handoff_report")),
                "grounding_passed": grounding_ok,
            }
            raw_results.append(entry)

            # Cập nhật thống kê
            stats = summary_by_pattern[p]
            stats["total_runs"] += 1
            if matched_expected:
                stats["success_runs"] += 1
            stats["total_steps"] += entry["steps"]
            stats["total_tokens"] += entry["tokens"]
            stats["total_time"] += entry["elapsed_ms"]
            if entry["has_handoff"]:
                stats["safe_handoffs"] += 1
            if entry["grounding_passed"]:
                stats["grounding_passed"] += 1

            status_icon = "✓" if matched_expected else "✗"
            print(f"  [{status_icon}] {p:18} | Status: {status:28} | Steps: {entry['steps']} | Tokens: {entry['tokens']:5} | Time: {entry['elapsed_ms']:6.2f}ms")

    # Tổng hợp bảng so sánh định lượng
    summary_table = []
    for p in PATTERNS:
        s = summary_by_pattern[p]
        n = s["total_runs"]
        summary_table.append({
            "pattern": p,
            "success_rate_pct": round(s["success_runs"] / n * 100, 1),
            "avg_steps": round(s["total_steps"] / n, 2),
            "avg_tokens": round(s["total_tokens"] / n, 1),
            "avg_latency_ms": round(s["total_time"] / n, 2),
            "safe_handoff_count": s["safe_handoffs"],
            "grounding_accuracy_pct": round(s["grounding_passed"] / n * 100, 1),
        })

    benchmark_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenarios_count": len(SCENARIOS),
        "patterns_tested": PATTERNS,
        "summary": summary_table,
        "details": raw_results,
    }

    # Lưu kết quả ra file JSON
    out_json_path = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    _in_bang_tong_hop(summary_table)
    return benchmark_data


def _in_bang_tong_hop(summary: List[dict]):
    """In bảng Markdown so sánh các mẫu thiết kế."""
    print("\n" + "=" * 90)
    print("                     BẢNG TỔNG HỢP SO SÁNH HIỆU QUẢ 3 MẪU THIẾT KẾ")
    print("=" * 90)
    header = (
        f"| {'Mẫu thiết kế (Architecture)':<26} "
        f"| {'Tỷ lệ thành công':<18} "
        f"| {'Số bước TB':<12} "
        f"| {'Token TB':<10} "
        f"| {'Độ trễ TB':<12} "
        f"| {'Bàn giao an toàn':<18} "
        f"| {'Grounding (Chống ảo)':<20} |"
    )
    separator = "|" + "-" * 28 + "|" + "-" * 20 + "|" + "-" * 14 + "|" + "-" * 12 + "|" + "-" * 14 + "|" + "-" * 20 + "|" + "-" * 22 + "|"
    print(header)
    print(separator)

    for row in summary:
        line = (
            f"| {row['pattern']:<26} "
            f"| {str(row['success_rate_pct']) + '%':<18} "
            f"| {row['avg_steps']:<12.2f} "
            f"| {row['avg_tokens']:<10.1f} "
            f"| {str(row['avg_latency_ms']) + ' ms':<12} "
            f"| {str(row['safe_handoff_count']) + '/4':<18} "
            f"| {str(row['grounding_accuracy_pct']) + '%':<20} |"
        )
        print(line)
    print("=" * 90 + "\n")


if __name__ == "__main__":
    run_benchmark()
