import yfinance as yf
import smtplib
import json
import os
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from datetime import datetime
import pytz

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

def get_status_color(price):
    if price < 20:
        return "#D4EDDA", "#155724"
    elif 20 <= price < 30:
        return "#FFF3CD", "#856404"
    else:
        return "#F8D7DA", "#721C24"

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

    bg_color, text_color = get_status_color(price)

    subject = f"🆕VIX Index Update - {current_time.split(' ')[0]}"
    
    body = f"""
    <div style="font-family: sans-serif; line-height: 1.6; color: #333; padding: 20px; background-color: {bg_color}; border-radius: 8px;">
        <h2 style="color: {text_color}; margin-top: 0;">Market Volatility Report</h2>
        <p style="font-size: 16px;"><b>Item:</b> CBOE Volatility Index (VIX)</p>
        <p style="font-size: 24px; color: {text_color};"><b>Current Value: {price}</b></p>
        <hr style="border: 0; border-top: 1px solid rgba(0,0,0,0.1);">
        <p style="font-size: 12px; color: #666;">Data updated at {current_time} (Beijing Time)</p>
    </div>
    """
    
    message = MIMEText(body, 'html', 'utf-8')
    
    message['From'] = formataddr((str(Header('News Alert', 'utf-8')), email_from))
    message['To'] = email_to
    message['Subject'] = Header(subject, 'utf-8')
    
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, [email_to], message.as_string())
        server.quit()
        print(f"Email sent successfully. (Value: {price})")
    except Exception as e:
        print(f"Error sending email: {e}")

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
