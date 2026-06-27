import hashlib
import urllib.parse

def generate_check_mac_value(params, hash_key, hash_iv):

    # 依照參數名稱排序（綠界規定）
    sorted_params = sorted(params.items())

    # 前面加上 HashKey
    raw = f"HashKey={hash_key}"

    # 將所有參數串接起來
    for k, v in sorted_params:
        raw += f"&{k}={v}"

    # 最後加上 HashIV
    raw += f"&HashIV={hash_iv}"

    # URL encode 並轉小寫
    raw = urllib.parse.quote_plus(raw).lower()

    # 綠界特殊轉換規則
    replacements = {
        '%2d': '-',
        '%5f': '_',
        '%2e': '.',
        '%21': '!',
        '%2a': '*',
        '%28': '(',
        '%29': ')'
    }

    # 進行特殊字元替換
    for key, value in replacements.items():
        raw = raw.replace(key, value)

    # SHA256 加密後轉大寫
    return hashlib.sha256(
        raw.encode('utf-8')
    ).hexdigest().upper()