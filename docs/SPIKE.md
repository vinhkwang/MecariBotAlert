# Technical Spike Report

Điền file này trước khi viết bất kỳ dòng code sản phẩm nào. Đây là cổng chặn.

Ngày chạy: ____ | Keyword thử: `OMEGA 168.005`

---

## 1. Hai môi trường, chạy cùng một script

| | Local (Hà Nội) | VPS Nhật (____) |
|---|---|---|
| IP / ASN | | |
| Kết quả tổng | ☐ Pass ☐ Fail | ☐ Pass ☐ Fail |
| Tỉ lệ thành công | | |
| Latency p50 | | |
| Latency p95 | | |
| HTTP 200 | | |
| HTTP 403 | | |
| HTTP 429 | | |
| Timeout | | |
| Lỗi parse | | |

Cột quyết định là **VPS Nhật** — đó là nơi bot sẽ chạy thật. Cột local chỉ để
đối chiếu: nếu local fail mà VPS Nhật pass thì vấn đề là IP chứ không phải code,
và ngược lại. Chỉ chạy local rồi kết luận là spike chưa xong.

## 2. Câu hỏi bắt buộc trả lời

| # | Câu hỏi | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Truy cập được search không cần đăng nhập? | | |
| 2 | Ép được thứ tự mới-nhất-trước thật sự? | | so sánh trường `created` |
| 3 | Trích được item id, title, price, url, thumbnail ổn định? | | |
| 4 | Lấy 1–4 ảnh có cần mở trang chi tiết? | | số ảnh search vs detail |
| 5 | Ba môi trường phản hồi khác nhau thế nào? | | bảng trên |
| 6 | Polling gap nào ổn định qua 30–50 chu kỳ? | | |
| 7 | Failure mode nào xuất hiện? | | CAPTCHA / 403 / 429 / timeout / schema |
| 8 | Độ trễ từ lúc đăng đến lúc nhận alert? | | |
| 9 | Tốc độ listing mới mỗi ngày, theo từng keyword? | | suy từ spread của `created` |

Câu 9 quyết định hai thứ: số alert bạn thực sự nhận mỗi ngày, và gap an toàn.

## 3. Tốc độ listing theo keyword

| Keyword | Spread của 30 item đầu | Item/ngày ước tính |
|---|---|---|
| | | |

Tổng ước tính: ____ item/ngày

## 4. Failure mode quan sát được

| Hiện tượng | Tần suất | Cách xử lý trong code sản phẩm |
|---|---|---|
| | | |

## 5. Quyết định

**Nguồn dữ liệu chính:** ☐ HTTP + DPoP ☐ Playwright interception ☐ Proxy site

**Nguồn dự phòng:**

**Polling gap chốt:** ____ giây → latency p95 dự kiến ____ giây

**VPS chốt:** ____ | Chi phí ____/tháng

**Cần proxy JP không:** ☐ Không ☐ Có, chi phí ____/tháng

## 6. Đi tiếp hay dừng

☐ **GO** — lấy được item mới, đúng thứ tự thời gian, ổn định qua 50 chu kỳ, từ
IP của VPS Nhật sẽ dùng thật.

☐ **NO-GO** — chuyển phương án dự phòng, cộng thêm ____ ngày.

Ghi chú:
