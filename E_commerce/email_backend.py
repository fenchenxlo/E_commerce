from django.core.mail.backends.console import EmailBackend
import email

class ReadableConsoleEmailBackend(EmailBackend):
    def _send(self, email_message):
        msg = email_message.message()

        for part in msg.walk():
            content_type = part.get_content_type()

            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"

                try:
                    print(payload.decode(charset))
                except Exception:
                    print(payload)

        return 1