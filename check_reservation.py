import asyncio
import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import requests
from playwright.async_api import async_playwright

RESERVATION_URL = "https://reserva.be/ninehours_sleeplab"
SOLD_OUT_TEXT = "満員のため、ご予約できません。"
GIST_ID = "70f068d574416f9864dffa6c5c4b3ed3"
GIST_FILENAME = "last_sent.json"

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


async def check_availability() -> bool:
    """Returns True if the slot is available (not sold out)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.goto(RESERVATION_URL)

        # Click the （男性）30代専用 link
        await page.get_by_text("（男性）30代専用", exact=False).first.click()
        await page.wait_for_load_state("networkidle")

        content = await page.content()
        await browser.close()

    return SOLD_OUT_TEXT not in content


def get_last_sent() -> datetime | None:
    """Fetch last_sent datetime from Gist. Returns None if null or not set."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    gist_data = response.json()
    content = gist_data["files"][GIST_FILENAME]["content"]
    data = json.loads(content)

    last_sent = data.get("last_sent")
    if last_sent is None:
        return None

    return datetime.fromisoformat(last_sent)


def update_last_sent(dt: datetime) -> None:
    """Write the given datetime to the Gist."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps({"last_sent": dt.isoformat()})
            }
        }
    }
    response = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        json=payload,
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()


def send_email() -> None:
    """Send notification email to EMAIL_ADDRESS."""
    msg = MIMEText(
        "9hs（男性）30代専用プランが予約可能です。\n\n"
        f"{RESERVATION_URL}"
    )
    msg["Subject"] = "【9hs】（男性）30代専用 予約可能のお知らせ"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


async def main() -> None:
    print("予約状況を確認中...")
    available = await check_availability()

    if not available:
        print(f"満員のため予約不可。通知なし。")
        return

    print("予約可能！Gistを確認中...")
    last_sent = get_last_sent()
    now = datetime.now(timezone.utc)

    if last_sent is not None:
        # Ensure last_sent is timezone-aware for comparison
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        elapsed = now - last_sent
        print(f"前回通知: {last_sent}  経過: {elapsed}")
        if elapsed < timedelta(days=1):
            print("前回の通知から1日未満のため通知なし。")
            return

    print("メール送信中...")
    send_email()
    print("Gistを更新中...")
    update_last_sent(now)
    print("完了。メール送信・Gist更新済み。")


if __name__ == "__main__":
    asyncio.run(main())
