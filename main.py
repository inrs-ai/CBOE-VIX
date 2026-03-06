import yfinance as yf
import smtplib
import json
import os
import requests
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from datetime import datetime
import pytz


# ═══════════════════════════ 数据获取 ═══════════════════════════

def get_vix_data():
    """获取 VIX 当前值、前值、变动值"""
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="5d")
        if len(hist) >= 2:
            cur = round(float(hist["Close"].iloc[-1]), 2)
            prev = round(float(hist["Close"].iloc[-2]), 2)
            return cur, prev, round(cur - prev, 2)
        if len(hist) == 1:
            cur = round(float(hist["Close"].iloc[-1]), 2)
            return cur, None, None
    except Exception as e:
        print(f"[VIX] Fetch error: {e}")
    return None, None, None


def get_fear_greed_data():
    """获取 CNN Fear & Greed Index 当前值、前值、变动值、评级"""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        fg = r.json().get("fear_and_greed", {})
        score = fg.get("score")
        if score is None:
            return None, None, None, None
        cur = round(float(score), 1)
        prev_raw = fg.get("previous_close")
        if prev_raw is not None:
            prev = round(float(prev_raw), 1)
            chg = round(cur - prev, 1)
        else:
            prev, chg = None, None
        return cur, prev, chg, fg.get("rating", "")
    except Exception as e:
        print(f"[F&G] Fetch error: {e}")
    return None, None, None, None


# ═══════════════════════ 区间 / 标签辅助 ═══════════════════════

def vix_zone(v):
    """返回 (标签, 颜色, 背景色)"""
    if v is None: return ("--",     "#adb5bd", "#f8f9fa")
    if v < 12:    return ("极度平静", "#2e86de", "#ebf5fb")
    if v < 20:    return ("低波动",   "#27ae60", "#eafaf1")
    if v < 25:    return ("中等波动", "#f39c12", "#fef9e7")
    if v < 30:    return ("较高波动", "#e67e22", "#fdf2e9")
    if v < 40:    return ("高波动",   "#e74c3c", "#fdedec")
    return         ("极端波动", "#c0392b", "#f9ebea")


def fg_zone(v):
    """返回 (标签, 颜色, 背景色)"""
    if v is None: return ("--",     "#adb5bd", "#f8f9fa")
    if v < 25:    return ("极度恐惧", "#c0392b", "#f9ebea")
    if v < 45:    return ("恐惧",     "#e67e22", "#fdf2e9")
    if v < 55:    return ("中性",     "#f39c12", "#fef9e7")
    if v < 75:    return ("贪婪",     "#27ae60", "#eafaf1")
    return         ("极度贪婪", "#2980b9", "#ebf5fb")


# ═══════════════════════ 预警逻辑 ═══════════════════════════════

def build_alerts(vix, fg):
    """
    返回 (level, [(icon, html_text), ...])
    level ∈ {'normal', 'warning', 'extreme'}
    """
    msgs = []
    level = "normal"

    is_warn = (vix is not None and vix > 28) or \
              (fg is not None and (fg < 25 or fg > 75))
    is_extreme = (vix is not None and vix > 50) or \
                 (fg is not None and fg < 10)

    if is_warn:
        level = "warning"
        msgs.append((
            "🔴",
            "短期内市场<b>连续大跌的概率明显上升</b>，建议关注风险敞口。"
        ))

    if is_extreme:
        level = "extreme"
        msgs.append((
            "🟡",
            "市场情绪已达极端水平，往往<b>接近短期底部</b>，"
            "后续 7–30 日的平均回报一般为正。"
        ))

    if not msgs:
        parts = []
        if vix is not None:
            parts.append(f"VIX 处于「{vix_zone(vix)[0]}」区间")
        if fg is not None:
            parts.append(f"F&amp;G Index 处于「{fg_zone(fg)[0]}」区间")
        summary = "，".join(parts) if parts else "暂无数据"
        msgs.append(("📊", f"{summary}，市场情绪整体平稳。"))

    return level, msgs


# ═══════════════════════ HTML 辅助函数 ══════════════════════════

def _chg_html(val, inverse=False):
    """涨跌着色：inverse=True 时上涨为红（用于 VIX）"""
    if val is None:
        return '<span style="color:#adb5bd;">--</span>'
    if val > 0:
        arr, c = "▲", "#e74c3c" if inverse else "#27ae60"
    elif val < 0:
        arr, c = "▼", "#27ae60" if inverse else "#e74c3c"
    else:
        arr, c = "—", "#adb5bd"
    sign = "+" if val > 0 else ""
    return (f'<span style="color:{c};font-weight:700;">'
            f'{arr}&thinsp;{sign}{val}</span>')


