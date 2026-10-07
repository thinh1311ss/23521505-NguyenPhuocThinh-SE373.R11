---
name: csv-quality
description: Kiểm tra chất lượng file CSV danh sách công việc (cột task_id, owner, hours) và kiểm tra quá tải công việc theo người bằng script có sẵn, rồi ghi báo cáo Markdown dưới output/. Dùng khi người dùng yêu cầu kiểm tra, rà soát chất lượng CSV, tính tổng giờ theo người, hoặc kiểm tra ai quá tải theo một ngưỡng giờ.
---

# CSV quality & Workload Check

Kiểm tra chất lượng CSV công việc và phân tích quá tải công việc theo người bằng script, không tự đếm bằng mắt.

## Chạy script

Dùng tool `bash` (cwd là workspace). Lệnh đầy đủ:

```
python skills/csv-quality/scripts/check_csv.py --input <đường dẫn CSV> --max-hours <ngưỡng>
```

Ví dụ: `python skills/csv-quality/scripts/check_csv.py --input data/workload.csv --max-hours 8`

> **QUY TẮC BẮT BUỘC VỀ NGƯỠNG GIỜ**:
> - Nếu người dùng yêu cầu kiểm tra quá tải hoặc tính tải công việc mà **thiếu ngưỡng giờ**, bạn **PHẢI HỎI LẠI** người dùng để xác nhận ngưỡng trước khi kết luận và ghi báo cáo.
> - Tuyệt đối không dùng ngưỡng từ các cuộc trò chuyện cũ hoặc tự ý gán một ngưỡng mặc định (như 8) khi người dùng chưa cung cấp.
> - Khi người dùng đã cung cấp ngưỡng, truyền đúng giá trị số đó vào tham số `--max-hours`.

## Kiểm tra kết quả

- `exit_code` 0: phân tích thành công. `stdout` là JSON gồm:
  - Thống kê chất lượng: `row_count`, `missing_owner_count`, `invalid_hours_count`, `duplicate_id_count`, `duplicate_ids`, `issues`.
  - Phân tích tải công việc:
    - `max_hours`: ngưỡng giờ đã nhận từ CLI.
    - `hours_by_owner`: object ánh xạ tên người sang tổng giờ hợp lệ (chỉ người có ít nhất 1 dòng được cộng).
    - `overloaded_owners`: danh sách những người vượt ngưỡng (`total_hours > max_hours`), sắp xếp theo tên.
    - `excluded_rows`: danh sách các dòng bị loại khỏi tính tổng giờ, kèm số dòng (`line`), `task_id` (null nếu rỗng) và danh sách mã lý do (`reasons`).
- `exit_code` khác 0: **lỗi thực thi** (file không tồn tại, thiếu cột bắt buộc, lỗi parse, hoặc thiếu/sai tham số `--max-hours`). Đọc `stderr`, báo lỗi rõ ràng cho người dùng. Không bịa số liệu, không ghi báo cáo như thể đã phân tích thành công.

## Viết báo cáo

1. Đọc template `references/report-template.md` trong thư mục skill này, tức `skills/csv-quality/references/report-template.md`.
2. Lấy mọi con số từ JSON của script. Báo cáo phải thể hiện đầy đủ:
   - Ngưỡng giờ áp dụng (`max_hours`).
   - Tổng giờ theo từng người (`hours_by_owner`).
   - Danh sách người vượt ngưỡng quá tải (`overloaded_owners`).
   - Các dòng bị loại kèm số dòng, task_id và tất cả lý do loại (`excluded_rows`).
   - Chi tiết các lỗi chất lượng dữ liệu cũ (`issues`).
3. Không sửa file CSV đầu vào. Có thể đề xuất cách xử lý trong mục khuyến nghị.
4. Ghi báo cáo bằng `write_file` vào đường dẫn người dùng yêu cầu (ví dụ `output/workload.md` hoặc `output/csv-quality.md`), rồi trả lời đường dẫn và tóm tắt ngắn.
