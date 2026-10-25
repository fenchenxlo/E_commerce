# commerce_shop/urls.py

from django.urls import path

from commerce_shop.views import (
    api_search,
    db_query_tool,

    product_list,
    add_to_cart,
    cart_detail,
#    checkout,
	cart_checkout_page,

    purchased_products,
    enter_receiver_info,

    atm_payment_notify,
    cod_payment_notify,   # 【新增】
    cod_store_confirmed,

    delete_order_item,
    delete_order,
    cancel_order,   # 【新增】取消訂單

    update_cart_item,
    remove_cart_item,

    ready_form,
    ecpay_checkout_redirect,

    payment_error,
    payment_callback,

    ecpay_mock_notify,
    payment_ok,

    download_orderPayment_json,

    # create_fake_ecpay_payment,
    # fake_ecpay_cashier,
    # fake_ecpay_callback,
)


urlpatterns = [

    # ========================================================
    # 商品
    # ========================================================

    path(
        "api_search/",
        api_search,
        name="api_search",
    ),

    path(
        "admin-tools/query/",
        db_query_tool,
        name="db_query_tool",
    ),

    path(
        "products/",
        product_list,
        name="product_list",
    ),

    path(
        "products/add/<int:product_id>/",
        add_to_cart,
        name="add_to_cart",
    ),

    # ========================================================
    # Cart
    # ========================================================

    path(
        "cart/",
        cart_detail,
        name="cart_detail",
    ),

    path(
        "cart/update/<int:product_id>/",
        update_cart_item,
        name="update_cart_item",
    ),

    path(
        "cart/remove/<int:product_id>/",
        remove_cart_item,
        name="remove_cart_item",
    ),

    # ========================================================
    # 第一次 Checkout
    #
    # Cart
    #   ↓
    # OrderService
    # ========================================================
    
	path("cart_checkout_page/",cart_checkout_page,name="cart_checkout_page"),
	
    # path(
        # "checkout/",
        # checkout,
        # name="checkout",
    # ),

    # ========================================================
    # 收件資料
    # ========================================================

    path(
        "enter_receiver_info/<str:order_number>/",
        enter_receiver_info,
        name="enter_receiver_info",
    ),

    # ========================================================
    # Orders
    # ========================================================

    path(
        "purchased_products/",
        purchased_products,
        name="purchased_products",
    ),

    path(
        "delete_order/<int:order_id>/",
        delete_order,
        name="delete_order",
    ),

    # 【新增】取消待付款 / 付款失敗的訂單（同步 ecpay_mock、Bank Mock）
    path(
        "cancel_order/<int:order_id>/",
        cancel_order,
        name="cancel_order",
    ),

    path(
        "delete_order_item/<int:order_item_id>/",
        delete_order_item,
        name="delete_order_item",
    ),

    # ========================================================
    # Payment Callback
    # ========================================================

    path(
        "atm_payment_notify/",
        atm_payment_notify,
        name="atm_payment_notify",
    ),

    path(
        "cod_payment_notify/",
        cod_payment_notify,
        name="cod_payment_notify",
    ),
    
    path(
        "cod_store_confirmed/",
        cod_store_confirmed,
        name="cod_store_confirmed",
    ),

    path(
        "payment_error/",
        payment_error,
        name="payment_error",
    ),

    path(
        "payment_callback/",
        payment_callback,
        name="payment_callback",
    ),

    # ========================================================
    # ECPay Mock callback / result
    #
    # 【保留】
    # 這些是外部 Mock → Store 的 HTTP endpoint。
    # ========================================================

    path(
        "ecpay_mock_notify/",
        ecpay_mock_notify,
        name="ecpay_mock_notify",
    ),

    path(
        "payment_ok/",
        payment_ok,
        name="payment_ok",
    ),

    # ========================================================
    # ready_form
    # ========================================================

    path(
        "ready_form/",
        ready_form,
        name="ready_form",
    ),
    
    # ========================================================
    # 【新增】
    # ECPay Checkout Redirect
    # ========================================================

    path(
        "ecpay_checkout_redirect/",
        ecpay_checkout_redirect,
        name="ecpay_checkout_redirect",
    ),

    # ========================================================
    # 商家下載
    # ========================================================

    path(
        "download_orderPayment_json/",
        download_orderPayment_json,
        name="download_orderPayment_json",
    ),

    # ========================================================
    # Fake ECPay
    #
    # 【保留】
    # 先不刪除你舊有 demo 功能。
    # ========================================================

    # path(
        # "payment/<int:order_id>/",
        # create_fake_ecpay_payment,
        # name="create_fake_ecpay_payment",
    # ),

    # path(
        # "fake_ecpay/cashier/<str:transaction_id>/",
        # fake_ecpay_cashier,
        # name="fake_ecpay_cashier",
    # ),

    # path(
        # "fake_ecpay/callback/",
        # fake_ecpay_callback,
        # name="fake_ecpay_callback",
    # ),
]