# Mercari JP New-Listing Alert Bot

Phát hiện listing mới trên Mercari Japan theo từ khoá, đẩy thông báo Telegram
kèm ảnh, giá và link. Có UI local để quản lý keyword và xem sức khoẻ hệ thống.

Không đăng nhập. Không tài khoản Mercari. Không mua tự động.

---

## Đọc theo thứ tự

| File | Nội dung |
|---|---|
| `CLAUDE.md` | Hiến pháp của repo. Mọi agent đọc trước khi chạm code. |
| `docs/TASKS.md` | Task board. 34 task, wave nào chạy song song được. |
| `docs/WORKFLOW.md` | Vòng lặp một task, chạy song song, giao thức merge. |
| `docs/SPIKE.md` | Cổng chặn. Điền xong mới được code. |
| `docs/UI.md` | Đặc tả UI và JSON API. |
| `docs/VPS.md` | Cấu hình VPS, chọn nhà cung cấp, hardening. |
| `docs/PLAN.md` | Đánh giá khả thi, estimate, chi phí. |
| `OPERATOR.md` | Hướng dẫn vận hành cho người không phải dev. |

## Keyword

Keyword **không nằm trong code và không cố định**. Chúng là dữ liệu chạy, lưu
trong SQLite, thêm/sửa/xoá/bật/tắt từ UI bất cứ lúc nào và có hiệu lực từ chu
kỳ quét kế tiếp mà không cần restart.

`config/keywords.yaml` mặc định rỗng (`keywords: []`) — bot khởi động không quét
gì, bạn tự thêm trong UI. File đó chỉ là seed nạp lần đầu khi bảng còn trống, và
là đích export khi bạn muốn sao lưu cấu hình.

`config/keywords.example.yaml` chỉ để xem cấu trúc, không bao giờ được nạp.

Rule mới thêm lúc nào cũng được seed baseline riêng, nên nó **không bắn hàng
chục alert** về các item đã tồn tại từ trước. Chi tiết vòng đời rule ở
`docs/UI.md`.

## Bắt đầu

```bash
chmod +x deploy/*.sh .claude/hooks/*.sh
git init && git add . && git commit -m "chore: add project charter and scaffolding"
git remote add origin <your-repo-url> && git push -u origin main
cp .env.example .env          # điền TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID
claude
```

Bước `chmod` bắt buộc: git giữ exec bit nhưng file tải về thì không, và hook
không chạy được sẽ âm thầm vô hiệu hoá toàn bộ lớp bảo vệ bên dưới.

## Thư mục `.claude`

```
.claude/
  settings.json          quyền hạn + đăng ký hook, commit vào repo
  settings.local.json    cấu hình riêng của bạn, đã gitignore
  commands/              10 slash command
  hooks/guard-git.sh     chặn cứng các thao tác phá hoại
```

`settings.json` cho phép sẵn các lệnh đọc và test nên agent không hỏi xin phép
mỗi lần chạy `make test` hay `git diff`. Nó chặn `git merge`, `gh pr merge`,
force push, `git reset --hard`, `docker compose down -v` và đọc file `.env`.
Nhóm `ask` vẫn hỏi với `docker`, `pip install`, `ssh`, `scp`.

`guard-git.sh` là chốt chặn thật. Từng có báo cáo `permissions.deny` không được
thực thi đúng ở một số phiên bản Claude Code, nên quy tắc quan trọng nhất —
**agent không bao giờ merge** — được chặn thêm bằng PreToolUse hook. Hook trả
exit 2 thì lệnh bị huỷ và agent nhận được lý do. Nó cũng chặn commit khi đang
đứng trên `main`.

Một điểm cần biết: subagent có thể không kế thừa hook và permission từ
`settings.json`. Đừng coi lớp này là tường thành — nó bắt lỗi do sơ ý, không
chống được một agent cố tình lách.

Trong Claude Code:

```
/spike            chạy trước tất cả, điền docs/SPIKE.md, tick GO
/next-task        chọn task, tạo branch, lập plan  -> bạn duyệt
/implement T01
/verify
/review T01
/finish T01                                        -> bạn review và merge
```

`/status` cho biết task nào đang chạy, task nào bắt đầu được ngay.

## Chuẩn bị trước khi code

- [ ] Telegram bot qua @BotFather, lấy token
- [ ] Chat id (nhắn cho bot rồi gọi `getUpdates`)
- [ ] VPS **đặt tại Nhật** — xem `docs/VPS.md` để chọn nhà cung cấp và cấu hình
- [ ] Chạy spike từ chính VPS đó, không chỉ từ máy local

## Lệnh local

```bash
make install      # cài deps + pre-commit hook
make gates        # lint + type + test, cổng chất lượng
make ui-dev       # UI reload tại http://127.0.0.1:8080
make run          # chạy cả scanner lẫn UI
make cov          # báo cáo coverage
```

## Vận hành

Khởi động, theo dõi, sao lưu, khôi phục và xử lý sự cố: xem `OPERATOR.md`.
Việc tạo VPS nằm ở `docs/VPS.md`.
