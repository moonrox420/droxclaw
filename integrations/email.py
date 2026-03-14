import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
from langchain_core.tools import tool

class EmailIntegration:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp-mail.outlook.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.email = os.getenv("EMAIL_ADDRESS")
        self.password = os.getenv("EMAIL_PASSWORD")
        
        if not all([self.email, self.password]):
            raise ValueError("Email credentials not found in environment variables")
            
    @tool
    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = to
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email, self.password)
            server.send_message(msg)
            server.quit()
            
            return f"Email sent to {to}"
        except Exception as e:
            return f"Error sending email: {str(e)}"

def get_email_tools():
    """Return email tools for the agent"""
    try:
        email_integration = EmailIntegration()
        return [email_integration.send_email]
    except Exception as e:
        print(f"Email integration failed: {e}")
        return []