def _safe(val, fallback="N/A"):
    return str(val) if val is not None else fallback


# ═══════════════════ 邮件 HTML 构建（卡片式） ══════════════════

def build_email_html(vix_cur, vix_prev, vix_chg,
                     fg_cur, fg_prev, fg_chg, fg_rating,
                     ts):

    level, alerts = build_alerts(vix_cur, fg_cur)

    # ---- 预警横幅配色 ----
    pal = {
        "normal":  ("#eafaf1", "#a3d9a5", "#155724"),
        "warning": ("#fff8e1", "#ffcc02", "#7c6608"),
        "extreme": ("#fce4ec", "#ef5350", "#7f1418"),
    }
    a_bg, a_brd, a_txt = pal[level]

    alert_rows = "".join(
        f'<tr><td style="padding:12px 24px;font-size:14px;'
        f'line-height:1.8;color:{a_txt};">{ic}&nbsp; {tx}</td></tr>'
        for ic, tx in alerts
    )

    # ---- 区间信息 ----
    vl, vc, _ = vix_zone(vix_cur)
    fl, fc, _ = fg_zone(fg_cur)

    # ---- F&G 仪表条 ----
    gauge = ""
    if fg_cur is not None:
        pct = max(0, min(100, int(fg_cur)))
        gauge = f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">
      <tr>
        <td width="{pct}%" style="background:{fc};height:6px;
            border-radius:3px 0 0 3px;font-size:1px;">&nbsp;</td>
        <td width="{100 - pct}%" style="background:#e9ecef;height:6px;
            border-radius:0 3px 3px 0;font-size:1px;">&nbsp;</td>
      </tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:5px;">
      <tr>
        <td style="font-size:10px;color:#b0b8c4;">0 极度恐惧</td>
        <td align="right" style="font-size:10px;color:#b0b8c4;">极度贪婪 100</td>
      </tr>
    </table>"""

    # ---- 完整 HTML ----
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f5;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,
  'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;">
<tr><td align="center" style="padding:32px 12px;">
<table width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;border-collapse:separate;border-spacing:0;">

<!-- ===== HEADER ===== -->
<tr><td style="background-color:#302b63;
  background:linear-gradient(135deg,#0f0c29 0%,#302b63 50%,#24243e 100%);
  border-radius:16px 16px 0 0;padding:36px 32px;text-align:center;">
  <p style="margin:0;font-size:24px;font-weight:800;color:#fff;">
    📊&ensp;市场情绪日报</p>
  <p style="margin:8px 0 0;font-size:12px;color:rgba(255,255,255,.45);
    letter-spacing:3px;">MARKET&ensp;SENTIMENT&ensp;REPORT</p>
</td></tr>

<!-- ===== ALERT BAR ===== -->
<tr><td style="background:{a_bg};border-left:5px solid {a_brd};padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0">{alert_rows}</table>
</td></tr>

<!-- ===== CARD AREA ===== -->
<tr><td style="background:#ffffff;padding:28px 24px 12px;">

  <!-- ─── VIX Card ─── -->
  <table width="100%" cellpadding="0" cellspacing="0"
    style="background:#fafbfc;border-radius:12px;
    border:1px solid #eaecf0;margin-bottom:20px;">
  <tr><td style="padding:24px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <p style="margin:0;font-size:11px;color:#8a94a6;font-weight:700;
          text-transform:uppercase;letter-spacing:1.5px;">
          CBOE Volatility Index</p>
        <p style="margin:3px 0 0;font-size:12px;color:#b0b8c4;">
          VIX · 恐慌指数</p>
      </td>
      <td align="right" valign="top">
        <span style="display:inline-block;background:{vc};color:#fff;
          font-size:11px;font-weight:700;padding:4px 14px;
          border-radius:20px;">{vl}</span>
      </td>
    </tr></table>

    <p style="margin:18px 0 0;line-height:1;">
      <span style="font-size:44px;font-weight:900;color:#1a1f36;
        letter-spacing:-2px;">{_safe(vix_cur)}</span>
      <span style="font-size:16px;margin-left:12px;
        vertical-align:middle;">{_chg_html(vix_chg, inverse=True)}</span>
    </p>
    <p style="margin:10px 0 0;font-size:13px;color:#8a94a6;">
      前值：<b style="color:#4a5568;">{_safe(vix_prev, '--')}</b></p>
  </td></tr></table>

  <!-- ─── F&G Card ─── -->
  <table width="100%" cellpadding="0" cellspacing="0"
    style="background:#fafbfc;border-radius:12px;
    border:1px solid #eaecf0;margin-bottom:8px;">
  <tr><td style="padding:24px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <p style="margin:0;font-size:11px;color:#8a94a6;font-weight:700;
          text-transform:uppercase;letter-spacing:1.5px;">
          Fear &amp; Greed Index</p>
        <p style="margin:3px 0 0;font-size:12px;color:#b0b8c4;">
          CNN · 恐惧与贪婪指数</p>
      </td>
      <td align="right" valign="top">
        <span style="display:inline-block;background:{fc};color:#fff;
          font-size:11px;font-weight:700;padding:4px 14px;
          border-radius:20px;">{fl}</span>
      </td>
    </tr></table>

    <p style="margin:18px 0 0;line-height:1;">
      <span style="font-size:44px;font-weight:900;color:#1a1f36;
        letter-spacing:-2px;">{_safe(fg_cur)}</span>
      <span style="font-size:16px;margin-left:12px;
        vertical-align:middle;">{_chg_html(fg_chg)}</span>
    </p>
    <p style="margin:10px 0 0;font-size:13px;color:#8a94a6;">
      前值：<b style="color:#4a5568;">{_safe(fg_prev, '--')}</b></p>
    {gauge}
  </td></tr></table>

</td></tr>

<!-- ===== FOOTER ===== -->
<tr><td style="background:#fff;border-radius:0 0 16px 16px;
  padding:0 24px 28px;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td style="border-top:1px solid #f0f2f5;padding-top:18px;
      text-align:center;">
      <p style="margin:0;font-size:12px;color:#b0b8c4;">
        Data updated at {ts} (Beijing Time)</p>
      <p style="margin:6px 0 0;font-size:11px;color:#ced4da;">
        For reference only. Not investment advice.</p>
    </td>
  </tr></table>
</td></tr>

</table>
</td></tr></table>
</body></html>"""


