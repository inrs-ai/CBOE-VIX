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

    subject = f"今日 VIX 指数更新: {price}"
    content = f"北京时间: {current_time}\n当前 CBOE VIX 数值为: {price}"
    
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = Header(f"VIX Bot <{email_from}>", 'utf-8')
    message['To'] = Header(email_to, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')
    
    try:
        # 核心逻辑：根据端口选择连接方式
        if smtp_port == 465:
            # 465 端口必须使用 SMTP_SSL
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            # 587 或 25 端口使用普通 SMTP + starttls
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, email_to, message.as_string())
        server.quit()
        print("Email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, email_from, email_to]):
        print("Error: Missing SMTP environment variables.")
        return

    subject = f"今日 VIX 指数更新: {price}"
    content = f"北京时间: {current_time}\n当前 CBOE VIX 数值为: {price}"
    
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = Header(f"VIX Bot <{email_from}>", 'utf-8')
    message['To'] = Header(email_to, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')
    
    try:
        # 连接 SMTP 服务器
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls() # TLS 安全连接
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, email_to, message.as_string())
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
