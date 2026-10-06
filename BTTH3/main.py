# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Chương trình chạy Agent Đặt Vé Máy Bay với 3 Mẫu Thiết Kế.

Sử dụng:
    python3 main.py --mau react --kich-ban chuan
    python3 main.py --mau plan-execute --kich-ban chuan
    python3 main.py --mau hybrid --kich-ban chuan

Các kịch bản kiểm thử:
    --kich-ban chuan       : Luồng chuẩn thành công, kiểm chứng code xác định
    --kich-ban lap         : Mô phỏng lặp tool, LoopDetector ngắt tại V2 và bàn giao
    --kich-ban vuot-gia    : Không có vé dưới ngân sách, harness kích hoạt bàn giao
    --kich-ban can-duyet   : Vé giá cao/không hoàn hủy, dừng chờ người duyệt (kiểm quyền)
    --kich-ban ao-giac     : Model cố tình bịa thông tin, GroundingVerifier chặn đứng

Chạy với Model thật (cần API key trong .env):
    python3 main.py --mau react --that
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from lib.mock_flight_db import mock_db
from lib.harness import (
    BookingConstraints,
    HandoffManager,
    PermissionGuard,
)
from lib.model_gia import ModelGiaFlight, model_that
from lib.agent_react import ReActFlightAgent
from lib.agent_plan_execute import PlanThenExecuteFlightAgent
from lib.agent_hybrid import HybridFlightAgent


CAU_HOI_MAC_DINH = (
    "Tôi muốn đặt 1 vé máy bay từ TP.HCM đi Đà Nẵng vào sáng ngày 2026-10-15, "
    "ngân sách tối đa 2.000.000 VNĐ. Tên hành khách: Nguyen Van A, CCCD: 079201009999."
)


