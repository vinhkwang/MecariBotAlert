# Đặc tả UI settings

Nguyên tắc: đơn giản. Một trang, không framework, không build step. Vanilla JS
gọi JSON API, FastAPI phục vụ static. Không có npm trong dự án này.

Mặc định bind `127.0.0.1:8080`. Không xác thực, vì không expose ra ngoài. Muốn
truy cập từ xa thì SSH tunnel:

```
ssh -L 8080:127.0.0.1:8080 user@vps
```

## Bốn khối trên trang

### 1. Keywords

Đây là khối quan trọng nhất của UI. Keyword là dữ liệu chạy, không phải cấu
hình cố định: thêm, sửa, xoá, bật/tắt bất cứ lúc nào, có hiệu lực từ chu kỳ
quét kế tiếp, **không cần restart**.

Bảng: tên, query, bật/tắt, số item đã phát hiện, lần cuối thấy item mới.
Thao tác: thêm, sửa, xoá, bật/tắt, reset baseline cho một rule.

Vòng đời của một rule:

| Hành động | Hệ quả |
|---|---|
| Thêm rule mới | Chu kỳ kế tiếp seed baseline riêng cho rule đó, **không bắn alert**. Từ chu kỳ sau mới báo item mới. |
| Sửa `query` | Baseline cũ mô tả một tìm kiếm khác nên tự động seed lại. UI phải báo trước điều này. |
| Sửa tên hiển thị | Không đụng baseline. |
| Tắt rule | Ngừng quét, giữ nguyên baseline và lịch sử. Bật lại thì chạy tiếp, không seed lại. |
| Xoá rule | Giữ lịch sử listing và giữ item ID trong bảng dedup, để thêm lại sau không phát lại alert cũ. |
| Reset baseline thủ công | Seed lại, không bắn alert. Cần hộp thoại xác nhận vì dễ bấm nhầm. |

Rule mới **phải** được seed riêng. Không có bước này thì mỗi lần thêm keyword
sẽ bắn hàng chục alert cùng lúc về các item đã tồn tại từ lâu.

### 2. Polling settings

Gap giây giữa các rule, page size, bật/tắt fetch detail, số ảnh tối đa mỗi
alert, ngưỡng lỗi liên tiếp trước khi cảnh báo, cooldown cảnh báo.

Hiển thị ngay dưới form: latency p95 ước tính = gap × số rule đang bật. Người
dùng phải thấy hậu quả của con số mình vừa gõ.

### 3. Status

Chu kỳ gần nhất chạy lúc nào, mất bao lâu, bao nhiêu rule thành công / thất bại,
chuỗi lỗi liên tiếp hiện tại, tổng số item đã biết, thời điểm alert gần nhất.

### 4. Recent listings

20 item phát hiện gần nhất: ảnh thumbnail, tiêu đề, giá JPY, rule khớp, giờ ICT,
link. Trạng thái gửi theo từng kênh.

## API

| Method | Path | Việc |
|---|---|---|
| GET | `/api/keywords` | danh sách rule |
| POST | `/api/keywords` | tạo rule |
| PATCH | `/api/keywords/{id}` | sửa hoặc bật/tắt |
| DELETE | `/api/keywords/{id}` | xoá rule |
| POST | `/api/keywords/{id}/reset-baseline` | seed lại rule |
| GET | `/api/settings` | polling settings |
| PUT | `/api/settings` | cập nhật |
| GET | `/api/status` | sức khoẻ hệ thống |
| GET | `/api/listings?limit=20` | listing gần đây |
| POST | `/api/actions/test-notification` | bắn alert thử |
| POST | `/api/actions/import-yaml` | nạp seed từ YAML |
| GET | `/api/actions/export-yaml` | xuất cấu hình hiện tại |
| GET | `/healthz` | cho Docker healthcheck |

## Ràng buộc kiến trúc

Controller chỉ làm ba việc: validate input, gọi **một** application service, map
kết quả sang response schema.

- Không có logic nghiệp vụ trong controller.
- Không có SQL trong controller.
- Controller không import `infrastructure`, chỉ import `application`.
- Request và response schema là lớp riêng trong `web/schemas/`, không dùng lại
  domain model làm response — domain đổi thì API không được vỡ theo.
- Không endpoint nào trả về `TELEGRAM_BOT_TOKEN` hay `TELEGRAM_CHAT_ID`, kể cả
  dạng che một phần. Có test khẳng định điều này.

## Thay đổi so với spec gốc

Keyword chuyển từ YAML sang SQLite làm nguồn sự thật. `config/keywords.yaml`
chỉ còn là seed nạp lần đầu và là đích export. Lý do: sửa YAML từ trình duyệt
rồi reload process là kiến trúc tồi, còn hai nguồn sự thật thì sẽ lệch nhau.

`KeywordRuleProvider` port giữ nguyên, chỉ đổi implementation từ YAML sang
SQLite. Đây đúng là thứ Repository pattern sinh ra để làm.
