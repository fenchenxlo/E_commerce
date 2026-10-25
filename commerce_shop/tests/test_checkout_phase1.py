# ============================================================
# commerce_shop/tests/test_checkout_phase1.py
#
# 第一階段 Checkout 測試
#
# 測試目標：
#
# cart.html
#     ↓
# POST /api/checkout
#     ↓
# CheckoutSchema
#     ↓
# OrderService.create_order_from_cart()
#     ↓
# 建立 Order
#     ↓
# 建立 OrderItem
#     ↓
# 扣除 Product.stock
#     ↓
# 增加 Product.reserved_stock
#     ↓
# 建立 InventoryReservation
#     ↓
# 清空 CartItem
#
# 本測試「不進入第二階段付款流程」。
#
# 因此本檔案不測試：
#
# ECPayGateway
# ECPayMockAdapter
# BankMock
# PaymentService.create_payment()
#
# 這樣可以先確認：
#
# 「第一階段建立訂單」本身是正常的。
# ============================================================

import os
import sys
import django
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone

from commerce_shop.models import (
    Product,
    Cart,
    CartItem,
    Order,
    OrderItem,
    InventoryReservation,
    Payment,
)

from commerce_shop.services.order_service import OrderService


# ============================================================
# 第一階段 Checkout 測試
# ============================================================

