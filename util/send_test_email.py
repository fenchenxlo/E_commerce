from django.core.mail import send_mail
from django.conf import settings

def send_test_email(to_email):
    """
    寄送測試郵件給指定收件人
    """
    subject = "Django 測試郵件"
    message = "這是一封使用 Django 郵件設定發送的測試信件。"
    from_email = settings.EMAIL_HOST_USER
    recipient_list = [to_email]

    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
        print(f"✅ 郵件已成功寄到 {to_email}")
    except Exception as e:
        print(f"❌ 郵件寄送失敗: {e}")