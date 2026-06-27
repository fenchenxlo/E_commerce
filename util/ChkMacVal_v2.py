import hashlib
import urllib.parse
HASH_KEY = "5294y06JbISpM5x9"
HASH_IV = "v77hoKGq4kWxNNIS"
def generate_check_mac_value(data: dict):
    params = data.copy()
    # 移除 CheckMacValue
    params.pop("CheckMacValue", None)
    # 依照 key 排序
    sorted_params = sorted(params.items(), key=lambda x: x[0].lower())
    # 組字串
    raw = f"HashKey={HASH_KEY}"
    for key, value in sorted_params:
        raw += f"&{key}={value}"
    raw += f"&HashIV={HASH_IV}"
    # URL Encode
    encoded = urllib.parse.quote_plus(raw).lower()
    # 特殊字元修正（綠界規則）
    replace_map = {
        "%2d": "-",
        "%5f": "_",
        "%2e": ".",
        "%21": "!",
        "%2a": "*",
        "%28": "(",
        "%29": ")",
    }
    for k, v in replace_map.items():
        encoded = encoded.replace(k, v)
    # SHA256
    check_mac = hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()
    return check_mac