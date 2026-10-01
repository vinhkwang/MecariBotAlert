# Hướng dẫn vận hành

Dành cho người vận hành bot, không cần biết lập trình. Mọi lệnh bên dưới chạy
trong thư mục chứa repo (trên VPS thường là `~/mercari-alert-bot`). Máy cần có
sẵn Docker.

---

## 1. Bot làm gì, không làm gì

Bot quét Mercari Japan theo các từ khoá bạn đặt. Thấy listing mới thì gửi một
tin Telegram kèm ảnh, giá JPY và link. Mỗi item chỉ báo một lần.

Bot **không** đăng nhập Mercari, **không** mua, bình luận hay nhắn người bán,
**không** lọc theo giá. Bạn tự quyết định khi nhận được thông báo.

## 2. Lần đầu cài

1. Tạo bot Telegram: nhắn `/newbot` cho [@BotFather](https://t.me/BotFather),
   làm theo hướng dẫn, lưu lại **token** nó trả về.
2. Lấy **chat id**: nhắn một tin bất kỳ cho bot vừa tạo, rồi mở
   `https://api.telegram.org/bot<TOKEN>/getUpdates` trong trình duyệt. Số nằm
   ở `"chat":{"id": ...}` là chat id.
3. Tạo file cấu hình:

   ```bash
   cp .env.example .env
   nano .env
   ```

   Điền hai dòng `TELEGRAM_BOT_TOKEN=` và `TELEGRAM_CHAT_ID=`. Các dòng khác
   để trống là dùng giá trị mặc định.
4. Khởi động:

   ```bash
   docker compose up -d --build
   ```

**Token là mật khẩu của bot.** Không gửi file `.env` cho ai, không dán token
vào chat, issue hay ảnh chụp màn hình, không commit `.env` lên git. Lộ token thì
vào @BotFather dùng `/revoke` lấy token mới rồi sửa `.env`.

## 3. Mở trang quản lý

Trên máy đang chạy bot: mở `http://127.0.0.1:8080`.

Bot chạy trên VPS: mở một terminal trên máy bạn, chạy

```bash
ssh -L 8080:127.0.0.1:8080 <user>@<vps-ip>
```

giữ nguyên cửa sổ đó, rồi mở `http://127.0.0.1:8080` trên máy bạn. Đóng cửa sổ
SSH là đóng đường vào.

Trang này không có mật khẩu vì nó chỉ nghe ở `127.0.0.1`. **Không bao giờ mở
cổng 8080 ra internet**: ai vào được sẽ sửa được keyword và gửi được tin qua bot
của bạn.

## 4. Quản lý keyword

Trang có bốn khối: **Keywords**, **Polling settings**, **Status**,
**Recent listings**.

Lần đầu khởi động, bot chưa có keyword nào và không quét gì. Thêm keyword ở mục
**Add keyword**: `Name` là tên hiển thị, `Query` là chữ bạn sẽ gõ vào ô tìm kiếm
của Mercari. Mọi thay đổi có hiệu lực từ chu kỳ quét kế tiếp, **không cần
restart**.

| Bạn làm | Bot làm |
|---|---|
| Thêm keyword | Chu kỳ kế tiếp chỉ ghi nhận các item đang có (gọi là *baseline*), **không gửi tin**. Từ chu kỳ sau mới báo item mới. |
| `Edit` đổi `Query` | Baseline cũ không còn đúng nên được ghi nhận lại, không gửi tin cho item đã có. Trang hỏi xác nhận trước. |
| `Edit` chỉ đổi `Name` | Giữ nguyên baseline, quét tiếp như cũ. |
| Bỏ tick `Enabled` | Ngừng quét keyword đó. Tick lại thì quét tiếp, không ghi nhận lại. |
| `Delete` | Ngừng quét. Lịch sử và danh sách item đã thấy vẫn giữ, nên thêm lại sau không bị báo lại item cũ. |
| `Reset baseline` | Ghi nhận lại từ đầu ở chu kỳ kế tiếp, không gửi tin. Dùng khi kết quả có vẻ lệch. |

Cột **Baseline** ghi `Seeds on next cycle` khi keyword đang chờ ghi nhận.

Một item khớp nhiều keyword chỉ gửi **một** tin, liệt kê mọi keyword khớp.

Nút khác trong khối Keywords:

- **Send test alert** — gửi một tin thử qua Telegram. Bấm sau khi cài hoặc khi
  nghi Telegram có vấn đề.
- **Export YAML** — tải danh sách keyword về máy dưới dạng `keywords.yaml`. Giữ
  file này như bản sao lưu dễ đọc.
- **Import YAML** — dán nội dung một file YAML đã export để nạp keyword. Keyword
  có `Query` trùng với keyword đã có sẽ bị bỏ qua.

File `config/keywords.yaml` trong repo chỉ được đọc **một lần**, khi bot khởi
động lần đầu với danh sách trống. Sửa file đó sau này không thay đổi gì, hãy
dùng trang quản lý.

## 5. Polling settings

| Ô | Mặc định | Nghĩa |
|---|---|---|
| Gap between rules (seconds) | 60 | Nghỉ bao lâu giữa hai lần quét keyword. Nhỏ quá dễ bị Mercari chặn. |
| Fetch item detail | bật | Lấy thêm ảnh từ trang chi tiết item. |
| Max images per alert | 4 | Số ảnh tối đa trong một tin (1–10). |
| Consecutive failures before alert | 3 | Một keyword lỗi bao nhiêu lần liên tiếp thì bot báo. |
| System alert cooldown (seconds) | 1800 | Cùng một cảnh báo hệ thống không gửi lại trong khoảng này. |

**Estimated p95 latency** bên dưới form = gap × số keyword đang bật: thời gian
tối đa từ lúc item lên Mercari tới lúc bạn nhận tin. Thêm keyword là con số này
tăng.

Bấm **Save** là lưu vào database, có hiệu lực ngay và giữ qua restart.

## 6. Tin Telegram do bot tự gửi

Ngoài tin báo listing mới, bot gửi ba loại tin hệ thống:

| Tin | Nghĩa | Bạn làm gì |
|---|---|---|
| `Baseline seeded for N rule(s): ... Alerts start next cycle.` | Bình thường. Keyword mới vừa ghi nhận xong. | Không cần làm gì. |
| `Keywords failing repeatedly:` kèm danh sách | Một số keyword lỗi nhiều lần liên tiếp. | Xem mục 7, rồi mục 10. |
| `Every scanned keyword returned zero listings. The Mercari source may be broken.` | **Tất cả** keyword đều không có kết quả. Gần như chắc chắn là bot hỏng hoặc bị chặn, không phải chợ trống. | Xem mục 7, restart, nếu vẫn lặp lại thì báo cho người phát triển. |

Cùng một cảnh báo không gửi lại trong khoảng cooldown nên sự cố kéo dài không
làm ngập Telegram.

## 7. Kiểm tra sức khoẻ

Khối **Status** trên trang cho biết:

- `Last cycle started`, `Last cycle duration` — chu kỳ gần nhất. Nếu thời điểm
  này đứng yên lâu hơn vài lần latency thì bot đã ngừng quét.
- `Rules succeeded / failed` — số keyword chạy được và lỗi trong chu kỳ đó.
- `Consecutive failed cycles` — khác 0 là đang có lỗi.
- `Known listings`, `Last alert sent`.

Giờ trên trang là giờ Việt Nam (ICT).

Từ terminal:

```bash
docker compose ps                 # cột STATUS phải có "healthy"
docker compose logs --since 1h    # log một giờ gần nhất
```

Docker tự kiểm tra bot mỗi 2 phút. Bot mới khởi động có thể hiện `starting`
trong khoảng 1–2 phút đầu, đó là bình thường.

## 8. Sao lưu

```bash
./deploy/backup.sh
```

Tạo `backups/listings-<thời điểm UTC>.db.gz`, an toàn khi bot đang chạy. Bản cũ
hơn 14 ngày tự xoá (đổi bằng `RETAIN_DAYS=30 ./deploy/backup.sh`). Bot phải đang
chạy thì lệnh này mới hoạt động.

Đặt sao lưu hằng ngày lúc 3 giờ sáng (giờ của máy):

```bash
crontab -e
```

thêm dòng (thay `<user>` và đường dẫn cho đúng):

```
0 3 * * * /home/<user>/mercari-alert-bot/deploy/backup.sh >> /home/<user>/mab-backup.log 2>&1
```

Đừng sao lưu bằng cách copy thẳng file database khi bot đang chạy, bản sao có
thể hỏng. Luôn dùng `backup.sh`.

Ngoài ra, thỉnh thoảng bấm **Export YAML** để giữ riêng danh sách keyword.

## 9. Khôi phục từ bản sao lưu

Thay `<file>` bằng tên bản muốn khôi phục trong thư mục `backups/`.

```bash
docker compose stop alert-bot
gunzip -c backups/<file> > restore.db
docker compose run --rm --no-deps -T \
  -v "$PWD/restore.db:/restore/listings.db:ro" \
  --entrypoint sh alert-bot \
  -c 'cp /restore/listings.db /data/listings.db && rm -f /data/listings.db-wal /data/listings.db-shm'
docker compose start alert-bot
rm restore.db
```

Mở trang quản lý, kiểm tra keyword và **Recent listings** đã trở lại. Mọi thứ
xảy ra sau thời điểm sao lưu sẽ mất, nên item nào lên Mercari trong khoảng đó có
thể được báo lại một lần.

## 10. Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Làm gì |
|---|---|---|
| Không nhận được tin nào | Chưa có keyword, hoặc keyword mới còn đang ghi nhận baseline | Xem khối Keywords. Keyword mới cần qua một chu kỳ mới bắt đầu báo. |
| **Send test alert** báo lỗi | Token hoặc chat id sai, hoặc chưa nhắn cho bot lần nào | Kiểm tra `.env`, nhắn một tin cho bot, rồi `docker compose up -d` |
| Bot không khởi động, log báo thiếu `telegram_bot_token` | `.env` thiếu hoặc trống | Làm lại mục 2 bước 3 |
| `docker compose ps` hiện `unhealthy` | Trang quản lý không phản hồi | `docker compose restart`, xem `docker compose logs --since 30m` |
| Mọi keyword lỗi hoặc zero results kéo dài | Mercari đổi cấu trúc, hoặc từ chối IP của máy | Báo cho người phát triển. **Không** tự gắn proxy hay đổi IP liên tục để lách. Đổi nhà cung cấp VPS là quyết định của bạn, không phải sửa code. |
| Máy hết đĩa | Bản sao lưu hoặc log chất đống | `df -h`, xoá bớt `backups/` cũ. Log Docker đã tự giới hạn 50 MB. |
| Thêm keyword xong nhận hàng loạt tin về item cũ | Không được xảy ra | Chụp lại, xuất log, báo cho người phát triển |

Xuất log để gửi người phát triển (log không chứa token):

```bash
docker compose logs --since 24h > bot-log.txt
```

## 11. Cập nhật phiên bản mới

```bash
./deploy/backup.sh
git pull
docker compose up -d --build
```

Dữ liệu nằm trong volume Docker riêng nên không mất khi cập nhật.

## 12. Những điều không được làm

- **Không** chạy `docker compose down -v`. Chữ `-v` xoá toàn bộ database: lịch
  sử, keyword, danh sách item đã thấy. `docker compose down` không có `-v` thì
  an toàn.
- **Không** mở cổng 8080 ra internet, kể cả tạm thời.
- **Không** commit hoặc gửi file `.env`.
- **Không** sửa `config/keywords.yaml` để đổi keyword đang chạy; dùng trang
  quản lý.
- **Không** giảm `Gap between rules` xuống vài giây để nhận tin nhanh hơn. Quét
  dồn dập là cách nhanh nhất để bị Mercari chặn.
