# ============================================================
# commerce_shop/services/order_service.py
# ============================================================

import logging, uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from commerce_shop.interfaces.ecpay_gateway import (
    ECPayGateway,
)
from commerce_shop.interfaces.order_repository import (
    OrderRepository,
)
from commerce_shop.adapters.django_order_repository import (
    DjangoOrderRepository,
)
from commerce_shop.adapters.ecpay_mock_adapter import (
    ECPayMockAdapter,
)
# 👈 關鍵：確保有把 Order 還有 OrderItem 等模型匯入進來
from commerce_shop.models import Order, OrderItem , InventoryReservation   # 【修改】新增 InventoryReservation

logger = logging.getLogger(__name__)


class OrderService:
    """
    Order Business Service。

    【修改】

    Service 負責：

        1. Order Business Logic
        2. Checkout Business Validation
        3. Inventory Reservation Business Logic
        4. Order Status Transition
        5. 呼叫 ECPayGateway

    Service 不直接：

        ❌ Model.objects
        ❌ model.save()
        ❌ model.delete()
        ❌ httpx.post()

    ORM：

        Service
            ↓
        OrderRepository
            ↓
        DjangoOrderRepository
            ↓
        Django ORM

    HTTP：

        OrderService
            ↓
        ECPayGateway
            ↓
        ECPayMockAdapter
            ↓
        httpx
    """

    # ========================================================
    # 【保留】
    # 固定運費
    # ========================================================

    SHIPPING_FEE = Decimal("60.00")

    def __init__(
        self,
        repository: Optional[OrderRepository] = None,
        ecpay_gateway: Optional[ECPayGateway] = None,
    ):
        """
        【修改】

        Dependency Injection。

        預設：

            OrderRepository
                ↓
            DjangoOrderRepository

            ECPayGateway
                ↓
            ECPayMockAdapter

        測試時可以注入 Fake / Mock。
        """

        self.repository = (
            repository
            or DjangoOrderRepository()
        )

        self.ecpay_gateway = (
            ecpay_gateway
            or ECPayMockAdapter()
        )

    # ============================================================
    # Stage 1
    # ============================================================

    def create_order_from_cart(
        self,
        user,
    ) -> Dict[str, Any]:
        """
        【修改】

        Stage 1：

            Cart
                ↓
            OrderService
                ↓
            OrderRepository
                ↓
            Order
            OrderItem
            InventoryReservation
            Product stock/reserved_stock
            Cart 清空

        注意：

            這裡是本地 DB Transaction。

            不應該在 transaction.atomic() 裡呼叫
            ECPay / Bank / HTTPX。
        """

        try:

            # ====================================================
            # 【新增】
            # 本地資料庫交易。
            #
            # 如果下面任何一步失敗：
            #
            # Order
            # OrderItem
            # Product
            # Reservation
            # Cart
            #
            # 全部 rollback。
            # ====================================================

            with transaction.atomic():

                # ------------------------------------------------
                # 【修改】
                # 原本 Service 直接：
                #
                # Cart.objects.select_for_update()
                #
                # 現在改成：
                #
                # Service
                #   ↓
                # Repository
                # ------------------------------------------------

                cart = (
                    self.repository
                    .get_cart_for_update(
                        user
                    )
                )

                if not cart:

                    raise ValueError(
                        "購物車不存在"
                    )

                # ------------------------------------------------
                # 取得 CartItem
                # ------------------------------------------------

                cart_items = list(
                    self.repository
                    .get_cart_items_for_update(
                        cart
                    )
                )

                if not cart_items:

                    raise ValueError(
                        "購物車是空的，無法結帳"
                    )

                # ------------------------------------------------
                # 商品總額
                # ------------------------------------------------

                total_product_amount = (
                    Decimal("0.00")
                )

                for cart_item in cart_items:

                    if cart_item.quantity <= 0:

                        raise ValueError(
                            "購物車商品數量必須大於 0"
                        )

                    product = cart_item.product

                    # --------------------------------------------
                    # 商品是否已下架
                    # --------------------------------------------

                    if product.is_deleted:

                        raise ValueError(
                            f"商品「{product.name}」"
                            "已下架"
                        )

                    # --------------------------------------------
                    # 庫存檢查
                    # --------------------------------------------

                    if (
                        product.stock
                        < cart_item.quantity
                    ):

                        raise ValueError(
                            f"商品「{product.name}」"
                            f"庫存不足，"
                            f"目前庫存：{product.stock}"
                        )

                    total_product_amount += (
                        cart_item.price
                        * cart_item.quantity
                    )

                # ------------------------------------------------
                # 【保留】
                #
                # Order.total_amount
                # = 商品總額 + 運費
                # ------------------------------------------------

                total_amount = (
                    total_product_amount
                    + self.SHIPPING_FEE
                )

                # ------------------------------------------------
                # 【修改】
                # 建立 Order 改透過 Repository。
                # ------------------------------------------------

                order = (
                    self.repository.create_order(
                        user=user,
                        shipping_fee=(
                            self.SHIPPING_FEE
                        ),
                        total_amount=(
                            total_amount
                        ),
                        status="pending_payment",
                        payment_method="",
                    )
                )

                # ------------------------------------------------
                # 建立 OrderItem + InventoryReservation
                # ------------------------------------------------

                for cart_item in cart_items:

                    product = cart_item.product

                    # --------------------------------------------
                    # OrderItem
                    # --------------------------------------------

                    self.repository.create_order_item(
                        order=order,
                        product=product,
                        name=product.name,
                        quantity=(
                            cart_item.quantity
                        ),
                        price=cart_item.price,
                    )

                    # --------------------------------------------
                    # 【保留】
                    #
                    # Checkout 時：
                    #
                    # stock -= quantity
                    # reserved_stock += quantity
                    # --------------------------------------------

                    new_stock = (
                        product.stock
                        - cart_item.quantity
                    )

                    new_reserved_stock = (
                        product.reserved_stock
                        + cart_item.quantity
                    )

                    self.repository.save_product_stock(
                        product,
                        stock=new_stock,
                        reserved_stock=(
                            new_reserved_stock
                        ),
                    )

                    # --------------------------------------------
                    # InventoryReservation
                    # --------------------------------------------

                    self.repository.create_inventory_reservation(
                        order=order,
                        product=product,
                        quantity=(
                            cart_item.quantity
                        ),
                        status="reserved",
                    )

                # ------------------------------------------------
                # 【修改】
                # 清空 Cart 改透過 Repository。
                # ------------------------------------------------

                self.repository.clear_cart_items(
                    cart
                )

                return {
                    "success": True,
                    "stage": 1,
                    "order_number": (
                        order.order_number
                    ),
                    "status": order.status,
                    "total_amount": str(
                        order.total_amount
                    ),
                }

        except ValueError:
            # ====================================================
            # 【保留】
            # Business Validation 原樣向上丟。
            # ====================================================

            raise

        except Exception as exc:

            logger.exception(
                "[OrderService.create_order_from_cart] "
                "建立 Order 失敗"
            )

            raise RuntimeError(
                f"建立訂單失敗：{exc}"
            ) from exc

    # ============================================================
    # Stage 2
    # ============================================================

    # ============================================================
    # 第二階段
    # ============================================================

    def process_existing_order_checkout(
        self,
        user,
        payload,
    ) -> Dict[str, Any]:
        """
        第二階段：

            enter_receiver_info.html
                    ↓
            OrderService
                    ↓
            更新既有 Order
                    ↓
            回傳給 API
                    ↓
            API 再呼叫 PaymentService
                    ↓
            PaymentService → ECPayGateway
                    ↓
            Ecpay Mock → Bank Mock
                    ↓
            完整 ATM 資訊回到 E_commerce

        【修改】

        OrderService 在這裡只負責：

            1. 驗證 checkout 資料
            2. 找到目前使用者的既有 Order
            3. 更新 receiver / payment_method / remark
            4. 儲存 Order

        Payment 不在這裡建立。

        ECPay 不在這裡呼叫。

        第三方 HTTP request 不在 Order transaction 裡。
        """

        # ========================================================
        # 【新增】
        # Schema 已經驗證型別，
        # 這裡仍然做 Business Validation。
        # ========================================================

        if not payload.order_number:
            raise ValueError(
                "第二階段缺少 order_number"
            )

        if not payload.receiver_name:
            raise ValueError(
                "缺少 receiver_name"
            )

        if not payload.receiver_phone:
            raise ValueError(
                "缺少 receiver_phone"
            )

        if not payload.receiver_address:
            raise ValueError(
                "缺少 receiver_address"
            )

        if payload.payment_method not in (
            "ATM",
            "COD",
        ):
            raise ValueError(
                "付款方式必須是 ATM 或 COD"
            )

        try:

            # ====================================================
            # 【修改】
            #
            # transaction 只包住 Order DB 操作。
            #
            # 不把：
            #
            # ECPay
            # httpx
            # Bank Mock
            #
            # 放進這個 transaction。
            # ====================================================

            with transaction.atomic():

                # ------------------------------------------------
                # 找到目前登入使用者自己的 Order。
                # ------------------------------------------------
                logger.warning(
                    "[DEBUG checkout] user_id=%s, payload.order_number=%r",
                    user.id,
                    payload.order_number,
                )

                order = (
                    Order.objects
                    .select_for_update()
                    .filter(
                        order_number=(
                            payload.order_number
                        ),
                        user=user,
                    )
                    .first()
                )

                if not order:
                    raise ValueError(
                        "找不到訂單，或訂單不屬於目前使用者"
                    )

                # ------------------------------------------------
                # 只能對尚未付款的訂單設定付款資料。
                # ------------------------------------------------

                # 【新增】逾期訂單給明確訊息（API 直接呼叫時的後端防線）
                if order.status == "expired":
                    raise ValueError(
                        "此訂單已逾期未付款，無法再付款，請重新下單"
                    )

                if order.status != "pending_payment":
                    raise ValueError(
                        f"目前訂單狀態為 {order.status}，"
                        "無法再次進行付款設定"
                    )

                # ------------------------------------------------
                # 更新收件資訊。
                # ------------------------------------------------

                order.receiver_name = (
                    payload.receiver_name
                )

                order.receiver_phone = (
                    payload.receiver_phone
                )

                order.receiver_address = (
                    payload.receiver_address
                )

                order.payment_method = (
                    payload.payment_method
                )

                order.remark = (
                    payload.remark or ""
                )

                # ------------------------------------------------
                # 【修改】
                # 只更新真正被修改的 Order 欄位。
                # ------------------------------------------------

                order.save(
                    update_fields=[
                        "receiver_name",
                        "receiver_phone",
                        "receiver_address",
                        "payment_method",
                        "remark",
                        "updated_at",
                    ]
                )

            # ====================================================
            # 【新增】
            # Order DB 更新成功。
            #
            # Payment / ECPay 交給 api.py + PaymentService。
            # ====================================================

            return {
                "success": True,
                "order_number": order.order_number,
                "status": order.status,
                "payment_method": (
                    order.payment_method
                ),
                "total_amount": str(
                    order.total_amount
                ),
                "message": "訂單資料更新成功。",
            }

        except ValueError:
            raise

        except Exception as exc:

            logger.exception(
                "[OrderService."
                "process_existing_order_checkout] "
                "更新 Order 失敗"
            )

            raise RuntimeError(
                f"更新訂單失敗：{exc}"
            ) from exc


    # ============================================================
    # 【新增】
    # ECPay ATM Checkout
    # ============================================================

    def prepare_ecpay_atm_checkout(
        self,
        user,
        order_number: str,
    ) -> Dict[str, Any]:
        """
        【新增】

        準備 Browser → Ecpay Mock 所需要的 ATM payload。

        流程：

            ecpay_checkout_redirect View
                    ↓
            OrderService
                    ↓
            取得目前使用者自己的 Order
                    ↓
            建立 ECPay payload
                    ↓
            回傳 payload 給 View

        注意：

            這裡只負責準備付款資料。

            不建立 Payment。
            不呼叫 ECPayGateway。
            不呼叫 HTTPX。
            不呼叫 Bank Mock。
        """

        if not order_number:
            raise ValueError(
                "缺少 order_number"
            )

        try:

            # ====================================================
            # 【新增】
            # 取得目前登入使用者自己的 Order。
            #
            # 這裡直接依照目前專案實際使用的
            # Django ORM 查詢方式取得 Order。
            # ====================================================

            order = (
                Order.objects
                .filter(
                    order_number=order_number,
                    user=user,
                )
                .first()
            )

            if not order:
                raise ValueError(
                    "找不到訂單，或訂單不屬於目前使用者"
                )

            # ====================================================
            # 【新增】
            # 只能對尚未付款的訂單建立 ATM Checkout。
            # ====================================================

            if order.status != "pending_payment":
                raise ValueError(
                    f"目前訂單狀態為 {order.status}，"
                    "無法進行 ATM 付款"
                )

            # ====================================================
            # 【新增】
            # 必須確認付款方式已經由
            # enter_receiver_info.html
            # → /api/checkout
            # 更新成 ATM。
            # ====================================================

            if order.payment_method != "ATM":
                raise ValueError(
                    "目前訂單付款方式不是 ATM"
                )

            # ====================================================
            # 【新增】
            # 取得商品名稱。
            #
            # ECPay ItemName 使用：
            #
            #     商品A#商品B#商品C
            #
            # OrderItem 已經在 Stage 1 建立，
            # 因此這裡只讀取既有資料。
            # ====================================================

            items = (
                order.items
                .select_related("product")
                .all()
            )

            item_names = "#".join(
                item.product.name
                for item in items
            )

            if not item_names:
                item_names = (
                    f"訂單 {order.order_number}"
                )

            # ====================================================
            # 【修改】
            #
            # 使用既有的 _build_ecpay_atm_payload()
            # 作為基礎 payload。
            # ====================================================

            payload = (
                self._build_ecpay_atm_payload(
                    order
                )
            )

            # ====================================================
            # 【新增】
            # 補上 Browser POST 到 Ecpay Mock
            # 所需要的欄位。
            # ====================================================

            payload.update(
                {
                    "merchant_id":
                        "2000132",

                    "merchant_trade_date":
                        timezone.localtime(
                            order.created_at
                        ).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),

                    "user_id":
                        user.id,

                    # 【新增】ecpay_mock 建立 Order 紀錄所需的收件人姓名
                    # （原本只送 user_id，所以 ecpay_mock Order.receiver_name 是空的）
                    # 【重點】此欄位會一併簽進 CheckMacValue，
                    # ecpay_mock schema 已放行 receiver_name
                    "receiver_name":
                        (
                            order.receiver_name
                            or ""
                        ),

                    "trade_desc":
                        (
                            order.remark
                            or "購買商品"
                        ),

                    "item_name":
                        item_names,

                    "status":
                        order.status,
                }
            )

            logger.info(
                "[OrderService."
                "prepare_ecpay_atm_checkout] "
                "Order=%s ECPay payload 建立成功",
                order.order_number,
            )

            return payload

        except ValueError:
            raise

        except Exception as exc:

            logger.exception(
                "[OrderService."
                "prepare_ecpay_atm_checkout] "
                "建立 ECPay ATM payload 失敗"
            )

            raise RuntimeError(
                "建立 ECPay ATM 付款資料失敗"
            ) from exc

    # ============================================================
    # 【新增】依付款方式分流
    # ============================================================

    def prepare_ecpay_checkout(
        self,
        user,
        order_number: str,
    ) -> Dict[str, Any]:

        order = (
            Order.objects
            .filter(order_number=order_number, user=user)
            .first()
        )

        if not order:
            raise ValueError("找不到訂單，或訂單不屬於目前使用者")

        if order.payment_method == "COD":
            return self.prepare_ecpay_cod_checkout(
                user=user,
                order_number=order_number,
            )

        return self.prepare_ecpay_atm_checkout(
            user=user,
            order_number=order_number,
        )

    # ============================================================
    # 【新增】ECPay COD Checkout payload（Browser → ecpay_mock cod_checkout）
    # 只準備資料，不建 Payment、不呼叫 httpx
    # ============================================================

    def prepare_ecpay_cod_checkout(
        self,
        user,
        order_number: str,
    ) -> Dict[str, Any]:

        order = (
            Order.objects
            .filter(order_number=order_number, user=user)
            .first()
        )

        if not order:
            raise ValueError("找不到訂單，或訂單不屬於目前使用者")

        if order.status != "pending_payment":
            raise ValueError(
                f"目前訂單狀態為 {order.status}，無法進行超商取貨付款"
            )

        if order.payment_method != "COD":
            raise ValueError("目前訂單付款方式不是 COD")

        item_names = "#".join(
            order.items.values_list("name", flat=True)
        ) or f"訂單 {order.order_number}"

        store_base_url = (
            getattr(settings, "HF_SPACE_E_COMMERCE_URL", "") or ""
        ).rstrip("/")

        return {
            "merchant_trade_no": order.order_number,
            "merchant_trade_date": timezone.localtime(
                order.created_at
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": user.id,
            "trade_amt": str(order.total_amount),
            "trade_desc": order.remark or "購買商品",
            "item_name": item_names,
            "payment_type": "aio",
            "choose_payment": "COD",
            "payment_method": "COD",
            "receiver_name": order.receiver_name or "",
            "receiver_cell_phone": order.receiver_phone or "",
            "receiver_address": order.receiver_address or "",
            "ReturnURL": f"{store_base_url}/commerce_shop/cod_payment_notify/",
            "OrderResultURL": f"{store_base_url}/commerce_shop/purchased_products/",
            "action_url": (
                f"{settings.HF_SPACE_ECPAY_MOCK_URL}"
                "/cod_gateway/cod_checkout/"
            ),
        }
        
    @classmethod
    def checkout(cls, user, cart):
        """將傳入的 cart 及其 items 寫入 SQLite3 資料庫，並生成對應的 Order 與 OrderItem"""

        # 啟動資料庫交易事務，萬一其中一步失敗（例如中途發現庫存不足），整筆訂單資料會自動倒帶（Rollback）
        with transaction.atomic():

            # 1. 撈出購物車所有的項目並預檢庫存
            cart_items = cart.items.select_related("product").all()
            items_total = Decimal("0.00")

            for item in cart_items:
                if item.product.stock < item.quantity:
                    raise ValueError(
                        f"商品 {item.product.name} 庫存不足，目前僅剩 {item.product.stock} 件。"
                    )
                # 累加總金額
                items_total += item.price * item.quantity

            shipping_fee = Decimal("60.00")  # 假設固定運費為 60
            total_amount = items_total + shipping_fee

            # 2. 建立並寫入 Order 紀錄到 SQLite3
            order_number = f"ORD-{uuid.uuid4().hex[:12].upper()}"

            # 因為你不要收件資訊，這裡的 receiver 欄位留空或給預設值
            order = Order.objects.create(
                order_number=order_number,
                user=user,
                #receiver_name=user.username,
                #receiver_phone=getattr(user, 'phone', '0900000000'), # 👈 補上預設電話（防呆）
                #receiver_address='現場取貨 / 未填寫',                 # 👈 補上預設地址（防呆）
                shipping_fee=shipping_fee,
                total_amount=total_amount,
                status='pending_payment',
                shipping_status='pending'
            )

            # 3. 遍歷購物車項目，將資料寫入 OrderItem，並扣除商品庫存

            for item in cart_items:
                # 寫入訂單明細到 SQLite3
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    name=item.product.name,  # 【新增】商品名稱快照（model 必填欄位）
                    quantity=item.quantity,
                    price=item.price,  # 使用購物車當時快照的價格
                )

                # 扣除並更新 Product 庫存
                product = item.product
                product.stock -= item.quantity
                product.reserved_stock += item.quantity  # 【新增】同步增加預留庫存
                product.save()

                # 【新增】建立庫存預留紀錄，delete_order 釋放庫存靠它
                InventoryReservation.objects.create(
                    order=order,
                    product=product,
                    quantity=item.quantity,
                    status="reserved",
                )

            # for item in cart_items:
                # # 寫入訂單明細到 SQLite3
                # OrderItem.objects.create(
                    # order=order,
                    # product=item.product,
                    # quantity=item.quantity,
                    # price=item.price,  # 使用購物車當時快照的價格
                # )

                # # 扣除並更新 Product 庫存
                # product = item.product
                # product.stock -= item.quantity
                # product.save()

            # 4. 清空購物車 (刪除目前購物車內所有的 CartItem 紀錄)
            cart_items.delete()

            return order

    # ============================================================
    # ECPay ATM Payload
    # ============================================================

    def _build_ecpay_atm_payload(
        self,
        order,
    ) -> Dict[str, Any]:
        """
        【新增】

        建立 Store → ECPay Mock payload。

        注意：

            這裡只提供 ECPay Mock 啟動 ATM
            所需要的資料。

        不產生：

            bank_code
            v_account
            expire_date

        那些資料是 Bank Mock 負責。
        """

        try:

            store_base_url = (
                getattr(
                    settings,
                    "HF_SPACE_E_COMMERCE_URL",
                    "",
                )
                or ""
            ).rstrip("/")

            payload = {
                "merchant_trade_no": (
                    order.order_number
                ),
                "trade_amt": str(
                    order.total_amount
                ),
                "payment_type": "aio",
                "choose_payment": "ATM",
                "payment_method": "ATM",

                # ------------------------------------------------
                # ECPay Mock 完成 Bank callback 後，
                # 用這個 URL 回 Store。
                # ------------------------------------------------
                "ReturnURL": (
                    f"{store_base_url}"
                    "/commerce_shop/"
                    "atm_payment_notify/"
                ),

                # ------------------------------------------------
                # Browser 最後結果頁。
                #
                # ECPay Mock 是否使用此欄位，
                # 由 ECPay Mock 的 Service 決定。
                # ------------------------------------------------
                "OrderResultURL": (
                    f"{store_base_url}"
                    "/commerce_shop/payment_ok/"
                ),
                # ------------------------------------------------
                # 【新增】
                # Browser 最後要 POST 到 Ecpay Mock
                # 的 ATM Checkout View。
                # ------------------------------------------------

                "action_url": (
                    f"{settings.HF_SPACE_ECPAY_MOCK_URL}"
                    "/gateway/ecpay_gateway_checkout/"
                ),
            }

            return payload

        except Exception as exc:

            logger.exception(
                "[OrderService._build_ecpay_atm_payload] "
                "建立 ECPay payload 失敗"
            )

            raise RuntimeError(
                "建立 ECPay ATM 付款資料失敗"
            ) from exc

    # ============================================================
    # Payment Success
    # ============================================================

    def mark_order_paid(
        self,
        order,
    ):
        """
        【修改】

        Payment success：

            Order
                pending_payment
                    ↓
                paid

            Reservation
                reserved
                    ↓
                committed

            Product
                reserved_stock -= quantity
        """

        try:

            with transaction.atomic():

                # ------------------------------------------------
                # 【修改】
                # Repository 取得鎖定 Order。
                # ------------------------------------------------

                locked_order = (
                    self.repository
                    .get_order_by_pk_for_update(
                        order_pk=order.pk
                    )
                )

                if not locked_order:

                    raise ValueError(
                        "找不到要更新付款狀態的訂單"
                    )

                # ------------------------------------------------
                # 【新增】
                # Idempotent：
                # callback 重送時，如果已經 paid，
                # 不要再次扣 reserved_stock。
                # ------------------------------------------------

                if locked_order.status == "paid":

                    return locked_order

                if locked_order.status in (
                    "cancelled",
                    "expired",
                ):

                    raise ValueError(
                        f"訂單目前狀態為 "
                        f"{locked_order.status}，"
                        "不能再標記為 paid"
                    )

                # ------------------------------------------------
                # 取得 Reservation
                # ------------------------------------------------

                reservations = list(
                    self.repository
                    .get_reservations_for_update(
                        locked_order
                    )
                )

                for reservation in reservations:

                    if reservation.status != (
                        "reserved"
                    ):
                        continue

                    product = reservation.product

                    new_reserved_stock = max(
                        0,
                        (
                            product.reserved_stock
                            - reservation.quantity
                        ),
                    )

                    # --------------------------------------------
                    # 【修改】
                    # Product ORM 改透過 Repository。
                    # --------------------------------------------

                    self.repository.save_product_reserved_stock(
                        product,
                        reserved_stock=(
                            new_reserved_stock
                        ),
                    )

                    # --------------------------------------------
                    # Reservation committed
                    # --------------------------------------------

                    self.repository.save_reservation(
                        reservation,
                        status="committed",
                    )

                # ------------------------------------------------
                # Order → paid
                # ------------------------------------------------

                self.repository.save_order_status(
                    locked_order,
                    status="paid",
                )

                return locked_order

        except ValueError:
            raise

        except Exception as exc:

            logger.exception(
                "[OrderService.mark_order_paid] "
                "Order paid 更新失敗"
            )

            raise RuntimeError(
                "訂單付款成功處理失敗"
            ) from exc

    # ============================================================
    # Payment Failed / Expired / Cancelled
    # ============================================================

    def release_order_inventory(
        self,
        order,
        order_status="expired",
    ):
        """
        【修改】

        Payment failed / expired / cancelled：

            stock += quantity
            reserved_stock -= quantity

            Reservation:
                reserved
                    ↓
                released
        """

        if order_status not in (
            "expired",
            "cancelled",
        ):

            raise ValueError(
                "release_order_inventory "
                "只能使用 expired / cancelled"
            )

        try:

            with transaction.atomic():

                locked_order = (
                    self.repository
                    .get_order_by_pk_for_update(
                        order_pk=order.pk
                    )
                )

                if not locked_order:

                    raise ValueError(
                        "找不到要釋放庫存的訂單"
                    )

                # ------------------------------------------------
                # 【新增】
                # Idempotent。
                #
                # 如果 callback 重複送，
                # Reservation 已經 released，
                # 不會再次加 stock。
                # ------------------------------------------------

                if locked_order.status in (
                    "expired",
                    "cancelled",
                ):

                    return locked_order

                if locked_order.status == "paid":

                    raise ValueError(
                        "已付款訂單不能釋放庫存"
                    )

                reservations = list(
                    self.repository
                    .get_reservations_for_update(
                        locked_order
                    )
                )

                for reservation in reservations:

                    if reservation.status != (
                        "reserved"
                    ):
                        continue

                    product = reservation.product

                    new_stock = (
                        product.stock
                        + reservation.quantity
                    )

                    new_reserved_stock = max(
                        0,
                        (
                            product.reserved_stock
                            - reservation.quantity
                        ),
                    )

                    # ------------------------------------------------
                    # 【修改】
                    # Product 更新透過 Repository。
                    # ------------------------------------------------

                    self.repository.save_product_inventory(
                        product,
                        stock=new_stock,
                        reserved_stock=(
                            new_reserved_stock
                        ),
                    )

                    # ------------------------------------------------
                    # Reservation → released
                    # ------------------------------------------------

                    self.repository.save_reservation(
                        reservation,
                        status="released",
                    )

                # ------------------------------------------------
                # Order status
                # ------------------------------------------------

                self.repository.save_order_status(
                    locked_order,
                    status=order_status,
                )

                return locked_order

        except ValueError:
            raise

        except Exception as exc:

            logger.exception(
                "[OrderService.release_order_inventory] "
                "庫存釋放失敗"
            )

            raise RuntimeError(
                "庫存釋放失敗"
            ) from exc