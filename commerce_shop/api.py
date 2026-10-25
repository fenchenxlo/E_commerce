# ============================================================
# commerce_shop/api.py
# ============================================================

import logging

from django.http import JsonResponse
from ninja import NinjaAPI

from commerce_shop.schemas.checkout import (
    CheckoutSchema,
)

from commerce_shop.services.order_service import (
    OrderService,
)

# from commerce_shop.services.payment_service import (
    # PaymentService,
# )


logger = logging.getLogger(__name__)


api = NinjaAPI()


# ============================================================
# Checkout API
# ============================================================

@api.post("/checkout")
def checkout(
    request,
    data: CheckoutSchema,
):
    """
    【修改】

    現在這個 API 只處理第二階段：

        enter_receiver_info.html
                ↓
        POST /api/checkout
                ↓
        CheckoutSchema
                ↓
        OrderService
                ↓
        更新既有 Order
                ↓
        PaymentService
                ↓
        ECPayGateway
                ↓
        Ecpay Mock
                ↓
        Bank Mock
                ↓
        完整 ATM 資訊
                ↓
        PaymentService
                ↓
        Payment.objects.create(...)
                ↓
        JsonResponse
                ↓
        atm_info.html
    """

    # ========================================================
    # 【新增】
    # 登入驗證
    # ========================================================

    if not request.user.is_authenticated:

        return JsonResponse(
            {
                "success": False,
                "message": "請先登入會員。",
            },
            status=401,
        )

    try:

        # ====================================================
        # 【新增】
        # 第一段：只更新 Order
        # ====================================================

        order_service = (
            OrderService()
        )

        order_result = (
            order_service
            .process_existing_order_checkout(
                user=request.user,
                payload=data,
            )
        )

        # ====================================================
        # 【新增】
        # COD 目前還不走 ECPay ATM。
        # ====================================================

        if data.payment_method == "COD":

            return JsonResponse(
                order_result,
                status=200,
            )

        # ====================================================
        # 【新增】
        # ATM：
        #
        # Order 已更新成功後，
        # 才真正進入 PaymentService。
        # ====================================================

        # payment_service = (
            # PaymentService()
        # )

        # payment_result = (
            # payment_service
            # .create_payment(
                # user=request.user,
                # order_number=data.order_number,
                # payment_method=data.payment_method,
            # )
        # )

        # ====================================================
        # 【新增】
        # 第四段：
        #
        # PaymentService 已經完成：
        #
        # PaymentService
        #       ↓
        # ECPayGateway
        #       ↓
        # Ecpay Mock
        #       ↓
        # Bank Mock
        #       ↓
        # bank_code
        # v_account
        # expire_date
        #       ↓
        # PaymentService
        #       ↓
        # Payment.objects.create()
        #
        # 現在 payment_result 已經是「完整 Payment 結果」。
        # ====================================================

        # atm_info_url = (
            # payment_result.get(
                # "atm_info_url"
            # )
        # )

        # ====================================================
        # 【新增】
        # 第五段：
        #
        # API 最後才把完整結果交給前端。
        # ====================================================

        # return JsonResponse(
            # {
                # "success": True,

                # "order_number": (
                    # order_result[
                        # "order_number"
                    # ]
                # ),

                # "order_status": (
                    # order_result[
                        # "status"
                    # ]
                # ),

                # "payment_method": (
                    # order_result[
                        # "payment_method"
                    # ]
                # ),

                # "payment": (
                    # payment_result
                # ),

                # "atm_info_url": (
                    # atm_info_url
                # ),
            # },
            # status=200,
        # )
        
        # ====================================================
        # 【修改】
        #
        # ATM 到這裡就停止 Server-side Checkout。
        #
        # 不再：
        #
        #     PaymentService
        #     ECPayGateway
        #     ECPayMockAdapter
        #     HTTPX
        #
        # 後續改由 Browser POST
        # 到 Ecpay Mock。
        # ====================================================

        return JsonResponse(
            {
                "success": True,

                "order_number": (
                    order_result[
                        "order_number"
                    ]
                ),

                "order_status": (
                    order_result[
                        "status"
                    ]
                ),

                "payment_method": (
                    order_result[
                        "payment_method"
                    ]
                ),

                "message": (
                    "訂單資料更新成功，"
                    "準備前往 ECPay ATM 付款。"
                ),
            },
            status=200,
        )

    except ValueError as exc:

        logger.warning(
            "[checkout] 業務錯誤：%s",
            exc,
        )

        return JsonResponse(
            {
                "success": False,
                "error_type": (
                    type(exc).__name__
                ),
                "message": str(exc),
            },
            status=400,
        )

    except Exception as exc:

        logger.exception(
            "[checkout] Checkout 發生未預期錯誤"
        )

        return JsonResponse(
            {
                "success": False,
                "error_type": (
                    type(exc).__name__
                ),
                "message": str(exc),
            },
            status=500,
        )