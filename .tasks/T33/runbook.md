# T33 runbook

Placeholders: `<vps-ip>`, `<user>`. Run each step, paste the decisive output
back into the session, and wait for a pass/fail before the next step.
Never paste `.env` content, the token or the chat id.

## R1 bootstrap

On your machine:

```bash
scp deploy/bootstrap.sh root@<vps-ip>:/tmp/
ssh root@<vps-ip> 'bash /tmp/bootstrap.sh <user> "<your-ssh-public-key>"'
```

Keep the root session open. In a second terminal:

```bash
ssh <user>@<vps-ip> 'docker run --rm hello-world | head -3; sudo ufw status; timedatectl | grep "Time zone"; swapon --show'
```

Pass: ssh works, hello-world prints, ufw lists only the SSH port, zone is UTC,
`/swapfile` is active.

## R2 checkout

```bash
ssh <user>@<vps-ip>
git clone git@github.com:vinhkwang/MecariBotAlert.git ~/mercari-alert-bot
cd ~/mercari-alert-bot && git log --oneline -1
```

Pass: `git log` shows `3cc8162` or later on `main`. If the clone is refused,
add a read-only deploy key and retry.

## R3 secrets

```bash
cd ~/mercari-alert-bot
cp .env.example .env
nano .env
chmod 600 .env
ls -l .env
```

Pass: `-rw-------`. Do not paste the file.

## R4 start

```bash
docker compose up -d --build
sleep 300
docker compose ps
ss -ltnp | grep 8080
```

From your machine:

```bash
curl -m 5 http://<vps-ip>:8080
```

Pass: `healthy`; listener on `127.0.0.1:8080` only; `curl` fails or times out.

## R5 first run

```bash
ssh -L 8080:127.0.0.1:8080 <user>@<vps-ip>
```

Open `http://127.0.0.1:8080`. Press "Gửi alert thử", then add the production
keyword rules.

Pass: test alert arrives in Telegram; after the first cycle exactly one
initialisation summary arrives and no listing alert.

## R6 backup cron

```bash
cd ~/mercari-alert-bot
./deploy/backup.sh
ls -l backups/
gunzip -c backups/listings-*.db.gz | python3 -c "import sqlite3,sys,tempfile,os; d=sys.stdin.buffer.read(); p=tempfile.mktemp(); open(p,'wb').write(d); print(sqlite3.connect(p).execute('pragma integrity_check').fetchone()[0]); os.remove(p)"
(crontab -l 2>/dev/null; echo '0 3 * * * /home/<user>/mercari-alert-bot/deploy/backup.sh >> /home/<user>/mab-backup.log 2>&1') | crontab -
crontab -l
```

Pass: archive non-empty, integrity check prints `ok`, cron line listed.

## R7 soak sampler

```bash
(crontab -l; echo '0 * * * * (date -u +\%FT\%TZ; free -m; df -h /; docker stats --no-stream; docker compose -f /home/<user>/mercari-alert-bot/docker-compose.yml logs --since 1h | grep -ci error) >> /home/<user>/mab-soak.log 2>&1') | crontab -
crontab -l
```

Pass: both lines listed. After the next full hour, `tail ~/mab-soak.log` shows a
sample. Record the soak start time (UTC).

## During the soak

Once, mid-soak (S6):

```bash
cd ~/mercari-alert-bot && docker compose restart
```

At the end (S1, S2, S5):

```bash
docker inspect -f '{{.RestartCount}}' mercari-alert-bot
docker compose ps
grep -c 'backup ok' ~/mab-backup.log
grep -E 'mercari-alert-bot' ~/mab-soak.log | tail -60
```

Never run `docker compose down -v`.
