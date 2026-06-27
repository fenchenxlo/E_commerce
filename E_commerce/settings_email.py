import os
from dotenv import load_dotenv

# 載入 .env 檔
load_dotenv()

# 選擇郵件服務
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'gmail')

# 郵件共用設定
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')

# 根據不同服務自動設定 HOST
if EMAIL_PROVIDER == 'gmail':
    EMAIL_HOST = 'smtp.gmail.com'

elif EMAIL_PROVIDER == 'yahoo':
    EMAIL_HOST = 'smtp.mail.yahoo.com'

elif EMAIL_PROVIDER == 'outlook':
    EMAIL_HOST = 'smtp.office365.com'

elif EMAIL_PROVIDER == 'icloud':
    EMAIL_HOST = 'smtp.mail.me.com'

elif EMAIL_PROVIDER == 'zoho':
    EMAIL_HOST = 'smtp.zoho.com'

else:
    raise ValueError("EMAIL_PROVIDER 必須是 gmail, yahoo, outlook, icloud, 或 zoho")