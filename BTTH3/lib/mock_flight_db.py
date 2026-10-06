# -*- coding: utf-8 -*-
"""Cơ sở dữ liệu mockup chuyến bay và đơn đặt vé (Mock Flight Database).

Cung cấp dữ liệu chuyến bay nội địa Việt Nam (SGN, HAN, DAD, CXR, PQC)
và quản lý trạng thái đặt vé phục vụ kiểm thử deterministically không phụ thuộc mạng.
"""
from typing import Dict, List, Optional
import copy


# Danh sách chuyến bay mẫu
FLIGHTS_DATABASE = [
    {
        "flight_code": "VN122",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "DAD",
        "depart_date": "2026-10-15",
        "depart_time": "08:15",
        "arrive_time": "09:35",
        "time_window": "sang",
        "price": 1850000,
        "available_seats": 5,
        "is_refundable": False,  # Vé không hoàn tiền -> Cần phê duyệt nếu chính sách yêu cầu
        "baggage": "23kg ký gửi + 12kg xách tay",
    },
    {
        "flight_code": "VJ624",
        "airline": "Vietjet Air",
        "origin": "SGN",
        "destination": "DAD",
        "depart_date": "2026-10-15",
        "depart_time": "06:30",
        "arrive_time": "07:50",
        "time_window": "sang",
        "price": 1420000,
        "available_seats": 12,
        "is_refundable": True,  # Vé hoàn tiền được, giá < 1.500.000đ -> Có thể auto-approve
        "baggage": "7kg xách tay",
    },
    {
        "flight_code": "QH150",
        "airline": "Bamboo Airways",
        "origin": "SGN",
        "destination": "DAD",
        "depart_date": "2026-10-15",
        "depart_time": "10:45",
        "arrive_time": "12:05",
        "time_window": "sang",
        "price": 1950000,
        "available_seats": 3,
        "is_refundable": True,
        "baggage": "20kg ký gửi + 7kg xách tay",
    },
    {
        "flight_code": "VN128",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "DAD",
        "depart_date": "2026-10-15",
        "depart_time": "14:20",
        "arrive_time": "15:40",
        "time_window": "chieu",
        "price": 1650000,
        "available_seats": 8,
        "is_refundable": True,
        "baggage": "23kg ký gửi + 12kg xách tay",
    },
    {
        "flight_code": "VJ632",
        "airline": "Vietjet Air",
        "origin": "SGN",
        "destination": "DAD",
        "depart_date": "2026-10-15",
        "depart_time": "16:00",
        "arrive_time": "17:20",
        "time_window": "chieu",
        "price": 1350000,
        "available_seats": 15,
        "is_refundable": False,
        "baggage": "7kg xách tay",
    },
    {
        "flight_code": "VN136",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "DAD",
        "depart_date": "2026-10-15",
        "depart_time": "19:30",
        "arrive_time": "20:50",
        "time_window": "toi",
        "price": 2150000,  # Vượt trần 2.000.000 VNĐ
        "available_seats": 6,
        "is_refundable": True,
        "baggage": "23kg ký gửi + 12kg xách tay",
    },
    {
        "flight_code": "VN210",
        "airline": "Vietnam Airlines",
        "origin": "HAN",
        "destination": "SGN",
        "depart_date": "2026-10-15",
        "depart_time": "09:00",
        "arrive_time": "11:15",
        "time_window": "sang",
        "price": 2350000,
        "available_seats": 4,
        "is_refundable": True,
        "baggage": "23kg ký gửi + 12kg xách tay",
    },
]

# Sân bay hỗ trợ
AIRPORTS = {
    "SGN": "Sân bay Quốc tế Tân Sơn Nhất (TP. Hồ Chí Minh)",
    "HAN": "Sân bay Quốc tế Nội Bài (Hà Nội)",
    "DAD": "Sân bay Quốc tế Đà Nẵng (Đà Nẵng)",
    "CXR": "Sân bay Quốc tế Cam Ranh (Khánh Hòa)",
    "PQC": "Sân bay Quốc tế Phú Quốc (Kiên Giang)",
}