class Phase1CheckoutIntegrationTest(TestCase):
    """
    測試第一階段：

        POST /api/checkout
                ↓
        CheckoutSchema
                ↓
        OrderService
                ↓
        建立 Order
                ↓
        建立 OrderItem
                ↓
        更新庫存
                ↓
        建立 InventoryReservation
                ↓
        清空 Cart
    """

    # ========================================================
    # setUp
    #
    # 每一個 test 都會重新建立一套測試資料。
    # ========================================================

    def setUp(self):

        # ----------------------------------------------------
        # 【新增】
        # 建立測試使用者
        # ----------------------------------------------------

        self.user = User.objects.create_user(
            username="test_phase1_user",
            password="test_password_123",
        )

        # ----------------------------------------------------
        # 【新增】
        # 建立購物車
        # ----------------------------------------------------

        self.cart = Cart.objects.create(
            user=self.user,
        )

        # ----------------------------------------------------
        # 【新增】
        # 建立測試商品
        #
        # 注意：
        #
        # Product.time 是 DateTimeField。
        #
        # 不能寫：
        #
        #     time="test"
        #
        # 必須使用 datetime。
        # ----------------------------------------------------

        self.product = Product.objects.create(
            name="測試商品",

            price=Decimal("100.00"),

            origin_price=Decimal("120.00"),

            source="test",

            # ------------------------------------------------
            # 【修改】
            # Product.time 是 DateTimeField
            # 所以使用 timezone.now()
            # ------------------------------------------------

            time=timezone.now(),

            url="https://example.com/test-product",

            rating=Decimal("5.0"),

            review_count=0,

            sales=0,

            stock=10,

            reserved_stock=0,

            is_deleted=False,

            owner=self.user,
        )

        # ----------------------------------------------------
        # 【新增】
        # 建立購物車商品
        #
        # 測試：
        #
        # 10 件庫存
        # 購買 2 件
        #
        # 預期：
        #
        # stock = 8
        # reserved_stock = 2
        # ----------------------------------------------------

        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,

            quantity=2,

            # ------------------------------------------------
            # CartItem.price 是購物車當下的價格快照
            # ------------------------------------------------

            price=Decimal("100.00"),
        )

        # ----------------------------------------------------
        # 【新增】
        # Django Test Client
        #
        # 用來測試真正的：
        #
        # POST /api/checkout
        # ----------------------------------------------------

        self.client = Client()

    # ========================================================
    # 測試 1
    #
    # 第一階段可以成功建立 Order
    # ========================================================

    def test_phase1_checkout_creates_order(self):
        """
        第一階段成功後：

            Cart
              ↓
            Order

        應該成功建立 Order。
        """

        # ----------------------------------------------------
        # 【新增】
        # 直接使用 OrderService。
        #
        # 這個測試主要確認 Service 本身。
        # ----------------------------------------------------

        service = OrderService()

        result = service.create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 Service 回傳成功
        # ----------------------------------------------------

        self.assertTrue(
            result["success"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 Order Number 有產生
        # ----------------------------------------------------

        self.assertTrue(
            result["order_number"]
        )

        self.assertTrue(
            result["order_number"].startswith("ORD-")
        )

        # ----------------------------------------------------
        # 【新增】
        # 從 DB 重新取得 Order
        # ----------------------------------------------------

        order = Order.objects.get(
            order_number=result["order_number"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 Order 屬於正確使用者
        # ----------------------------------------------------

        self.assertEqual(
            order.user,
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 第一階段建立訂單後：
        #
        # status 應該是 pending_payment
        # ----------------------------------------------------

        self.assertEqual(
            order.status,
            "pending_payment"
        )

    # ========================================================
    # 測試 2
    #
    # 第一階段建立 OrderItem
    # ========================================================

    def test_phase1_checkout_creates_order_items(self):
        """
        驗證：

            CartItem
                ↓
            OrderItem
        """

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        # ----------------------------------------------------

        result = OrderService().create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 找出剛剛建立的 Order
        # ----------------------------------------------------

        order = Order.objects.get(
            order_number=result["order_number"]
        )

        # ----------------------------------------------------
        # 【新增】
        # OrderItem 數量應該只有一筆
        # ----------------------------------------------------

        self.assertEqual(
            OrderItem.objects.filter(
                order=order
            ).count(),
            1
        )

        # ----------------------------------------------------
        # 【新增】
        # 取得 OrderItem
        # ----------------------------------------------------

        order_item = OrderItem.objects.get(
            order=order
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證商品
        # ----------------------------------------------------

        self.assertEqual(
            order_item.product,
            self.product
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證商品名稱快照
        # ----------------------------------------------------

        self.assertEqual(
            order_item.name,
            "測試商品"
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證購買數量
        # ----------------------------------------------------

        self.assertEqual(
            order_item.quantity,
            2
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證交易價格快照
        #
        # 注意：
        #
        # OrderItem.price
        # 不是重新讀 Product.price。
        #
        # 而是 Checkout 當下 CartItem.price。
        # ----------------------------------------------------

        self.assertEqual(
            order_item.price,
            Decimal("100.00")
        )

    # ========================================================
    # 測試 3
    #
    # 第一階段更新庫存
    # ========================================================

    def test_phase1_checkout_updates_inventory(self):
        """
        第一階段成功後：

            stock
                10 → 8

            reserved_stock
                0 → 2
        """

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        # ----------------------------------------------------

        OrderService().create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 重新從 DB 取得 Product
        # ----------------------------------------------------

        product = Product.objects.get(
            product_id=self.product.product_id
        )

        # ----------------------------------------------------
        # 【新增】
        # stock 應該減少 2
        # ----------------------------------------------------

        self.assertEqual(
            product.stock,
            8
        )

        # ----------------------------------------------------
        # 【新增】
        # reserved_stock 應該增加 2
        # ----------------------------------------------------

        self.assertEqual(
            product.reserved_stock,
            2
        )

    # ========================================================
    # 測試 4
    #
    # 第一階段建立 InventoryReservation
    # ========================================================

    def test_phase1_checkout_creates_inventory_reservation(self):
        """
        第一階段成功後：

            Order
              ↓
            InventoryReservation

        應該建立一筆 reserved 狀態的庫存保留紀錄。
        """

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        # ----------------------------------------------------

        result = OrderService().create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 取得 Order
        # ----------------------------------------------------

        order = Order.objects.get(
            order_number=result["order_number"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 取得 Reservation
        # ----------------------------------------------------

        reservation = InventoryReservation.objects.get(
            order=order,
            product=self.product,
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證數量
        # ----------------------------------------------------

        self.assertEqual(
            reservation.quantity,
            2
        )

        # ----------------------------------------------------
        # 【新增】
        # 第一階段應該是 reserved
        # ----------------------------------------------------

        self.assertEqual(
            reservation.status,
            "reserved"
        )

    # ========================================================
    # 測試 5
    #
    # 第一階段清空 Cart
    # ========================================================

    def test_phase1_checkout_clears_cart(self):
        """
        第一階段成功後：

            CartItem
                ↓
            DELETE

        購物車商品應該被清除。
        """

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        # ----------------------------------------------------

        OrderService().create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # CartItem 應該已經不存在
        # ----------------------------------------------------

        self.assertEqual(
            CartItem.objects.filter(
                cart=self.cart
            ).count(),
            0
        )

        # ----------------------------------------------------
        # 【新增】
        # Cart 本身仍然存在
        # ----------------------------------------------------

        self.assertTrue(
            Cart.objects.filter(
                user=self.user
            ).exists()
        )

    # ========================================================
    # 測試 6
    #
    # 第一階段不應建立 Payment
    # ========================================================

    def test_phase1_checkout_does_not_create_payment(self):
        """
        非常重要。

        第一階段只是：

            Cart
              ↓
            Order
              ↓
            OrderItem
              ↓
            InventoryReservation

        不應該在第一階段建立 Payment。

        Payment 應該留到第二階段：

            enter_receiver_info.html
                    ↓
            POST /api/checkout
                    ↓
            OrderService
                    ↓
            PaymentService
                    ↓
            ECPayGateway
        """

        # ----------------------------------------------------
        # 【新增】
        # 【保留】執行第一階段
        # ----------------------------------------------------

        # 【保留】執行第一階段
        service = OrderService()
		
        result = OrderService().create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # Payment 數量必須為 0
        # ----------------------------------------------------

        # 【保留】第一階段只能建立 Order
        # 不應該在第一階段建立 Payment
        self.assertEqual(
            Payment.objects.count(),
            0
        )

    # ========================================================
    # 測試 7
    #
    # 第一階段 Order 欄位
    # ========================================================

    def test_phase1_checkout_order_fields(self):
        """
        驗證 Order 的主要欄位。
        """

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        # ----------------------------------------------------

        result = OrderService().create_order_from_cart(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 取得 Order
        # ----------------------------------------------------

        order = Order.objects.get(
            order_number=result["order_number"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 使用者
        # ----------------------------------------------------

        self.assertEqual(
            order.user,
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # Order 狀態
        # ----------------------------------------------------

        self.assertEqual(
            order.status,
            "pending_payment"
        )

        # ----------------------------------------------------
        # 【新增】
        # Shipping Fee
        #
        # 目前 OrderService：
        #
        # SHIPPING_FEE = Decimal("60.00")
        # ----------------------------------------------------

        self.assertEqual(
            order.shipping_fee,
            Decimal("60.00")
        )

        # ----------------------------------------------------
        # 【新增】
        # 商品：
        #
        # 100 × 2 = 200
        #
        # 運費：
        #
        # 60
        #
        # Total：
        #
        # 260
        # ----------------------------------------------------

        self.assertEqual(
            order.total_amount,
            Decimal("260.00")
        )

        # ----------------------------------------------------
        # 【新增】
        # 第一階段尚未選擇付款方式
        #
        # OrderService 目前建立 Order 時：
        #
        # payment_method=""
        # ----------------------------------------------------

        self.assertEqual(
            order.payment_method,
            ""
        )

    # ========================================================
    # 測試 8
    #
    # 空購物車
    #
    # 必須失敗
    # ========================================================

    def test_phase1_checkout_empty_cart_returns_failure(self):
        """
        購物車沒有商品時：

            不應建立 Order
            不應修改庫存
        """

        # ----------------------------------------------------
        # 【新增】
        # 先刪除 CartItem
        # ----------------------------------------------------

        CartItem.objects.filter(
            cart=self.cart
        ).delete()

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        #
        # OrderService 會將 ValueError
        # 包裝成 RuntimeError。
        # ----------------------------------------------------

        with self.assertRaises(
            RuntimeError
        ):

            OrderService().create_order_from_cart(
                self.user
            )

        # ----------------------------------------------------
        # 【新增】
        # 不應建立 Order
        # ----------------------------------------------------

        self.assertEqual(
            Order.objects.filter(
                user=self.user
            ).count(),
            0
        )

        # ----------------------------------------------------
        # 【新增】
        # 商品庫存不得被修改
        # ----------------------------------------------------

        product = Product.objects.get(
            product_id=self.product.product_id
        )

        self.assertEqual(
            product.stock,
            10
        )

        self.assertEqual(
            product.reserved_stock,
            0
        )

    # ========================================================
    # 測試 9
    #
    # 庫存不足時必須 Rollback
    # ========================================================

    def test_phase1_insufficient_stock_rolls_back(self):
        """
        商品庫存只有 1，

        但是購物車要購買 2 件。

        因此：

            Order 不建立
            OrderItem 不建立
            InventoryReservation 不建立
            stock 不修改
            reserved_stock 不修改
            CartItem 保留
        """

        # ----------------------------------------------------
        # 【新增】
        # 將商品庫存改成 1
        # ----------------------------------------------------

        self.product.stock = 1

        self.product.reserved_stock = 0

        self.product.save(
            update_fields=[
                "stock",
                "reserved_stock",
            ]
        )

        # ----------------------------------------------------
        # 【新增】
        # 執行第一階段
        # ----------------------------------------------------

        with self.assertRaises(
            RuntimeError
        ):

            OrderService().create_order_from_cart(
                self.user
            )

        # ----------------------------------------------------
        # 【新增】
        # Order 不應建立
        # ----------------------------------------------------

        self.assertEqual(
            Order.objects.filter(
                user=self.user
            ).count(),
            0
        )

        # ----------------------------------------------------
        # 【新增】
        # OrderItem 不應建立
        # ----------------------------------------------------

        self.assertEqual(
            OrderItem.objects.count(),
            0
        )

        # ----------------------------------------------------
        # 【新增】
        # InventoryReservation 不應建立
        # ----------------------------------------------------

        self.assertEqual(
            InventoryReservation.objects.count(),
            0
        )

        # ----------------------------------------------------
        # 【新增】
        # 重新取得 Product
        # ----------------------------------------------------

        product = Product.objects.get(
            product_id=self.product.product_id
        )

        # ----------------------------------------------------
        # 【新增】
        # stock 必須維持 1
        # ----------------------------------------------------

        self.assertEqual(
            product.stock,
            1
        )

        # ----------------------------------------------------
        # 【新增】
        # reserved_stock 必須維持 0
        # ----------------------------------------------------

        self.assertEqual(
            product.reserved_stock,
            0
        )

        # ----------------------------------------------------
        # 【新增】
        # CartItem 必須保留
        #
        # 因為這次 checkout 失敗。
        # ----------------------------------------------------

        self.assertEqual(
            CartItem.objects.filter(
                cart=self.cart
            ).count(),
            1
        )

    # ========================================================
    # 額外 API 測試
    #
    # 驗證真正的：
    #
    # Django Client
    #     ↓
    # /api/checkout
    #     ↓
    # CheckoutSchema
    #     ↓
    # OrderService
    #
    # 而不是只測 Service。
    # ========================================================

    def test_phase1_api_checkout(self):
        """
        驗證真正 POST：

            /api/checkout

        第一階段不提供 order_number。

        因此 API 應該走：

            create_order_from_cart()
        """

        # ----------------------------------------------------
        # 【新增】
        # 登入
        # ----------------------------------------------------

        self.client.force_login(
            self.user
        )

        # ----------------------------------------------------
        # 【新增】
        # 第一階段不需要 order_number。
        #
        # CheckoutSchema 所有欄位都是 optional，
        # 因此 {} 可以通過 Schema。
        # ----------------------------------------------------

        response = self.client.post(
            "/api/checkout",
            data={},
            content_type="application/json",
        )

        # ----------------------------------------------------
        # 【新增】
        # HTTP Status
        # ----------------------------------------------------

        self.assertEqual(
            response.status_code,
            200
        )

        # ----------------------------------------------------
        # 【新增】
        # 解析 JSON
        # ----------------------------------------------------

        data = response.json()

        # ----------------------------------------------------
        # 【新增】
        # API 必須成功
        # ----------------------------------------------------

        self.assertTrue(
            data["success"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 必須回傳 order_number
        # ----------------------------------------------------

        self.assertIn(
            "order_number",
            data
        )

        self.assertTrue(
            data["order_number"]
        )

        # ----------------------------------------------------
        # 【新增】
        # Order 狀態
        # ----------------------------------------------------

        self.assertEqual(
            data["status"],
            "pending_payment"
        )

        # ----------------------------------------------------
        # 【新增】
        # DB 確認 Order 已建立
        # ----------------------------------------------------

        self.assertTrue(
            Order.objects.filter(
                order_number=data["order_number"],
                user=self.user,
            ).exists()
        )

        # ----------------------------------------------------
        # 【新增】
        # DB 確認 Cart 已清空
        # ----------------------------------------------------

        self.assertEqual(
            CartItem.objects.filter(
                cart=self.cart
            ).count(),
            0
        )