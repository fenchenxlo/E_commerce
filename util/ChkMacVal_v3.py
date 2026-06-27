import hashlib
import urllib.parse


def generate_check_mac_value(
    params,
    hash_key,
    hash_iv
):
    """
    產生綠界 CheckMacValue
    """

    params = params.copy()

    # 移除舊的 CheckMacValue
    params.pop("CheckMacValue", None)

    # 不分大小寫排序
    sorted_params = sorted(
        params.items(),
        key=lambda x: x[0].lower()
    )

    # 組字串
    raw = f"HashKey={hash_key}"

    for k, v in sorted_params:
        raw += f"&{k}={v}"

    raw += f"&HashIV={hash_iv}"

    # URL Encode
    encoded = urllib.parse.quote_plus(
        raw,
        safe='-_.!*()'
    ).lower()

    # SHA256
    return hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest().upper()