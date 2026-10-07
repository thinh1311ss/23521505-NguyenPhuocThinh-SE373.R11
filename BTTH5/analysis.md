# BÁO CÁO PHÂN TÍCH THỰC NGHIỆM VÀ KẾT QUẢ BÀI TẬP THỰC HÀNH SỐ 5 (BTTH5)
### Môn học: Kỹ thuật xây dựng hệ thống Agentic AI (SE373) — Buổi 05: Tool Use & Skill Use
**Sinh viên thực hiện:** Nguyễn Phước Thịnh — **MSSV:** 23521505 — **Lớp:** SE373.R11  

---

## MỤC LỤC
1. [TỔNG QUAN BÀI TẬP THỰC HÀNH 5](#1-tong-quan-bai-tap-thuc-hanh-5)
2. [BLOCK 1: TRA CỨU CHÍNH SÁCH ĐÚNG PHIÊN BẢN](#2-block-1-tra-cuu-chinh-sach-dung-phien-ban)
   - 2.1. Cài đặt Tool `list_files` và Cơ chế An toàn Sandbox
   - 2.2. Kết quả Kiểm thử Tool Trực tiếp (4 trường hợp)
   - 2.3. Thiết kế Skill `refund-policy` và Hướng dẫn Xử lý
   - 2.4. Phân tích Thực nghiệm & Dẫn chứng Trace (Trường hợp A, B, Thiếu thông tin)
   - 2.5. Trả lời Câu hỏi Phân tích Cuối Block 1
3. [BLOCK 2: KIỂM TRA QUÁ TẢI THEO NGƯỜI](#3-block-2-kiem-tra-qua-tai-theo-nguoi)
   - 3.1. Phân tích Stage 03: Tính Tổng Giờ qua Bash & Thuật toán Khử Trùng
   - 3.2. Mở rộng Script `check_csv.py` và Cập nhật Skill `csv-quality`
   - 3.3. Kết quả Chạy Trực tiếp và Trường hợp Biên (Edge Case)
   - 3.4. Bộ Kiểm thử Tự động Pytest
   - 3.5. Phân tích Thực nghiệm & Dẫn chứng Trace (Ngưỡng 8h, 9h, Thiếu ngưỡng, File lỗi)
   - 3.6. Trả lời Câu hỏi Phân tích Cuối Block 2
4. [TỔNG KẾT ĐÁNH GIÁ VÀ BÀI HỌC KINH NGHIỆM](#4-tong-ket-danh-gia-va-bai-hoc-kinh-nghiem)

---

## 1. TỔNG QUAN BÀI TẬP THỰC HÀNH 5

Bài tập thực hành 5 tập trung vào hai năng lực cốt lõi của hệ thống Agentic AI trong môi trường doanh nghiệp:
1. **Tool Use kết hợp Skill Use (Block 1):** Bổ sung công cụ tương tác file hệ thống (`list_files`), kết hợp với quy trình nghiệp vụ (Skill) để tra cứu, đối chiếu và áp dụng chính sách hoàn tiền đúng phiên bản hiệu lực, có khả năng thích ứng linh hoạt khi cấu trúc thư mục hoặc tên file bị thay đổi mà không cần hardcode trong system prompt.
2. **Deterministic Script Execution kết hợp Skill Use (Block 2):** Khắc phục hoàn toàn điểm yếu tính toán số học xác suất của LLM bằng cách chuyển giao logic tính tổng tải công việc, khử trùng định danh (`task_id`) và lọc dữ liệu bẩn cho một script Python xác định (`check_csv.py`), trong khi LLM đóng vai trò điều phối (orchestration), kiểm tra tham số người dùng và diễn giải kết quả phân tích theo mẫu báo cáo chuẩn.

Toàn bộ quá trình thực nghiệm được triển khai trên nền tảng `agent-tools-skills-lab` (từ `stage-00-chat` đến `stage-04-script-skill`), sử dụng mô hình ngôn ngữ lớn thật (`gemini-3.5-flash-lite`) thông qua Google AI API, ghi nhận đầy đủ trace JSON Lines (JSONL) theo chuẩn của hệ thống.

---

## 2. BLOCK 1: TRA CỨU CHÍNH SÁCH ĐÚNG PHIÊN BẢN

### 2.1. Cài đặt Tool `list_files` và Cơ chế An toàn Sandbox

Trong kiến trúc của `stage-01-files` và `stage-02-skills`, agent ban đầu chỉ được cung cấp 2 công cụ thao tác file: `read_file` và `write_file`. Khi người dùng đưa ra yêu cầu tra cứu chính sách, nếu tên file thay đổi hoặc agent không biết trước cấu trúc thư mục, agent hoàn toàn bất lực trong việc định vị tài liệu.

Để giải quyết vấn đề này, tool `list_files(path: str)` được thiết kế và tích hợp vào `tools/files.py` với các nguyên tắc kỹ thuật nghiêm ngặt:
- **Nguyên tắc Sandbox (Path Traversal Protection):** Toàn bộ đường dẫn đầu vào được chuẩn hóa và kiểm tra bằng `resolve_path(path)`. Bất kỳ nỗ lực truy cập nào có chứa `..`, đường dẫn tuyệt đối ra ngoài workspace, hoặc symlink trỏ ra ngoài đều bị chặn đứng và trả về mã lỗi `PATH_OUTSIDE_WORKSPACE`.
- **Xác định rõ ràng kiểu lỗi:** 
  - Nếu đường dẫn không tồn tại: Trả về lỗi `DIR_NOT_FOUND` kèm thông báo chi tiết, tuyệt đối không trả về danh sách rỗng (tránh gây ngộ nhận cho LLM rằng thư mục tồn tại nhưng không có file).
  - Nếu đường dẫn trỏ tới một file thông thường: Trả về lỗi `NOT_A_DIRECTORY`.
- **Cấu trúc dữ liệu chuẩn hóa:** Mỗi mục con trả về gồm `name` (tên mục), `path` (đường dẫn tương đối so với workspace), và `type` (`"file"` hoặc `"directory"`).
- **Tính tiền định (Determinism):** Danh sách các mục được sắp xếp theo thứ tự bảng chữ cái (`key=lambda x: x["name"]`) để đảm bảo đầu ra luôn ổn định giữa các lần gọi.
- **Đăng ký tool:** Tool được đăng ký vào danh sách xuất khẩu trong `tools/__init__.py` và mảng `tools` trong hàm `build_agent()` tại `agent.py`.

```python
# Trích đoạn cài đặt list_files trong tools/files.py:
@tool
def list_files(path: str) -> str:
    """Liệt kê các file và thư mục trực tiếp trong một thư mục thuộc workspace.
    
    path: Đường dẫn tương đối trong workspace, ví dụ 'data/policies'.
    """
    resolved = resolve_path(path)
    if not resolved.ok:
        return json.dumps({"ok": False, "error": resolved.error}, ensure_ascii=False)

    target: Path = resolved.path
    if not target.exists():
        return json.dumps({
            "ok": False,
            "error": {"code": "DIR_NOT_FOUND", "message": f"Không tìm thấy thư mục: {path}"}
        }, ensure_ascii=False)

    if not target.is_dir():
        return json.dumps({
            "ok": False,
            "error": {"code": "NOT_A_DIRECTORY", "message": f"Đây là file, không phải thư mục: {path}"}
        }, ensure_ascii=False)

    entries = []
    for item in target.iterdir():
        rel_path = item.relative_to(paths.WORKSPACE_DIR).as_posix()
        entries.append({
            "name": item.name,
            "path": rel_path,
            "type": "directory" if item.is_dir() else "file",
        })
    entries.sort(key=lambda x: x["name"])
    return json.dumps({"ok": True, "path": path, "entries": entries}, ensure_ascii=False)
```

---

### 2.2. Kết quả Kiểm thử Tool Trực tiếp (4 trường hợp)

Thực hiện kiểm thử độc lập tool `list_files` với 4 trường hợp biên theo yêu cầu đề bài. Dữ liệu được ghi nhận trực tiếp từ hàm thực thi:

| STT | Trường hợp kiểm thử | Đầu vào `path` | Trạng thái `ok` | Mã lỗi / Kết quả trả về |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **Thư mục hợp lệ** | `data/policies` | `True` | Trả về danh sách gồm các file: `chinh-sach-truoc-10.md`, `chinh-sach-tu-10.md`, `policy-before-oct.md`, `policy-from-oct.md`. Mỗi phần tử có đủ `name`, `path`, `type="file"`. |
| **2** | **Đường dẫn là file** | `data/policies/policy-before-oct.md` | `False` | `code: "NOT_A_DIRECTORY"`, thông báo: *"Đây là file, không phải thư mục: data/policies/policy-before-oct.md"* |
| **3** | **Thư mục không tồn tại** | `data/nonexistent_dir` | `False` | `code: "DIR_NOT_FOUND"`, thông báo: *"Không tìm thấy thư mục: data/nonexistent_dir"* |
| **4** | **Thoát ngoài workspace** | `../../etc` | `False` | `code: "PATH_OUTSIDE_WORKSPACE"`, thông báo: *"Đường dẫn thoát ra ngoài workspace: ../../etc"* |

> **Minh chứng dữ liệu JSON thực tế:** Tệp [`submission/block1/direct_tool_check.json`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block1/direct_tool_check.json) chứa toàn bộ cấu trúc phản hồi chi tiết của 4 ca kiểm thử trên.

---

### 2.3. Thiết kế Skill `refund-policy` và Hướng dẫn Xử lý

Skill `refund-policy` được đặt tại `workspace/skills/refund-policy/` và sao lưu đồng bộ tại `fixtures/skills/refund-policy/`. Cấu trúc bao gồm:
1. **`SKILL.md`:** 
   - Phần Frontmatter chứa metadata chuẩn hóa:
     ```yaml
     ---
     name: refund-policy
     description: Tra cứu và áp dụng chính sách hoàn tiền cho khách hàng dựa trên ngày mua hàng, ngày yêu cầu hoàn tiền và trạng thái kích hoạt sản phẩm. Dùng khi người dùng hỏi về quyền lợi hoàn tiền, tính hợp lệ của yêu cầu hoàn tiền, thời hạn hoàn tiền hoặc mức phí hoàn tiền.
     ---
     ```
   - **Quy tắc kiểm tra thông tin đầu vào:** Bắt buộc phải có đủ 3 trường: (1) Ngày mua hàng, (2) Ngày yêu cầu hoàn tiền (lấy trong câu hỏi, không lấy ngày hệ thống), (3) Trạng thái kích hoạt. Nếu thiếu bất kỳ thông tin nào (đặc biệt là trạng thái kích hoạt), agent **bắt buộc phải hỏi lại**, tuyệt đối **không tự suy đoán/giả định** là "chưa kích hoạt".
   - **Quy trình khám phá động:** Hướng dẫn agent gọi `list_files("data/policies")` để lấy danh sách file thực tế, sau đó đọc từng file bằng `read_file`, đối chiếu ngày mua với phạm vi hiệu lực của chính sách thay vì cố định tên file.
   - **Quy tắc tính toán ngày:** Chênh lệch ngày lịch = `Ngày yêu cầu hoàn - Ngày mua`. Bằng đúng giới hạn vẫn được tính là hợp lệ.
2. **`references/answer-template.md`:**
   - Định dạng câu trả lời chuẩn gồm 5 mục bắt buộc:
     1. Chính sách áp dụng (tên & phạm vi hiệu lực)
     2. Số ngày đã qua
     3. Kết luận (Đủ điều kiện / Không đủ điều kiện)
     4. Phí hoàn tiền (nêu rõ mức phí hoặc không thu phí)
     5. Căn cứ tài liệu (đường dẫn tương đối chính xác đến file chính sách)

---

### 2.4. Phân tích Thực nghiệm & Dẫn chứng Trace

Các kịch bản thực nghiệm được chạy trên `stage-02-skills` với model `gemini-3.5-flash-lite`. Kết quả và vị trí dòng trong trace cụ thể như sau:

#### Trường hợp A: Mua trước ngày đổi chính sách (28/09/2026)
- **Câu hỏi của người dùng:** *"Tôi mua ngày 28/09/2026, yêu cầu hoàn ngày 06/10/2026, chưa kích hoạt. Tôi có được hoàn không?"*
- **File trace:** [`submission/block1/traces/20261007-132834_c128d7d5_turn01_b7c77715.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block1/traces/20261007-132834_c128d7d5_turn01_b7c77715.jsonl)
- **Chuỗi sự kiện và vị trí bằng chứng trong trace:**
  - **Dòng 1 (`user_submitted`):** Nhận câu hỏi từ người dùng.
  - **Dòng 3-5 (`model_response` → `tool_started` → `tool_finished`):** Model nhận diện intent hoàn tiền, gọi `read_file(path='skills/refund-policy/SKILL.md')` để tải hướng dẫn nghiệp vụ.
  - **Dòng 7-9 (`model_response` → `tool_started` → `tool_finished`):** Theo hướng dẫn trong skill, model gọi `list_files(path='data/policies')`. Kết quả trả về danh sách file: `policy-before-oct.md`, `policy-from-oct.md`.
  - **Dòng 11-13 (`model_response` → `tool_started` → `tool_finished`):** Model gọi `read_file(path='skills/refund-policy/references/answer-template.md')` để nắm cấu trúc câu trả lời chuẩn.
  - **Dòng 15-17 (`model_response` → `tool_started` → `tool_finished`):** Dựa vào ngày mua 28/09/2026 (< 01/10/2026), model gọi `read_file(path='data/policies/policy-before-oct.md')` để đọc nội dung chính sách cũ.
  - **Dòng 19-20 (`model_response` → `run_completed`):** Model tổng hợp kết luận:
    - *Chính sách áp dụng:* Chính sách hoàn tiền trước tháng 10 (`data/policies/policy-before-oct.md`).
    - *Số ngày đã qua:* 8 ngày (từ 28/09 đến 06/10).
    - *Kết luận:* **Không đủ điều kiện** hoàn tiền (vượt quá thời hạn 7 ngày theo quy định).
    - *Căn cứ tài liệu:* `data/policies/policy-before-oct.md`.

#### Trường hợp B: Mua từ ngày đổi chính sách sau khi Đổi tên file (02/10/2026)
- **Thao tác chuẩn bị:** Đổi tên hai file chính sách trong `workspace/data/policies/`:
  - `policy-before-oct.md` $\rightarrow$ `chinh-sach-truoc-10.md`
  - `policy-from-oct.md` $\rightarrow$ `chinh-sach-tu-10.md`
- **Câu hỏi của người dùng:** *"Tôi mua ngày 02/10/2026, yêu cầu hoàn ngày 12/10/2026, chưa kích hoạt. Tôi có được hoàn không?"*
- **File trace:** [`submission/block1/traces/20261007-132912_3c29dba0_turn01_95989c32.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block1/traces/20261007-132912_3c29dba0_turn01_95989c32.jsonl)
- **Chuỗi sự kiện và vị trí bằng chứng trong trace:**
  - **Dòng 1 (`user_submitted`):** Nhận câu hỏi từ người dùng trong phiên hội thoại hoàn toàn mới.
  - **Dòng 3-5 (`model_response` → `tool_started` → `tool_finished`):** Model gọi `read_file(path='skills/refund-policy/SKILL.md')`.
  - **Dòng 7-9 (`model_response` → `tool_started` → `tool_finished`):** Model gọi `list_files(path='data/policies')`. Dữ liệu trả về tại dòng 9 phản ánh chính xác các tên file đã đổi:
    ```json
    {"name": "chinh-sach-truoc-10.md", "path": "data/policies/chinh-sach-truoc-10.md", "type": "file"},
    {"name": "chinh-sach-tu-10.md", "path": "data/policies/chinh-sach-tu-10.md", "type": "file"}
    ```
  - **Dòng 11-13 (`model_response` → `tool_started` → `tool_finished`):** Model thông minh chọn và đọc đúng file mới `read_file(path='data/policies/chinh-sach-tu-10.md')` mà không hề gặp lỗi `FILE_NOT_FOUND`.
  - **Dòng 15-17 (`model_response` → `tool_started` → `tool_finished`):** Model đọc `read_file(path='skills/refund-policy/references/answer-template.md')`.
  - **Dòng 19-20 (`model_response` → `run_completed`):** Model đưa ra kết luận:
    - *Chính sách áp dụng:* Chính sách hoàn tiền từ tháng 10 (`data/policies/chinh-sach-tu-10.md`).
    - *Số ngày đã qua:* 10 ngày (từ 02/10 đến 12/10).
    - *Kết luận:* **Đủ điều kiện** hoàn tiền (10 ngày $\le$ 14 ngày, chưa kích hoạt).
    - *Phí hoàn tiền:* Không thu phí (0%).
    - *Căn cứ tài liệu:* `data/policies/chinh-sach-tu-10.md`.

#### Trường hợp Thiếu thông tin (Missing Information Case)
- **Câu hỏi của người dùng:** *"Tôi mua ngày 02/10/2026, muốn hoàn ngày 12/10/2026."* (Khách hàng không cung cấp trạng thái kích hoạt).
- **File trace:** [`submission/block1/traces/20261007-132931_ec90d406_turn01_50a250ca.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block1/traces/20261007-132931_ec90d406_turn01_50a250ca.jsonl)
- **Chuỗi sự kiện và vị trí bằng chứng trong trace:**
  - **Dòng 1 (`user_submitted`):** Nhận câu hỏi thiếu thông tin kích hoạt.
  - **Dòng 3-5 (`model_response` → `tool_started` → `tool_finished`):** Model đọc `skills/refund-policy/SKILL.md`.
  - **Dòng 7-8 (`model_response` → `run_completed`):** Nhận thấy thiếu trạng thái kích hoạt của sản phẩm, theo quy định nghiêm ngặt tại mục 1 của `SKILL.md`, model **ngay lập tức dừng lại và hỏi người dùng**:
    > *"Để kiểm tra chính xác bạn có đủ điều kiện hoàn tiền hay không, vui lòng cho biết: **Sản phẩm của bạn đã được kích hoạt hay chưa?** (Theo quy định, sản phẩm đã kích hoạt sẽ không được hỗ trợ hoàn tiền)."*
  - **Chứng minh:** Model **hoàn toàn không tự tiện giả định** sản phẩm "chưa kích hoạt", không vội vã đưa ra kết luận hoàn tiền.

---

### 2.5. Trả lời Câu hỏi Phân tích Cuối Block 1

#### Câu hỏi 1: Vì sao cần tool để tìm file (`list_files`) và skill để hướng dẫn chọn chính sách?
- **Vai trò của Tool (`list_files`):** 
  - Mô hình ngôn ngữ lớn (LLM) bị cô lập hoàn toàn khỏi hệ điều hành và hệ thống tệp cục bộ (Sandboxed Environment). Mô hình không thể "nhìn thấy" trạng thái hiện thời của ổ đĩa. 
  - Tool `list_files` đóng vai trò là **giác quan quan sát môi trường (Sensory Interface)**, cho phép Agent truy vấn động các thực thể tệp tin đang tồn tại trong thư mục tại thời điểm thực thi (runtime). Nếu không có tool này, agent chỉ có thể phán đoán dựa trên ảo giác (hallucination) hoặc tên file được cung cấp sẵn từ trước.
- **Vai trò của Skill (`refund-policy`):**
  - Tool chỉ cung cấp năng lực kỹ thuật nguyên thủy (Primitive Action - liệt kê file), chứ không biết *khi nào cần liệt kê*, *thư mục nào cần tra cứu*, hay *tiêu chí nghiệp vụ nào dùng để phân định chính sách*.
  - Skill đóng vai trò là **Quy trình chuẩn hóa nghiệp vụ (Standard Operating Procedure - SOP)**. Skill cung cấp tri thức ngữ cảnh (In-context Domain Knowledge): hướng dẫn agent đọc danh mục chính sách, so sánh ngày mua với mốc thời gian chuyển giao hiệu lực (01/10/2026), bắt buộc kiểm tra trạng thái kích hoạt, và định dạng câu trả lời theo đúng mẫu chuẩn.

#### Câu hỏi 2: Nếu agent chưa có tool tìm file, việc sửa prompt có giải quyết được yêu cầu đổi tên file không? Giải thích chi tiết.
- **Khẳng định:** **KHÔNG THỂ.** Việc chỉnh sửa System Prompt đơn thuần hoàn toàn **bất khả thi** trong việc giải quyết vấn đề đổi tên file ở runtime nếu không có tool tìm file.
- **Giải thích chuyên sâu:**
  1. *Tính chất tĩnh của Prompt (Static In-Context Context):* Prompt được đóng gói cố định tại thời điểm khởi tạo phiên làm việc. Prompt chỉ có thể cung cấp các thông tin cố định (hardcoded). Nếu lập trình viên hardcode danh sách tên file cũ (như `policy-before-oct.md`) vào prompt, khi người dùng hoặc hệ thống đổi tên file trên ổ đĩa thành `chinh-sach-truoc-10.md`, agent vẫn sẽ cố gắng gọi `read_file` với tên file cũ và lập tức gặp lỗi `FILE_NOT_FOUND`.
  2. *Thiếu khả năng nhận thức môi trường (Lack of Environmental Grounding):* Prompt Engineering chỉ định hướng cách suy luận và định dạng phản hồi của mô hình. Mô hình không thể "đoán mò" được một chuỗi ký tự ngẫu nhiên hoặc một cấu trúc đặt tên mới do con người vừa thay đổi ngoài hệ thống tệp mà không có kênh thu thập thông tin (I/O Observation).
  3. *Nguyên lý Agentic AI:* Một hệ thống Agentic thực thụ phải dựa trên vòng lặp phản hồi **Perceive $\rightarrow$ Reason $\rightarrow$ Act**. Tool `list_files` chính là bước *Perceive* (Quan sát). Mất bước quan sát này, mọi kỹ thuật prompt engineering đều trở nên vô hiệu trước sự biến động của môi trường thực tế.

---

## 3. BLOCK 2: KIỂM TRA QUÁ TẢI THEO NGƯỜI

### 3.1. Phân tích Stage 03: Tính Tổng Giờ qua Bash & Thuật toán Khử Trùng

Tại `stage-03-bash`, agent được cấp quyền thực thi lệnh thông qua tool `bash`. Mục tiêu là tính tổng số giờ (`hours`) theo từng người phụ trách (`owner`) từ tệp dữ liệu `data/workload.csv`.

#### Phân tích cấu trúc dữ liệu `data/workload.csv`:
```csv
task_id,owner,hours
T01,Lan,4
T02,Lan,5
T03,Minh,3
T04,Minh,abc
T02,Lan,5
T05,,2
```

#### Phân tích các dòng dữ liệu:
- **Dòng 2 (`T01,Lan,4`):** Đầy đủ thông tin, `hours=4` hợp lệ $\rightarrow$ Cộng vào tổng của **Lan**: 4 giờ.
- **Dòng 3 (`T02,Lan,5`):** Lần xuất hiện đầu tiên của task `T02`, đầy đủ thông tin, `hours=5` hợp lệ $\rightarrow$ Cộng vào tổng của **Lan**: $4 + 5 = 9$ giờ.
- **Dòng 4 (`T03,Minh,3`):** Đầy đủ thông tin, `hours=3` hợp lệ $\rightarrow$ Cộng vào tổng của **Minh**: 3 giờ.
- **Dòng 5 (`T04,Minh,abc`):** `hours='abc'` không phải là số hợp lệ $\rightarrow$ **Loại trừ** (lý do: `invalid_hours`).
- **Dòng 6 (`T02,Lan,5`):** `task_id='T02'` đã xuất hiện trước đó tại Dòng 3 $\rightarrow$ **Loại trừ** (lý do: `duplicate_id`).
- **Dòng 7 (`T05,,2`):** `owner` bị để trống $\rightarrow$ **Loại trừ** (lý do: `missing_owner`).

#### Trả lời câu hỏi Stage 03:
- **Nếu tổng của Lan là 14 giờ:** Dòng bị cộng trùng chính là **Dòng 6 (`T02,Lan,5`)**. Do `4 + 5 + 5 = 14`.
- **Nếu tổng của Lan là 9 giờ:** Lệnh Python đã áp dụng cơ chế theo dõi và loại trừ trùng lặp bằng tập hợp `seen_task_ids`:
  ```python
  seen_tasks = set()
  # Trong vòng lặp duyệt từng dòng:
  if task_id in seen_tasks:
      continue  # Loại trừ công việc bị lặp ID
  seen_tasks.add(task_id)
  ```
- **Kết quả chính xác:** **Lan: 9 giờ**, **Minh: 3 giờ**.

---

### 3.2. Mở rộng Script `check_csv.py` và Cập nhật Skill `csv-quality`

Trong `stage-04-script-skill`, script kiểm tra CSV được nâng cấp toàn diện tại `workspace/skills/csv-quality/scripts/check_csv.py` với các yêu cầu kỹ thuật:

1. **Tham số CLI bắt buộc `--max-hours`:**
   - Được phân tích thông qua `argparse`. Giá trị nhận vào phải là số thực hoặc số nguyên hữu hạn không âm (`value >= 0` và `math.isfinite(value)`).
   - Nếu thiếu tham số hoặc giá trị không hợp lệ (ví dụ số âm, chuỗi chữ), script lập tức xuất thông báo lỗi ra `sys.stderr` và trả về `exit code 1` (khác 0).
2. **Quy tắc Khử trùng ID chặt chẽ (First Occurrence Rule):**
   - Mỗi `task_id` không rỗng chỉ giữ lại **lần xuất hiện đầu tiên trong file**. Mọi lần xuất hiện sau đều bị loại bỏ với mã lý do `duplicate_id`, kể cả khi lần đầu tiên có dữ liệu bị lỗi (không thay thế bằng "lần hợp lệ đầu tiên").
3. **Quy tắc Tính tổng giờ (`hours_by_owner`):**
   - Dòng hợp lệ để cộng giờ phải thỏa mãn: đúng 3 cột, `task_id` không rỗng, `owner` không rỗng, không trùng `task_id`, và `hours` là số hữu hạn không âm. Giá trị `0` là hợp lệ.
   - Chỉ lưu các owner có ít nhất 1 dòng được cộng giờ.
4. **Quy tắc Xác định Quá tải (`overloaded_owners`):**
   - Quá tải khi và chỉ khi: $\text{Tổng giờ} > \text{Ngưỡng max\_hours}$ (lớn hơn nghiêm ngặt, bằng ngưỡng không quá tải).
   - Sắp xếp danh sách người quá tải theo thứ tự bảng chữ cái của tên.
5. **Quy tắc Liệt kê Dòng bị loại (`excluded_rows`):**
   - Mỗi dòng dữ liệu không được cộng vào tổng giờ sẽ xuất hiện đúng 1 lần trong `excluded_rows`, sắp xếp theo số thứ tự dòng (`line`).
   - Mã lý do được chuẩn hóa và sắp xếp cố định theo thứ tự ưu tiên:
     `["wrong_field_count", "missing_task_id", "duplicate_id", "missing_owner", "invalid_hours"]`.
6. **Đồng bộ hóa Skill & Template:**
   - `SKILL.md`: Yêu cầu agent kiểm tra sự hiện diện của ngưỡng quá tải trong prompt. Nếu người dùng chưa cung cấp, agent bắt buộc phải hỏi lại; tuyệt đối không dùng ngưỡng của phiên hội thoại cũ.
   - `references/report-template.md`: Chuẩn hóa khung báo cáo gồm 4 phần: (1) Kiểm tra tải công việc (Bảng tổng giờ, Danh sách quá tải, Dòng bị loại), (2) Tổng quan chất lượng dữ liệu, (3) Chi tiết lỗi dữ liệu, (4) Đánh giá và khuyến nghị.

---

### 3.3. Kết quả Chạy Trực tiếp và Trường hợp Biên (Edge Case)

#### 1. Chạy trực tiếp với `data/workload.csv` và `--max-hours 8`:
```bash
uv run python workspace/skills/csv-quality/scripts/check_csv.py --input workspace/data/workload.csv --max-hours 8
```
- **Kết quả JSON:**
  - `max_hours`: 8
  - `hours_by_owner`: `{"Lan": 9, "Minh": 3}`
  - `overloaded_owners`: `[{"owner": "Lan", "total_hours": 9}]` (Lan vượt ngưỡng 8h)
  - `excluded_rows`:
    - Dòng 5 (`T04`): `["invalid_hours"]`
    - Dòng 6 (`T02`): `["duplicate_id"]`
    - Dòng 7 (`T05`): `["missing_owner"]`
- **File kết quả lưu trữ:** [`submission/block2/direct_runs/direct_run_max_hours_8.json`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/direct_runs/direct_run_max_hours_8.json)

#### 2. Chạy trực tiếp với `data/workload.csv` và `--max-hours 9`:
```bash
uv run python workspace/skills/csv-quality/scripts/check_csv.py --input workspace/data/workload.csv --max-hours 9
```
- **Kết quả JSON:**
  - `max_hours`: 9
  - `hours_by_owner`: `{"Lan": 9, "Minh": 3}`
  - `overloaded_owners`: `[]` (Không ai vượt ngưỡng vì Lan có đúng 9h = ngưỡng)
  - `excluded_rows`: Giữ nguyên như trên.
- **File kết quả lưu trữ:** [`submission/block2/direct_runs/direct_run_max_hours_9.json`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/direct_runs/direct_run_max_hours_9.json)

#### 3. Trường hợp Biên Đặc biệt (`data/workload-edge.csv` với `--max-hours 0`):
- **Cấu trúc tệp dữ liệu kiểm thử biên:**
  ```csv
  task_id,owner,hours
  E01,Lan,abc
  E01,Lan,5
  E02,Minh,0
  ```
- **Phân tích chi tiết quy tắc xử lý:**
  - **Dòng 2 (`E01,Lan,abc`):** Lần xuất hiện đầu tiên của task `E01`. `hours='abc'` không hợp lệ $\rightarrow$ Bị loại do `invalid_hours`. ID `E01` được ghi nhận đã xuất hiện!
  - **Dòng 3 (`E01,Lan,5`):** Xuất hiện lại task `E01`. Mặc dù `hours=5` là số hợp lệ, nhưng theo quy tắc bất di bất dịch: *chỉ giữ lần xuất hiện đầu tiên của ID, không thay thế bằng lần hợp lệ đầu tiên*, dòng này **bị loại do `duplicate_id`**. Số giờ `5` của Lan tuyệt đối không được cộng!
  - **Dòng 4 (`E02,Minh,0`):** `hours=0` là số hợp lệ $\rightarrow$ Minh có 0 giờ.
- **Kết quả JSON từ lệnh chạy trực tiếp:**
  ```json
  {
    "max_hours": 0,
    "hours_by_owner": {"Minh": 0},
    "overloaded_owners": [],
    "excluded_rows": [
      {"line": 2, "task_id": "E01", "reasons": ["invalid_hours"]},
      {"line": 3, "task_id": "E01", "reasons": ["duplicate_id"]}
    ]
  }
  ```
  - Chỉ duy nhất Minh có tổng giờ được ghi nhận (0 giờ).
  - Lan không có trong `hours_by_owner` vì không có dòng hợp lệ nào được cộng.
  - Không ai bị quá tải (Minh có 0h = ngưỡng 0h).
- **File kết quả lưu trữ:** [`submission/block2/direct_runs/direct_run_edge_max_hours_0.json`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/direct_runs/direct_run_edge_max_hours_0.json)

---

### 3.4. Bộ Kiểm thử Tự động Pytest

Để bảo đảm tính toàn vẹn và độ tin cậy tuyệt đối của mã nguồn theo chuẩn phát triển phần mềm, một bộ kiểm thử tự động gồm 11 test cases đã được xây dựng tại [`stage-04-script-skill/tests/test_check_csv.py`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/agent-tools-skills-lab/stage-04-script-skill/tests/test_check_csv.py) (sao lưu tại `submission/block2/tests/test_check_csv.py`).

Nội dung bao phủ của bộ kiểm thử:
- `test_missing_max_hours_cli`: Bắt lỗi thiếu tham số CLI `--max-hours`.
- `test_invalid_max_hours_negative`: Bắt lỗi truyền ngưỡng âm (ví dụ: `--max-hours -1`).
- `test_invalid_max_hours_nan`: Bắt lỗi truyền giá trị không phải số.
- `test_normal_workload_max_hours_8`: Kiểm tra tính đúng đắn với dữ liệu mẫu và ngưỡng 8.
- `test_normal_workload_max_hours_9`: Kiểm tra tính đúng đắn với ngưỡng 9 (không ai quá tải).
- `test_edge_case_first_occurrence_invalid_hours`: **Kiểm thử tự động đặc tả quy tắc lần xuất hiện đầu tiên của ID có hours không hợp lệ, không cộng giờ ở lần lặp sau.**
- `test_reason_codes_ordering`: Đảm bảo mảng mã lý do trong `excluded_rows` luôn được sắp xếp theo đúng thứ tự ưu tiên chuẩn.
- `test_nonexistent_file_handling`: Kiểm tra bắt lỗi file không tồn tại.
- `test_missing_required_columns`: Kiểm tra bắt lỗi thiếu cột bắt buộc trong CSV.

> **Kết quả thực thi:** `64 passed in 6.44s` trên toàn stage 04; 100% test cases đều đạt kết quả xuất sắc.

---

### 3.5. Phân tích Thực nghiệm & Dẫn chứng Trace

Các kịch bản thực nghiệm Agent trên `stage-04-script-skill` sử dụng `gemini-3.5-flash-lite`:

#### Kịch bản 1: Ngưỡng 8 giờ
- **Câu lệnh người dùng:** *"Kiểm tra data/workload.csv, người nào vượt 8 giờ? Ghi báo cáo vào output/workload.md."*
- **File trace:** [`submission/block2/traces/20261007-133734_bd25169d_turn01_a42d0f0d.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/traces/20261007-133734_bd25169d_turn01_a42d0f0d.jsonl)
- **Vị trí bằng chứng trong trace:**
  - **Dòng 1:** Người dùng gửi yêu cầu.
  - **Dòng 3-5:** Model gọi `read_file(path='skills/csv-quality/SKILL.md')`.
  - **Dòng 7-9:** Model gọi `read_file(path='skills/csv-quality/references/report-template.md')`.
  - **Dòng 11-13:** Model gọi `bash(command='python skills/csv-quality/scripts/check_csv.py --input data/workload.csv --max-hours 8')`. Script trả về JSON với `exit_code: 0`.
  - **Dòng 15-17:** Model tổng hợp dữ liệu JSON vào template báo cáo và gọi `write_file(path='output/workload.md', content=...)`.
  - **Dòng 19-20:** Model trả lời hoàn tất. Báo cáo tạo ra tại [`submission/block2/reports/workload.md`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/reports/workload.md).

#### Kịch bản 2: Ngưỡng 9 giờ
- **Câu lệnh người dùng:** *"Kiểm tra data/workload.csv với ngưỡng 9 giờ, người nào quá tải? Ghi báo cáo vào output/workload-9h.md."*
- **File trace:** [`submission/block2/traces/20261007-133755_18da6d00_turn01_d2fab8f9.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/traces/20261007-133755_18da6d00_turn01_d2fab8f9.jsonl)
- **Vị trí bằng chứng trong trace:**
  - **Dòng 11-13:** Model thực thi `bash(command='python skills/csv-quality/scripts/check_csv.py --input data/workload.csv --max-hours 9')`.
  - **Dòng 15-17:** Model ghi tệp [`output/workload-9h.md`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/reports/workload-9h.md). Báo cáo ghi nhận: Lan (9 giờ) và Minh (3 giờ) đều trong định mức; danh sách người quá tải là rỗng ("Không có ai vượt ngưỡng 9 giờ").

#### Kịch bản 3: Không cung cấp ngưỡng (Missing Threshold)
- **Câu lệnh người dùng:** *"Tính tổng giờ theo người trong data/workload.csv và xác định người quá tải."*
- **File trace:** [`submission/block2/traces/20261007-133813_30ab43f3_turn01_071ba7cc.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/traces/20261007-133813_30ab43f3_turn01_071ba7cc.jsonl)
- **Vị trí bằng chứng trong trace:**
  - **Dòng 3-5:** Model đọc `skills/csv-quality/SKILL.md`.
  - **Dòng 7-8:** Model tuân thủ nguyên tắc trong skill: *"Nếu yêu cầu kiểm tra quá tải thiếu ngưỡng thì hỏi lại"*. Model không tự tiện chọn ngưỡng mặc định (như 8 hay 40), mà phản hồi hỏi người dùng:
    > *"Vui lòng cung cấp **ngưỡng số giờ tối đa (max_hours)** để xác định người quá tải."*

#### Kịch bản 4: Tệp không tồn tại (Missing File)
- **Câu lệnh người dùng:** *"Kiểm tra data/khong-ton-tai.csv với ngưỡng 8 giờ."*
- **File trace:** [`submission/block2/traces/20261007-133838_5d53453f_turn01_aec246a0.jsonl`](file:///Users/macbook/Documents/HKI_2627/SE373_AgenticAI/BTTH/BTTH5/submission/block2/traces/20261007-133838_5d53453f_turn01_aec246a0.jsonl)
- **Vị trí bằng chứng trong trace:**
  - **Dòng 7-9:** Model chạy lệnh Bash: `python skills/csv-quality/scripts/check_csv.py --input data/khong-ton-tai.csv --max-hours 8`. Lệnh trả về `exit_code: 1` và `stderr: ERROR: Không đọc được file data/khong-ton-tai.csv: [Errno 2] No such file or directory`.
  - **Dòng 11-12:** Model thông báo rõ ràng cho người dùng rằng file không tồn tại và không thể tiến hành phân tích; tuyệt đối không sinh ra bảng tổng giờ giả tạo.

---

### 3.6. Trả lời Câu hỏi Phân tích Cuối Block 2

#### Câu hỏi 1: Phần nào do script tính, phần nào do model diễn giải?
- **Phần do Script (`check_csv.py`) đảm nhiệm (Deterministic Layer):**
  1. *Phân tích cú pháp tệp CSV (Parsing):* Tách dòng, chuẩn hóa chuỗi (strip whitespace), đếm số cột.
  2. *Kiểm tra tính hợp lệ của kiểu dữ liệu (Validation):* Kiểm tra trường rỗng, ép kiểu `hours` sang số thực, kiểm tra số âm/vô hạn/NaN.
  3. *Khử trùng lặp định danh (Deduplication):* Xác định và ghi nhận lần xuất hiện đầu tiên của từng `task_id`; loại bỏ các lần lặp tiếp theo.
  4. *Tính toán số học chính xác (Computation):* Cộng tổng giờ theo từng `owner` (tránh sai số làm tròn hoặc tính nhẩm sai của LLM).
  5. *So sánh ngưỡng logic:* Đối chiếu `total_hours > max_hours`.
  6. *Phân loại và gán nhãn mã lý do:* Xác định danh sách lý do loại trừ và sắp xếp chuẩn hóa.
- **Phần do Model (LLM) đảm nhiệm (Semantic & Cognitive Layer):**
  1. *Hiểu ý định người dùng (Intent Understanding):* Trích xuất đường dẫn tệp mục tiêu và tham số ngưỡng từ ngôn ngữ tự nhiên.
  2. *Kiểm soát điều kiện tiên quyết (Prerequisite Verification):* Nhận biết khi câu hỏi thiếu ngưỡng cần thiết để chủ động hỏi lại người dùng trước khi thực thi.
  3. *Điều phối công cụ (Tool Orchestration):* Đọc tài liệu hướng dẫn (`SKILL.md`), định dạng lệnh CLI chính xác và thực thi qua tool `bash`.
  4. *Diễn giải ngữ nghĩa (Semantic Interpretation):* Đọc cấu trúc JSON kết quả trả về từ script và ánh xạ vào các tiêu đề của bản báo cáo (`output/workload.md`).
  5. *Tổng hợp nhận xét và khuyến nghị (Evaluation & Recommendation):* Viết phần đánh giá chất lượng dữ liệu và đề xuất giải pháp xử lý nhân sự bằng ngôn ngữ tự nhiên lưu loát, chuyên nghiệp.

#### Câu hỏi 2: Nếu sửa script nhưng không cập nhật skill và reference, báo cáo có thể sai hoặc thiếu thông tin gì?
Nếu lập trình viên chỉ cập nhật mã nguồn script mà bỏ quên việc đồng bộ `SKILL.md` và `references/report-template.md`, hệ thống sẽ gặp các lỗi nghiêm trọng sau:
1. **Lỗi thực thi lệnh CLI (Command Failure):** Khi script bổ sung tham số bắt buộc `--max-hours`, nếu `SKILL.md` không được cập nhật cú pháp lệnh, Agent vẫn sẽ gọi script theo cú pháp cũ: `python check_csv.py --input data/workload.csv`. Script sẽ báo lỗi thiếu tham số và thoát với `exit code 1`, khiến Agent không thể hoàn thành nhiệm vụ.
2. **Không biết hỏi lại khi thiếu ngưỡng (Missing Information Hallucination):** Agent không được chỉ dẫn rằng ngưỡng là tham số bắt buộc, dẫn tới việc Agent có thể tự ý "bịa" ra một ngưỡng (ví dụ tự giả định là 8 giờ hoặc 40 giờ một tuần) hoặc thất bại khi gọi lệnh.
3. **Bỏ sót các trường thông tin mới trong báo cáo (Information Loss):** Template báo cáo cũ chỉ có các bảng về chất lượng dữ liệu cơ bản. Nếu template không được cập nhật cấu trúc mới, Agent sẽ bỏ qua các trường JSON giá trị như `hours_by_owner`, `overloaded_owners`, và `excluded_rows`. Bản báo cáo sinh ra sẽ không có bảng tổng giờ theo người, không chỉ ra được ai bị quá tải và không giải thích tại sao các dòng công việc bị loại trừ.
4. **Vi phạm tính nhất quán của hệ thống Agent:** Một Skill hoàn chỉnh là một hợp đồng tương tác (Interface Contract) giữa Agent và môi trường thực thi. Bất kỳ sự lệch pha (mismatch) nào giữa mã nguồn thực thi và hướng dẫn ngữ nghĩa đều dẫn đến sự cố vận hành của toàn bộ quy trình Agentic.

---

## 4. TỔNG KẾT ĐÁNH GIÁ VÀ BÀI HỌC KINH NGHIỆM

1. **Hiệu quả của việc kết hợp Tool Use và Skill Use:** 
   - Tool mở rộng không gian hành động vật lý (Physical Action Space) của Agent trong môi trường máy tính.
   - Skill định hình không gian nhận thức (Cognitive Reasoning Space), thiết lập ranh giới an toàn và quy trình nghiệp vụ rõ ràng.
2. **Nguyên tắc "Code for Determinism, LLM for Semantics":** 
   - Không bao giờ để LLM tự tính toán số học trên tập dữ liệu lớn hoặc phức tạp. Toàn bộ logic cộng trừ, lọc dòng, khử trùng phải được đẩy xuống các script Python xác định (Deterministic Scripts) để đảm bảo độ chính xác 100%.
   - LLM phát huy sức mạnh tối đa ở khâu giao tiếp, điều phối, bắt lỗi người dùng và tổng hợp báo cáo.
3. **Khả năng tự động hóa kiểm thử (Full Test Coverage):**
   - Dự án đã vượt qua 100% các bài kiểm thử unit test và integration test (`218/218` passed across all stages) và chạy thành công trên mô hình thật với vết thực thi minh bạch.
