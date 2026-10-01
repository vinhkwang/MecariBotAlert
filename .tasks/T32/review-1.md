verdict: PASS
summary: OPERATOR.md covers all twelve planned sections. Its claims match the code (UI labels, defaults, system alert texts, rule lifecycle, import dedup by query, backup and restore), and the restore procedure was proven by a real dry run. The README edits match the amended plan. Three minor wording findings remain; none blocks.

findings:
  - id: F1
    severity: minor
    file: OPERATOR.md
    anchor: "Bấm **Save** là lưu vào database, có hiệu lực ngay và giữ qua restart."
    problem: Polling settings are read once per scan cycle (`composition_root.py` reads `polling_settings_service.current_polling_settings` at the start of each cycle), so a save takes effect from the next cycle, not "ngay". An operator who saves mid-cycle and sees no change may think the save failed.
    fix: Replace that line with exactly "Bấm **Save** là lưu vào database, có hiệu lực từ chu kỳ quét kế tiếp và giữ qua restart."

  - id: F2
    severity: minor
    file: OPERATOR.md
    anchor: "Dữ liệu nằm trong volume Docker riêng nên không mất khi cập nhật."
    problem: Compose names the data volume after the project folder (`<folder>_listings-data`). If the operator renames or moves the repo folder, `docker compose up` creates a new empty volume. The bot then starts with no keywords and no dedup history, and looks as if the data was lost.
    fix: Add one sentence directly after the anchor line: "Volume được đặt tên theo tên thư mục repo, nên **không đổi tên hay di chuyển thư mục** này; làm vậy bot sẽ khởi động với database trống. Cần chuyển máy thì sao lưu rồi khôi phục theo mục 9."

  - id: F3
    severity: minor
    file: OPERATOR.md
    anchor: "`https://api.telegram.org/bot<TOKEN>/getUpdates` trong trình duyệt."
    problem: Opening this URL in a browser stores the bot token in the browser history, which conflicts with section 2's own warning that the token is a password.
    fix: At the end of step 2 (after the sentence ending "là chat id."), add: "Xong thì xoá dòng đó khỏi lịch sử trình duyệt, vì URL chứa token."
