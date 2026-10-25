# ============================================================
# commerce_shop/adapters/ecpay_mock_adapter.py
# ============================================================

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx
from django.conf import settings

from commerce_shop.interfaces.ecpay_gateway import (
    ECPayGateway,
)

from util.ChkMacVal import (
    generate_check_mac_value,
)


logger = logging.getLogger(__name__)


class ECPayMockAdapter(ECPayGateway):
    """
    Store → ECPay Mock HTTPX Adapter。

    【保留】

    Adapter 負責：

        1. ECPay Mock URL
        2. HTTPX
        3. CheckMacValue
        4. HTTP response
        5. JSON parsing

    Service 不知道：

        httpx
        HashKey
        HashIV
        ECPay Mock URL

    【修改】

    create_atm_payment() 只負責：

        Store
          ↓
        ECPay Mock
          ↓
        啟動 ATM 流程

    ATM：

        bank_code
        v_account
        expire_date

    不在這裡同步取得。

    真正的 ATM 資訊由：

        Bank Mock
            ↓
        ECPay Mock callback
            ↓
        Store callback

    回來。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        checkout_path: Optional[str] = None,
        query_path: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        【保留】
        Adapter 設定。
        """

        self.base_url = (
            base_url
            or getattr(
                settings,
                "HF_SPACE_ECPAY_MOCK_URL",
                "",
            )
            or getattr(
                settings,
                "ECPAY_MOCK_URL",
                "",
            )
        ).rstrip("/")

        if not self.base_url:

            raise RuntimeError(
                "缺少 ECPay Mock URL 設定"
            )

        self.checkout_path = (
            checkout_path
            or "/gateway/"
            "ecpay_gateway_checkout/"
        )

        self.query_path = (
            query_path
            or "/gateway/"
            "payment_query/"
        )

        self.timeout = (
            timeout
            if timeout is not None
            else 10.0
        )

    # ============================================================
    # URL
    # ============================================================

    def _build_url(
        self,
        path: str,
    ) -> str:
        """
        【保留】
        組合 ECPay Mock URL。
        """

        if not path.startswith("/"):
            path = f"/{path}"

        return (
            f"{self.base_url}"
            f"{path}"
        )

    # ============================================================
    # CheckMacValue
    # ============================================================

    def _sign_payload(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【保留】

        Store → ECPay Mock：

            payload
                ↓
            remove CheckMacValue
                ↓
            HashKey / HashIV
                ↓
            generate_check_mac_value
                ↓
            CheckMacValue
        """

        if not isinstance(payload, dict):

            raise ValueError(
                "ECPay payload 必須是 dict"
            )

        signed_payload = dict(
            payload
        )

        # --------------------------------------------------------
        # 【保留】
        # 同時防止大小寫版本殘留。
        # --------------------------------------------------------

        signed_payload.pop(
            "CheckMacValue",
            None,
        )

        signed_payload.pop(
            "check_mac_value",
            None,
        )

        hash_key = getattr(
            settings,
            "ECPAY_HASH_KEY",
            "",
        )

        hash_iv = getattr(
            settings,
            "ECPAY_HASH_IV",
            "",
        )

        if not hash_key or not hash_iv:

            raise RuntimeError(
                "缺少 ECPAY_HASH_KEY / "
                "ECPAY_HASH_IV"
            )

        check_mac_value = (
            generate_check_mac_value(
                signed_payload,
                hash_key,
                hash_iv,
            )
        )

        signed_payload[
            "CheckMacValue"
        ] = check_mac_value

        return signed_payload

    # ============================================================
    # HTTP POST
    # ============================================================

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【保留】

        唯一真正呼叫 httpx.post()
        的地方。
        """

        try:

            response = httpx.post(
                url,
                json=payload,
                timeout=self.timeout,
            )

        except httpx.TimeoutException as exc:

            logger.exception(
                "ECPay Mock request timeout"
            )

            raise RuntimeError(
                "ECPay Mock request timeout"
            ) from exc

        except httpx.RequestError as exc:

            logger.exception(
                "ECPay Mock request error"
            )

            raise RuntimeError(
                f"ECPay Mock request error：{exc}"
            ) from exc

        except Exception as exc:

            logger.exception(
                "ECPay Mock HTTP request 未預期錯誤"
            )

            raise RuntimeError(
                "ECPay Mock HTTP request 失敗"
            ) from exc

        if not (
            200
            <= response.status_code
            < 300
        ):

            logger.error(
                "ECPay Mock HTTP status=%s body=%s",
                response.status_code,
                response.text,
            )

            raise RuntimeError(
                f"ECPay Mock HTTP "
                f"status={response.status_code}"
            )

        try:

            response_data = response.json()

        except ValueError as exc:

            logger.exception(
                "ECPay Mock 回傳不是合法 JSON"
            )

            raise RuntimeError(
                "ECPay Mock 回傳資料不是合法 JSON"
            ) from exc

        if not isinstance(
            response_data,
            dict,
        ):

            raise RuntimeError(
                "ECPay Mock JSON response 必須是 dict"
            )

        return response_data

    # ============================================================
    # ATM
    # ============================================================

    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        【修改】

        Store → ECPay Mock。

        這裡只啟動 ATM。

        不要求：

            bank_code
            v_account
            expire_date

        因為：

            ATM 資訊不是 Store → ECPay
            這一步同步取得。

        而是：

            ECPay
                ↓
            Bank Mock
                ↓
            callback
                ↓
            Store Payment
        """

        if not isinstance(
            payload,
            dict,
        ):

            raise ValueError(
                "ATM payment payload 必須是 dict"
            )

        # --------------------------------------------------------
        # merchant_trade_no
        # --------------------------------------------------------

        merchant_trade_no = (
            payload.get(
                "merchant_trade_no"
            )
        )

        if not merchant_trade_no:

            raise ValueError(
                "缺少 merchant_trade_no"
            )

        # --------------------------------------------------------
        # trade_amt
        # --------------------------------------------------------

        trade_amt_raw = payload.get(
            "trade_amt"
        )

        if (
            trade_amt_raw is None
            or str(trade_amt_raw).strip() == ""
        ):

            raise ValueError(
                "缺少 trade_amt"
            )

        try:

            trade_amt = Decimal(
                str(trade_amt_raw)
            )

        except Exception as exc:

            raise ValueError(
                "trade_amt 格式錯誤"
            ) from exc

        if trade_amt <= 0:

            raise ValueError(
                "trade_amt 必須大於 0"
            )

        # --------------------------------------------------------
        # 【保留】
        # 強制 ATM 所需欄位。
        # --------------------------------------------------------

        request_payload = dict(
            payload
        )

        request_payload[
            "merchant_trade_no"
        ] = str(
            merchant_trade_no
        )

        request_payload[
            "trade_amt"
        ] = str(
            trade_amt
        )

        request_payload[
            "payment_type"
        ] = "aio"

        request_payload[
            "choose_payment"
        ] = "ATM"

        request_payload[
            "payment_method"
        ] = "ATM"

        # --------------------------------------------------------
        # 【保留】
        # Store → ECPay Mock MAC
        # --------------------------------------------------------

        signed_payload = (
            self._sign_payload(
                request_payload
            )
        )

        url = self._build_url(
            self.checkout_path
        )

        # --------------------------------------------------------
        # HTTPX
        # --------------------------------------------------------

        response_data = (
            self._post_json(
                url,
                signed_payload,
            )
        )

        # ========================================================
        # 【修改】
        #
        # 只判斷 ECPay Mock 有沒有接受請求。
        #
        # 絕對不要在這裡：
        #
        # response_data["bank_code"]
        # response_data["v_account"]
        # response_data["expire_date"]
        #
        # 因為這三個資料要等 callback。
        # ========================================================

        status_value = response_data.get(
            "status"
        )

        response_status = (
            response_data.get(
                "response_status"
            )
        )

        failure_values = {
            False,
            "false",
            "failed",
            "error",
            "failure",
        }

        if (
            status_value in failure_values
            or str(status_value).lower()
            in failure_values
            or str(response_status).lower()
            in failure_values
        ):

            logger.error(
                "ECPay Mock 拒絕 ATM 請求：%s",
                response_data,
            )

            raise RuntimeError(
                "ECPay Mock 拒絕 ATM 付款請求"
            )

        return {
            "success": True,
            "status": "accepted",
            "merchant_trade_no": (
                str(merchant_trade_no)
            ),
            "gateway_response": (
                response_data
            ),
        }

    # ============================================================
    # 【修改】取消交易：E_commerce → ECPay Mock（原 cancel_atm_payment，
    # 加 payment_method 參數同時支援 ATM / COD）
    # 沿用 query_payment 的流程：sign → build url → post
    # ============================================================

    def cancel_payment(
        self,
        merchant_trade_no: str,
        payment_method: str = "ATM",
        delete_record: bool = False,   # 【新增】True=通知 ecpay_mock（→ Bank）刪除已取消的紀錄
    ) -> Dict[str, Any]:

        if not merchant_trade_no:
            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        payload = {
            "merchant_trade_no": str(merchant_trade_no)
        }

        # 【新增】刪除模式：加進 payload 後一起簽章，下游驗章通過才會刪
        if delete_record:
            payload["delete_record"] = "1"

        signed_payload = self._sign_payload(payload)

        # 【修改】依付款方式選 ecpay_mock 取消端點（ATM 經 Bank；COD 不經 Bank）
        url = self._build_url(
            "/cod_gateway/cod_cancel/"
            if payment_method == "COD"
            else "/gateway/cancel_order/"
        )

        response_data = self._post_json(url, signed_payload)

        # 【新增】ecpay_mock 回 status=False 視為取消 / 刪除失敗
        if not response_data.get("status"):
            raise RuntimeError(
                "ECPay Mock 取消失敗："
                f"{response_data.get('message') or '未知錯誤'}"
            )

        return response_data

    # ============================================================
    # Query
    # ============================================================

    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        【保留】

        保留 payment query 能力。
        """

        if not merchant_trade_no:

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        payload = {
            "merchant_trade_no": (
                str(merchant_trade_no)
            )
        }

        signed_payload = (
            self._sign_payload(
                payload
            )
        )

        url = self._build_url(
            self.query_path
        )

        return self._post_json(
            url,
            signed_payload,
        )