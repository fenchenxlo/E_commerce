
# ============================================================
# commerce_shop/interfaces/ecpay_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict


class ECPayGateway(ABC):
    """
    ECPay Gateway Interface。

    【新增】

    Service 只依賴這個 Interface。

    實際 HTTPX：
        ECPayMockAdapter

    Service：
        不知道 HTTPX
        不知道 CheckMacValue 實作細節
        不知道 ECPay Mock URL

    """

    # ========================================================
    # 【保留】
    # ATM 建立
    # ========================================================

    @abstractmethod
    def create_atm_payment(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        建立 ATM 付款流程。

        payload：
            Store 業務資料。

        return：
            ECPay Mock 回應結果。
        """
        raise NotImplementedError

    # ========================================================
    # 【保留】
    # Payment Query
    # ========================================================

    # 【修改】取消交易（E_commerce → ECPay Mock）：原 cancel_atm_payment，
    # 加 payment_method 參數同時支援 ATM / COD
    @abstractmethod
    def cancel_payment(
        self,
        merchant_trade_no: str,
        payment_method: str = "ATM",
        delete_record: bool = False,   # 【新增】True=通知下游刪除已取消的紀錄
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def query_payment(
        self,
        merchant_trade_no: str,
    ) -> Dict[str, Any]:
        """
        查詢付款狀態。

        【保留】

        這個能力不能因為目前先做 ATM 建立，
        就被刪除。

        實際 HTTPX：
            ECPayMockAdapter
        """
        raise NotImplementedError

