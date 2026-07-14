# KẾ HOẠCH TRIỂN KHAI TỔNG HỢP (HỆ THỐNG AUTO-BET & CÁC TÍNH NĂNG CHƯA HOÀN THÀNH)

Tài liệu này là nơi lưu trữ **duy nhất** toàn bộ kế hoạch, đặc tả kỹ thuật và danh sách các công việc chưa thực hiện của dự án. Tất cả các ghi chú cũ từ `notes.md`, `plan-update.md` và `trung_nhau.md` đã được hợp nhất tại đây để tránh trùng lặp.

---

## 1. Tự động đặt cược (Auto-Bet) bằng Tampermonkey
* **Mô tả:** Triển khai script Tampermonkey chạy trên trình duyệt của người dùng để giả lập hành vi click đặt cược thật dựa trên phân tích từ Bot local.

### 1.1 Sơ đồ hoạt động (Flow)
```mermaid
sequenceDiagram
    participant Bot as Bot Python (Local)
    participant TM as Script Tampermonkey
    participant Game as Trang web Game (EE88)
    
    TM->>Bot: 1. Lấy dữ liệu dự đoán (/api/predictions)
    Bot-->>TM: Trả về dự đoán (ví dụ: MUA LẺ, tiền cược: 300k)
    TM->>Game: 2. Kiểm tra kỳ hiện tại trên giao diện có khớp không
    alt Khớp kỳ & Chưa cược kỳ này
        TM->>Game: 3. Click nút chọn cửa cược (ví dụ: "Lẻ")
        TM->>Game: 4. Điền số tiền cược vào ô "Cược đơn" (300,000)
        TM->>Game: 5. Click nút "Đặt Cược" để hoàn tất lệnh cược thật
        TM->>TM: Đánh dấu kỳ này đã cược xong
    end
```

### 1.2 Các bước triển khai chi tiết
* **Bước 1: Xây dựng Endpoint API hỗ trợ Auto-Bet trên Bot**
  Tạo endpoint `GET /api/next-action` trả về thông tin cược sẵn sàng cho kỳ tiếp theo:
  ```json
  {
    "status": "success",
    "issue": "202607080432",
    "parity": { "decision": "MUA LẺ", "amount": 300000 },
    "size": { "decision": "BỎ QUA", "amount": 0 }
  }
  ```
* **Bước 2: Tích hợp logic tìm nút và đặt cược vào Script Tampermonkey**
  Script sẽ tìm các phần tử HTML trên trang game theo cấu trúc mẫu:
  1. **Nút chọn cửa:** Tìm các thẻ chứa chữ "Lẻ", "Chẵn", "Tài", "Xỉu" trong phần "Kèo đôi".
     * *Selector dự kiến:* `//div[contains(text(), 'Kèo đôi')]/..//span[contains(text(), 'Lẻ')]` (dùng XPath hoặc ClassName cụ thể).
  2. **Ô nhập tiền cược:** Tìm ô Input kế bên nhãn "Cược đơn:".
  3. **Nút đặt cược:** Tìm nút màu xanh ở góc phải chứa chữ "Đặt Cược".
* **Bước 3: Cơ chế chống cược lặp (Double Bet Prevention)**
  Script lưu trạng thái `last_bet_issue = "202607080432"` vào `localStorage` của trình duyệt. Chỉ đặt cược nếu `Kỳ tiếp theo trên game == Kỳ dự đoán` và `Kỳ dự đoán != last_bet_issue`.

### 1.3 Quy trình nghiệm thu & Kiểm thử an toàn
1. **Chạy thử nghiệm ở chế độ hiển thị (Dry-Run):** Script chỉ tự động Click chọn cửa và điền số tiền, nhưng **KHÔNG** click nút "Đặt cược" để người dùng kiểm tra xem script đã click và điền đúng tiền cược chưa.
2. **Chạy thật:** Sau khi người dùng xác nhận Dry-run chuẩn xác, kích hoạt tự động Click nút "Đặt cược".