# ═══════════════════════ 发送 / 保存 ═══════════════════════════

def send_email(html_body, current_time):
    smtp_host  = os.getenv("SMTP_HOST")
    smtp_port  = int(os.getenv("SMTP_PORT") or 0)
    smtp_user  = os.getenv("SMTP_USER")
    smtp_pass  = os.getenv("SMTP_PASS")
    email_from = os.getenv("EMAIL_FROM")
    email_to   = os.getenv("EMAIL_TO")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass,
                email_from, email_to]):
        print("Error: Missing SMTP environment variables.")
        return

    date_str = current_time.split(" ")[0]
    subject = f"🦊Daily Sentiment Report – {date_str}"

    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = formataddr(
        (str(Header("Market Flash", "utf-8")), email_from))
    msg["To"] = email_to
    msg["Subject"] = Header(subject, "utf-8")

    try:
        if smtp_port == 465:
            srv = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            srv = smtplib.SMTP(smtp_host, smtp_port)
            srv.starttls()
        srv.login(smtp_user, smtp_pass)
        srv.sendmail(email_from, [email_to], msg.as_string())
        srv.quit()
        print("✅ Email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")


def update_json(price, current_time):
    file_path = "data.json"
    new_record = {"date": current_time, "value": price}
    data = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    data.insert(0, new_record)
    data = data[:10]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ══════════════════════════ 主入口 ══════════════════════════════

if __name__ == "__main__":
    vix_cur, vix_prev, vix_chg = get_vix_data()
    fg_cur, fg_prev, fg_chg, fg_rat = get_fear_greed_data()

    if vix_cur is None and fg_cur is None:
        print("Failed to fetch any market data.")
        exit(1)

    beijing_tz = pytz.timezone("Asia/Shanghai")
    now_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

    print(f"VIX  → current={vix_cur}  previous={vix_prev}  change={vix_chg}")
    print(f"F&G  → current={fg_cur}  previous={fg_prev}  "
          f"change={fg_chg}  rating={fg_rat}")

    html = build_email_html(
        vix_cur, vix_prev, vix_chg,
        fg_cur, fg_prev, fg_chg, fg_rat,
        now_str,
    )
    send_email(html, now_str)

    if vix_cur is not None:
        update_json(vix_cur, now_str)

    print("✅ Done.")
