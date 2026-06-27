from allauth.account.adapter import DefaultAccountAdapter
import sys
import io
import base64
import re

class MyAccountAdapter(DefaultAccountAdapter):

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """
        覆寫 Allauth Adapter 的 send_confirmation_mail
        - 呼叫原本方法（console backend 會印郵件）
        - 捕捉 console output
        - 自動解析 Base64 郵件正文（HTML / 純文字）
        """

        # -------------------------
        # 1️⃣ 先捕捉 sys.stdout
        # -------------------------
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            # 呼叫原本方法（會印到 console backend）
            super().send_confirmation_mail(request, emailconfirmation, signup)

            # -------------------------
            # 2️⃣ 取得捕捉到的輸出
            # -------------------------
            output = sys.stdout.getvalue()

        finally:
            # 還原 stdout
            sys.stdout = old_stdout

        # -------------------------
        # 3️⃣ 嘗試解析 Base64 內容
        # -------------------------
        # 找 Content-Transfer-Encoding: base64 的區塊
        base64_blocks = re.findall(r'Content-Transfer-Encoding: base64\n\n([A-Za-z0-9+/=\n]+)', output)
        if base64_blocks:
            for block in base64_blocks:
                try:
                    decoded_bytes = base64.b64decode(block)
                    decoded_text = decoded_bytes.decode('utf-8', errors='ignore')
                    print("\n==== 解碼後郵件內容 ====\n")
                    print(decoded_text)
                    print("\n=======================\n")
                except Exception as e:
                    print("⚠️ Base64 解碼失敗:", e)
        else:
            # 沒有找到 base64，就直接印整個 console output
            print("\n==== 郵件內容 (未找到 Base64) ====\n")
            print(output)
            print("\n===============================\n")