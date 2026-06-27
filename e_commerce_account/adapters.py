from allauth.account.adapter import DefaultAccountAdapter
import base64

class MyAccountAdapter(DefaultAccountAdapter):
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        # 取得正確 email
        if hasattr(emailconfirmation, 'email'):
            to_addr = emailconfirmation.email
            user = emailconfirmation.user
        else:
            to_addr = emailconfirmation.email_address.email
            user = emailconfirmation.email_address.user

        # 自己建 context
        context = {
            "user": user,
            "activate_url": self.get_email_confirmation_url(request, emailconfirmation),
            "current_site": getattr(request, "site", None),
        }

        # render mail
        email = self.render_mail(
            template_prefix='account/email/email_confirmation',
            email=to_addr,
            context=context
        )
        email.send()  # console backend 會印到 console

        # 解析 email.message() 裡的 base64 內容
        msg = email.message()
        if msg.is_multipart():
            for part in msg.walk():
                if part.get('Content-Transfer-Encoding', '').lower() == 'base64':
                    payload = part.get_payload()
                    decoded = base64.b64decode(payload).decode('utf-8')
                    print("=== Decoded Base64 Part ===")
                    print(decoded)
        else:
            if msg.get('Content-Transfer-Encoding', '').lower() == 'base64':
                decoded = base64.b64decode(msg.get_payload()).decode('utf-8')
                print("=== Decoded Base64 ===")
                print(decoded)