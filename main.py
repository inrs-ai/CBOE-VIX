import yfinance as yf
import smtplib
import json
import os
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import pytz

# 1. 获取 VIX 数据
def get_vix_price():
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1d")
        if not hist.empty:
            return round(hist['Close'].iloc[-1], 2)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None
    return None

# 2. 发送邮件
def send_email(price, current_time):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT") or 0)
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, email_from, email_to]):
        print("Error: Missing SMTP environment variables.")
        return

    # 构造更规范的邮件内容
    subject = f"Market Alert: VIX Index Update - {current_time}" # 改变主题，避免纯中文或过于像广告
    body = f"""
    Hello,
    
    This is an automated market data update.
    
    Item: CBOE Volatility Index (VIX)
    Current Value: {price}
    Timestamp: {current_time} (Beijing Time)
    
    ---
    Sent from GitHub Actions Automated Bot.
    """
    
    message = MIMEText(body, 'plain', 'utf-8')
    # 关键：确保 From 这里的格式非常标准
    message['From'] = email_from
    message['To'] = email_to
    message['Subject'] = Header(subject, 'utf-8')
    
    try:
        # 使用 465 端口
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, [email_to], message.as_string())
        server.quit()
        print("Email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")

# 3. 更新本地 JSON 数据
def update_json(price, current_time):
    file_path = 'data.json'
    new_record = {"date": current_time, "value": price}
    
    data = []
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    
    data.insert(0, new_record)
    data = data[:10]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    price = get_vix_price()
    
    if price:
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"Fetched VIX: {price} at {current_time}")
        send_email(price, current_time)
        update_json(price, current_time)
    else:
        print("Failed to get VIX price.")
        exit(1)