class MockFlightDatabase:
    """Quản lý trạng thái dữ liệu chuyến bay và đặt chỗ trong bộ nhớ."""

    def __init__(self):
        self.flights = copy.deepcopy(FLIGHTS_DATABASE)
        self.bookings: Dict[str, dict] = {}
        self._booking_seq = 1000

    def reset(self):
        """Khôi phục trạng thái ban đầu."""
        self.flights = copy.deepcopy(FLIGHTS_DATABASE)
        self.bookings.clear()
        self._booking_seq = 1000

    def search_flights(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        time_window: Optional[str] = None,
        max_price: Optional[int] = None,
    ) -> List[dict]:
        """Tìm chuyến bay khớp lộ trình và điều kiện."""
        norm_orig = origin.strip().upper()
        norm_dest = destination.strip().upper()

        results = []
        for f in self.flights:
            if (
                f["origin"] == norm_orig
                and f["destination"] == norm_dest
                and f["depart_date"] == depart_date
            ):
                if time_window and f["time_window"] != time_window.lower():
                    continue
                if max_price and f["price"] > max_price:
                    continue
                results.append(copy.deepcopy(f))
        return results

    def get_flight_by_code(self, flight_code: str) -> Optional[dict]:
        """Tra cứu chuyến bay theo mã."""
        code = flight_code.strip().upper()
        for f in self.flights:
            if f["flight_code"] == code:
                return copy.deepcopy(f)
        return None

    def create_booking(
        self,
        flight_code: str,
        passenger_name: str,
        passenger_id: str,
        seat_preference: str = "window",
    ) -> dict:
        """Tạo booking ở trạng thái giữ chỗ (pending)."""
        flight = self.get_flight_by_code(flight_code)
        if not flight:
            raise ValueError(f"Không tìm thấy chuyến bay {flight_code}")
        if flight["available_seats"] <= 0:
            raise ValueError(f"Chuyến bay {flight_code} đã hết chỗ")

        # Giảm số ghế khả dụng
        for f in self.flights:
            if f["flight_code"] == flight["flight_code"]:
                f["available_seats"] -= 1
                break

        self._booking_seq += 1
        booking_code = f"BK-{flight['flight_code']}-{self._booking_seq}"
        booking = {
            "booking_code": booking_code,
            "flight_code": flight["flight_code"],
            "airline": flight["airline"],
            "origin": flight["origin"],
            "destination": flight["destination"],
            "depart_date": flight["depart_date"],
            "depart_time": flight["depart_time"],
            "arrive_time": flight["arrive_time"],
            "price": flight["price"],
            "passenger_name": passenger_name,
            "passenger_id": passenger_id,
            "seat_preference": seat_preference,
            "is_refundable": flight["is_refundable"],
            "status": "pending",  # pending -> confirmed -> cancelled
            "is_paid": False,
            "payment_id": None,
        }
        self.bookings[booking_code] = booking
        return copy.deepcopy(booking)

    def pay_booking(self, booking_code: str, payment_method: str = "credit_card") -> dict:
        """Thực hiện thanh toán và xác nhận đặt chỗ."""
        code = booking_code.strip().upper()
        if code not in self.bookings:
            raise ValueError(f"Không tìm thấy đơn đặt vé {code}")
        b = self.bookings[code]
        if b["status"] == "confirmed" and b["is_paid"]:
            return copy.deepcopy(b)
        if b["status"] == "cancelled":
            raise ValueError(f"Đơn đặt vé {code} đã bị hủy, không thể thanh toán")

        b["is_paid"] = True
        b["status"] = "confirmed"
        b["payment_id"] = f"PAY-{self._booking_seq}-OK"
        return copy.deepcopy(b)

    def get_booking(self, booking_code: str) -> Optional[dict]:
        """Lấy thông tin đơn đặt chỗ để kiểm tra bằng code."""
        code = booking_code.strip().upper()
        if code in self.bookings:
            return copy.deepcopy(self.bookings[code])
        return None


# Global singleton instance
mock_db = MockFlightDatabase()