---

## 2. Quản lý vốn và Chiến thuật theo thời gian (Money Management & Time Strategy)

### 2.1 Cấu hình khung giờ chạy Bot (Time-based Restrictions)
Tự động điều chỉnh mức độ tự tin (Confidence Level) và tiền cược dựa trên thời gian thực tế:
* **Khung giờ thuận lợi (Có lợi/Ưu tiên cược):**
  * `10:00 - 12:00` (Trưa)
  * `15:00 - 16:00` (3h - 4h chiều)
* **Khung giờ bất lợi (Rủi ro/Hạn chế hoặc tạm dừng cược):**
  * `19:30 - 21:00` (7h30 - 9h tối)

### 2.2 Logic đặt cược thông minh theo Tỷ lệ thắng (Dynamic Bet Sizing)
* **Vòng có tỷ lệ cao:** Thêm logic phân tích xác suất. Đánh cược mạnh, ưu tiên dồn vốn vào những vòng có tỷ lệ thắng cao được dự đoán để mang lợi nhuận lớn về.
* **Cơ chế bỏ qua:** Nếu vòng đấu không đạt ngưỡng tỷ lệ an toàn tối thiểu -> Bỏ qua hoàn toàn (Skip), không vào tiền để bảo toàn vốn.

---

## 3. Khắc phục lỗi hoạt động không ổn định sau 10 phút chờ (Idling Bug)
* **Mô tả hành vi lỗi:** Sau khi hệ thống ngưng hoạt động khoảng 10 phút (Idling), ở lần cược thứ 1, 2, 3, 4 ngay sau khi chạy lại, hệ thống mất khả năng tự động tính toán chính xác dữ liệu/số tiền cược.
* **Cách sửa đề xuất:** Trong `place_demo_bet` (bets_mixin.py), sau khi lấy `pause_until`, thêm kiểm tra:
  ```python
  if pause_until is not None and time.time() >= pause_until:
      pause_until = None
  ```
  Đồng thời, đảm bảo `is_market_stable` chỉ trả về False khi thực sự không ổn định (WR trượt 30 phiên < 45%), không bị ảnh hưởng bởi pause.

---

## 4. Tự động tạm dừng khi gặp chuỗi thua (Circuit Breaker)
* **Yêu cầu:** Thiết lập cơ chế tự động tạm dừng (Circuit Breaker) khi Win Rate của 30 phiên gần nhất tụt dưới 55% để bảo vệ tài khoản khỏi khủng hoảng chuỗi thua dài.

---

## 5. Rà soát chéo đồng thuận giữa 2 Engine (Consensus Cross-check)
* **Yêu cầu:** Viết hàm kiểm tra chéo (Cross-check) trước khi đặt cược nâng tiền để đảm bảo 2 engine (Gemini & Heuristics) thực sự đồng thuận trên cùng một bộ dữ liệu mới nhất, tránh việc sai lệch phiên hoặc cache kết quả cũ.

---

## 6. Đánh dấu nguồn gốc dự đoán (Prediction Tagging) trong Log cược
* **Yêu cầu:** Các lệnh cược khi xuất ra log console/tập tin đặt cược phải được đánh dấu rõ ràng nguồn gốc:
  * Tag `[Gemini]` nếu chỉ Gemini chọn.
  * Tag `[Heuristics]` nếu chỉ Heuristics chọn.
  * Tag `[Combined]` nếu cả hai engine đồng thuận.

---

## 7. Triển khai API `/api/health` & Giám sát chạy ngầm
* **Yêu cầu:** Xây dựng tính năng Health Check chạy ngầm kiểm tra sức khỏe của các API và trạng thái bot. Hệ thống sẽ không ghi log thường lệ khi hoạt động bình thường, chỉ xuất log cảnh báo khi có lỗi.
