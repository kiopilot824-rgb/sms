import os
import re
import time
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

TEXTBELT_URL = "https://textbelt.com/text"
TEXTBELT_STATUS_URL = "https://textbelt.com/status"
TEXTBELT_KEY = os.getenv("TEXTBELT_KEY", "textbelt")

# Simple per-process protection against accidental repeated clicks/abuse.
# This is not a replacement for a real distributed rate limiter.
last_send_by_ip = {}
COOLDOWN_SECONDS = int(os.getenv("SEND_COOLDOWN_SECONDS", "15"))

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/send")
def send():
    phone = request.form.get("phone", "").strip().replace(" ", "")
    message = request.form.get("message", "").strip()

    if not phone or not message:
        return render_template("index.html", error="شماره و پیام الزامی است.")

    if not PHONE_RE.fullmatch(phone):
        return render_template(
            "index.html",
            error="شماره را با فرمت بین‌المللی وارد کنید؛ مثال: +989121234567",
        )

    if len(message) > 500:
        return render_template("index.html", error="پیام خیلی طولانی است.")

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    client_ip = client_ip.split(",")[0].strip()
    now = time.time()
    previous = last_send_by_ip.get(client_ip, 0)

    if now - previous < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - previous)) + 1
        return render_template(
            "index.html",
            error=f"لطفاً {remaining} ثانیه صبر کنید و دوباره تلاش کنید.",
        )

    try:
        response = requests.post(
            TEXTBELT_URL,
            data={"phone": phone, "message": message, "key": TEXTBELT_KEY},
            timeout=30,
        )
        try:
            result = response.json()
        except ValueError:
            return render_template(
                "index.html",
                error=f"Textbelt پاسخ JSON معتبر برنگرداند (HTTP {response.status_code}).",
            )
    except requests.RequestException as exc:
        return render_template(
            "index.html",
            error=f"خطا در ارتباط با Textbelt: {exc}",
        )

    if not result.get("success"):
        return render_template(
            "index.html",
            error=result.get("error", "Textbelt درخواست را نپذیرفت."),
            result=result,
        )

    last_send_by_ip[client_ip] = now

    return render_template(
        "index.html",
        success=True,
        text_id=result.get("textId"),
        quota=result.get("quotaRemaining"),
        result=result,
    )


@app.get("/status/<text_id>")
def status(text_id):
    # Textbelt documents GET /status/<textId>.
    try:
        response = requests.get(
            f"{TEXTBELT_STATUS_URL}/{text_id}",
            timeout=15,
        )
        result = response.json()
    except (requests.RequestException, ValueError):
        return {"error": "Could not read Textbelt status."}, 502

    return result, response.status_code


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
