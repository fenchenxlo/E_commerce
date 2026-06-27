from allauth.account.adapter import DefaultAccountAdapter
import base64
import re

class MyAccountAdapter(DefaultAccountAdapter):
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        
        if hasattr(emailconfirmation, 'email'):
            to_addr = emailconfirmation.email
        else:
            to_addr = emailconfirmation.email_address.email
        # 先呼叫原本寄送流程（console backend 會直接印出）
        email = self.render_mail(
            template_prefix='account/email/email_confirmation',
            to=to_addr,
            context=self.get_email_confirmation_context(request, emailconfirmation)
        )
        email.send()  # console backend 會印到 console

        # 解析 email.message() 裡的 base64 內容
        msg = email.message()
        if msg.is_multipart():
            for part in msg.walk():
                cte = part.get('Content-Transfer-Encoding', '')
                if cte.lower() == 'base64':
                    payload = part.get_payload()
                    decoded = base64.b64decode(payload).decode('utf-8')
                    print("=== Decoded Base64 Part ===")
                    print(decoded)
        else:
            if msg.get('Content-Transfer-Encoding', '').lower() == 'base64':
                decoded = base64.b64decode(msg.get_payload()).decode('utf-8')
                print("=== Decoded Base64 ===")
                print(decoded)