def chay_agent(
    mau_thiet_ke: str,
    kich_ban: str = "chuan",
    dung_model_that: bool = False,
    tu_dong_duyet: bool = False,
    cau_hoi: Optional[str] = None,
) -> dict:
    """Khởi tạo và thực thi Agent theo mẫu thiết kế đã chọn."""
    mock_db.reset()

    is_over_budget_test = kich_ban in ["vuot-gia", "vuot_gia"]
    max_price = 1200000 if is_over_budget_test else 2000000

    if not cau_hoi:
        if is_over_budget_test:
            cau_hoi = (
                "Tôi muốn đặt 1 vé máy bay từ TP.HCM đi Đà Nẵng vào sáng ngày 2026-10-15, "
                "ngân sách tối đa 1.200.000 VNĐ. Tên hành khách: Nguyen Van A, CCCD: 079201009999."
            )
        else:
            cau_hoi = CAU_HOI_MAC_DINH

    # Thiết lập ràng buộc dữ liệu (Lớp 1 Harness)
    constraints = BookingConstraints(
        origin="SGN",
        destination="DAD",
        depart_date="2026-10-15",
        time_window="sang",
        max_price=max_price,
        passenger_name="Nguyen Van A",
        passenger_id="079201009999",
    )

    # Khởi tạo Model
    if dung_model_that:
        try:
            model = model_that()
            print(">> Đang sử dụng Model THẬT kết nối từ .env")
        except Exception as e:
            print(f"[CẢNH BÁO] Không tải được model thật ({e}). Chuyển sang ModelGiaFlight.")
            model = ModelGiaFlight(kich_ban=kich_ban)
    else:
        model = ModelGiaFlight(kich_ban=kich_ban)

    # Khởi tạo PermissionGuard (Lớp 3 Harness)
    # Nếu kịch bản là can-duyet thì không auto approve để thấy rõ việc dừng chờ duyệt
    guard = PermissionGuard(
        autopay_limit=1500000,
        auto_approve_test=(tu_dong_duyet or kich_ban == "chuan"),
    )

    print("=" * 80)
    print(f"BTVN#3 · AGENT ĐẶT VÉ MÁY BAY | MẪU: {mau_thiet_ke.upper()} | KỊCH BẢN: {kich_ban}")
    print("=" * 80)
    print(f"[Yêu cầu người dùng]: {cau_hoi}")
    print(f"[Ràng buộc dữ liệu] : Đi {constraints.origin} -> Đến {constraints.destination} | Ngày {constraints.depart_date} | Buổi: {constraints.time_window} | Trần giá: {constraints.max_price:,} VNĐ")
    print("-" * 80)

    agent_runner = None
    if mau_thiet_ke == "react":
        agent_runner = ReActFlightAgent(model=model, constraints=constraints, permission_guard=guard)
    elif mau_thiet_ke == "plan-execute":
        agent_runner = PlanThenExecuteFlightAgent(model=model, constraints=constraints, permission_guard=guard)
    elif mau_thiet_ke == "hybrid":
        agent_runner = HybridFlightAgent(model=model, constraints=constraints, permission_guard=guard)
    else:
        raise ValueError(f"Mẫu thiết kế không hợp lệ: {mau_thiet_ke}")

    ket_qua = agent_runner.run(cau_hoi)

    # In Trace thực thi
    print("\n--- NHẬT KÝ HÀNH ĐỘNG (ACTION TRACE) ---")
    for idx, act in enumerate(ket_qua.get("actions_taken", []), 1):
        print(f"  [V{idx}] Thực thi Tool -> {act}")

    print("\n--- KẾT QUẢ VÀ BÁO CÁO HARNESS ---")
    print(f"- Trạng thái kết thúc : {ket_qua.get('status')}")
    print(f"- Số bước thực hiện   : {ket_qua.get('steps')}")
    print(f"- Ước lượng Token     : {ket_qua.get('total_tokens')}")
    print(f"- Thời gian thực thi  : {ket_qua.get('elapsed_time')}s")

    # Báo cáo tiêu chí hoàn thành kiểm bằng code
    comp_report = ket_qua.get("completion_report", {})
    if comp_report:
        print("\n[Lớp 2: Tiêu chí hoàn thành kiểm bằng code]:")
        print(f"  + Hoàn tất xác nhận: {comp_report.get('is_completed')}")
        print(f"  + Chi tiết các kiểm tra:")
        for k, v in comp_report.get("checks", {}).items():
            print(f"      * {k:25}: {'[PASS] ĐẠT' if v else '[FAIL] LỖI'}")

    # Báo cáo chống ảo giác
    ground_report = ket_qua.get("grounding_report", {})
    if ground_report:
        print("\n[Lớp 1: Kiểm tra Căn cứ dữ liệu (Grounding / Anti-Hallucination)]:")
        print(f"  + Căn cứ hợp lệ : {'[PASS] 100% CÓ NGUỒN' if ground_report.get('passed') else '[FAIL] CÓ SỐ LIỆU ẢO'}")
        if not ground_report.get("passed"):
            print(f"  + Dữ kiện bịa đặt: {ground_report.get('ungrounded_facts')}")

    # Báo cáo bàn giao nếu dừng bất thường
    handoff = ket_qua.get("handoff_report")
    if handoff:
        print("\n" + HandoffManager.format_handoff_display(handoff))
    else:
        print("\n--- PHẢN HỒI CUỐI CÙNG CHO KHÁCH HÀNG ---")
        print(ket_qua.get("final_response"))

    print("=" * 80 + "\n")
    return ket_qua


def main():
    parser = argparse.ArgumentParser(description="SE373 · BTVN#3 Agent Đặt Vé Máy Bay")
    parser.add_argument(
        "--mau",
        default="react",
        choices=["react", "plan-execute", "hybrid", "all"],
        help="Mẫu thiết kế Agent: react, plan-execute, hybrid, hoặc all để chạy cả 3",
    )
    parser.add_argument(
        "--kich-ban",
        default="chuan",
        choices=["chuan", "lap", "vuot-gia", "can-duyet", "ao-giac"],
        help="Kịch bản thử nghiệm: chuan, lap, vuot-gia, can-duyet, ao-giac",
    )
    parser.add_argument(
        "--that",
        action="store_true",
        help="Sử dụng Model thật từ cấu hình .env thay vì model giả lập",
    )
    parser.add_argument(
        "--tu-dong-duyet",
        action="store_true",
        help="Tự động cấp quyền phê duyệt cho các hành động nhạy cảm",
    )

    args = parser.parse_args()

    if args.mau == "all":
        print("\n>>> CHẠY SO SÁNH CẢ 3 MẪU THIẾT KẾ TRÊN CÙNG KỊCH BẢN <<<\n")
        for m in ["react", "plan-execute", "hybrid"]:
            chay_agent(
                mau_thiet_ke=m,
                kich_ban=args.kich_ban,
                dung_model_that=args.that,
                tu_dong_duyet=args.tu_dong_duyet,
            )
    else:
        chay_agent(
            mau_thiet_ke=args.mau,
            kich_ban=args.kich_ban,
            dung_model_that=args.that,
            tu_dong_duyet=args.tu_dong_duyet,
        )


if __name__ == "__main__":
    sys.exit(main())
