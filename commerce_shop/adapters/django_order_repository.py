# ============================================================
# commerce_shop/adapters/django_order_repository.py
# ============================================================

import logging

from commerce_shop.interfaces.order_repository import (
    OrderRepository,
)

from commerce_shop.models import (
    Cart,
    CartItem,
    Product,
    Order,
    OrderItem,
    InventoryReservation,
)


logger = logging.getLogger(__name__)


class DjangoOrderRepository(OrderRepository):
    """
    Django Order Repository。

    【新增】

    這是：

        OrderRepository

    的 Django ORM 實作。

    ============================================================
    重要規則
    ============================================================

    只有這個 Adapter 可以直接使用：

        .objects
        .select_for_update()
        .create()
        .save()
        .delete()

    OrderService：

        ❌ 不可以 ORM
        ❌ 不可以 .objects
        ❌ 不可以直接 .save()
        ❌ 不可以直接 .delete()

    ============================================================
    """

    # ========================================================
    # 第一階段：Cart
    # ========================================================

    def get_cart_for_update(
        self,
        user,
    ):
        """
        【新增】

        取得目前 User 的 Cart。

        select_for_update：

            防止同時建立兩張 Order 時，
            同一個 Cart 被重複處理。
        """

        try:

            return (
                Cart.objects
                .select_for_update()
                .filter(
                    user=user
                )
                .first()
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "取得 Cart 失敗"
            )

            raise RuntimeError(
                "取得購物車失敗"
            ) from exc

    def get_cart_items_for_update(
        self,
        cart,
    ):
        """
        【新增】

        取得 CartItem。

        同時鎖定：

            CartItem
            Product
        """

        try:

            return list(
                cart.items
                .select_related("product")
                .select_for_update()
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "取得 CartItem 失敗"
            )

            raise RuntimeError(
                "取得購物車商品失敗"
            ) from exc

    def clear_cart_items(
        self,
        cart,
    ) -> None:
        """
        【新增】

        第一階段成功後清空 Cart。
        """

        try:

            CartItem.objects.filter(
                cart=cart
            ).delete()

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "清空 CartItem 失敗"
            )

            raise RuntimeError(
                "清空購物車失敗"
            ) from exc

    # ========================================================
    # 第一階段：Order
    # ========================================================

    def create_order(
        self,
        *,
        user,
        shipping_fee,
        total_amount,
        status,
        payment_method,
    ):
        """
        【新增】

        建立 Order。
        """

        try:

            return Order.objects.create(
                user=user,

                shipping_fee=shipping_fee,

                total_amount=total_amount,

                status=status,

                payment_method=payment_method,
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "建立 Order 失敗"
            )

            raise RuntimeError(
                "建立訂單失敗"
            ) from exc

    def create_order_item(
        self,
        *,
        order,
        product,
        name,
        quantity,
        price,
    ):
        """
        【新增】

        建立 OrderItem。
        """

        try:

            return OrderItem.objects.create(
                order=order,

                product=product,

                name=name,

                quantity=quantity,

                price=price,
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "建立 OrderItem 失敗"
            )

            raise RuntimeError(
                "建立訂單商品失敗"
            ) from exc

    # ========================================================
    # 第一階段：Product
    # ========================================================

    def save_product_stock(
        self,
        product,
        *,
        stock,
        reserved_stock,
    ) -> None:
        """
        【新增】

        更新商品庫存。
        """

        try:

            product.stock = stock

            product.reserved_stock = (
                reserved_stock
            )

            product.save(
                update_fields=[
                    "stock",
                    "reserved_stock",
                ]
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "更新 Product 庫存失敗"
            )

            raise RuntimeError(
                "更新商品庫存失敗"
            ) from exc

    # ========================================================
    # 第一階段：InventoryReservation
    # ========================================================

    def create_inventory_reservation(
        self,
        *,
        order,
        product,
        quantity,
        status,
    ):
        """
        【新增】

        建立庫存預約。
        """

        try:

            return (
                InventoryReservation.objects.create(
                    order=order,

                    product=product,

                    quantity=quantity,

                    status=status,
                )
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "建立 InventoryReservation 失敗"
            )

            raise RuntimeError(
                "建立庫存預約失敗"
            ) from exc

    # ========================================================
    # 第二階段：Order
    # ========================================================

    def get_order_for_update(
        self,
        *,
        user,
        order_number,
    ):
        """
        【新增】

        依：

            user
            order_number

        找到指定訂單。

        ========================================================
        重要

        原本 OrderService：

            Order.objects
                .select_for_update()
                .filter(...)

        已經移到這裡。

        ========================================================
        """

        try:

            return (
                Order.objects
                .select_for_update()
                .filter(
                    order_number=order_number,
                    user=user,
                )
                .first()
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "取得指定 Order 失敗"
            )

            raise RuntimeError(
                "取得訂單失敗"
            ) from exc

    def save_order_checkout_data(
        self,
        order,
        *,
        receiver_name,
        receiver_phone,
        receiver_address,
        payment_method,
        remark,
    ) -> None:
        """
        【新增】

        儲存第二階段收件資訊。

        注意：

        不修改：

            total_amount
            shipping_fee

        因為這兩個值在第一階段已經決定。
        """

        try:

            order.receiver_name = (
                receiver_name
            )

            order.receiver_phone = (
                receiver_phone
            )

            order.receiver_address = (
                receiver_address
            )

            order.payment_method = (
                payment_method
            )

            order.remark = (
                remark
            )

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

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "更新 Order Checkout 資料失敗"
            )

            raise RuntimeError(
                "更新訂單收件資料失敗"
            ) from exc

    # ========================================================
    # Payment Callback
    # ========================================================

    def get_order_by_pk_for_update(
        self,
        *,
        order_pk,
    ):
        """
        【新增】

        Payment Callback 使用。

        依 PK 鎖定 Order。
        """

        try:

            return (
                Order.objects
                .select_for_update()
                .get(
                    pk=order_pk
                )
            )

        except Order.DoesNotExist as exc:

            raise ValueError(
                "找不到指定訂單"
            ) from exc

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "鎖定 Order 失敗"
            )

            raise RuntimeError(
                "取得訂單失敗"
            ) from exc

    def get_reservations_for_update(
        self,
        order,
    ):
        """
        【新增】

        取得訂單的庫存預約。

        同時鎖定：

            InventoryReservation
            Product
        """

        try:

            return list(
                order
                .inventory_reservations
                .select_related("product")
                .select_for_update()
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "取得 InventoryReservation 失敗"
            )

            raise RuntimeError(
                "取得庫存預約失敗"
            ) from exc

    def save_reservation(
        self,
        reservation,
        *,
        status,
    ) -> None:
        """
        【新增】

        更新 Reservation 狀態。
        """

        try:

            reservation.status = status

            reservation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "更新 Reservation 失敗"
            )

            raise RuntimeError(
                "更新庫存預約狀態失敗"
            ) from exc

    def save_product_reserved_stock(
        self,
        product,
        *,
        reserved_stock,
    ) -> None:
        """
        【新增】

        Payment Success：

            reserved_stock -= quantity
        """

        try:

            product.reserved_stock = (
                reserved_stock
            )

            product.save(
                update_fields=[
                    "reserved_stock",
                ]
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "更新 reserved_stock 失敗"
            )

            raise RuntimeError(
                "更新商品保留庫存失敗"
            ) from exc

    def save_product_inventory(
        self,
        product,
        *,
        stock,
        reserved_stock,
    ) -> None:
        """
        【新增】

        Payment Failed / Expired：

            stock += quantity
            reserved_stock -= quantity
        """

        try:

            product.stock = stock

            product.reserved_stock = (
                reserved_stock
            )

            product.save(
                update_fields=[
                    "stock",
                    "reserved_stock",
                ]
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "更新商品庫存失敗"
            )

            raise RuntimeError(
                "更新商品庫存失敗"
            ) from exc

    def save_order_status(
        self,
        order,
        *,
        status,
    ) -> None:
        """
        【新增】

        更新 Order.status。
        """

        try:

            order.status = status

            order.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        except Exception as exc:

            logger.exception(
                "[DjangoOrderRepository] "
                "更新 Order 狀態失敗"
            )

            raise RuntimeError(
                "更新訂單狀態失敗"
            ) from exc