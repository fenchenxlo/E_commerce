"""
URL configuration for E_commerce project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path,include
from commerce_shop.views import (
#    home,
    api_search,
    db_query_tool,
    product_list,
    add_to_cart,
    cart_detail,
    checkout,
    purchased_products,
    update_cart_item,
    remove_cart_item,
	delete_order_item,
    delete_order,
    ready_form,
    ecpay_mock_notify,
    payment_ok,
    download_orderPayment_json,
    payment_error,
    payment_callback,
#     create_ecpay_payment,
#     ecpay_callback,
    create_fake_ecpay_payment,
    fake_ecpay_cashier,
    fake_ecpay_callback,
    
)

# app_name = "commerce_shop"   # ⭐ 就是這一行 

urlpatterns = [    
#    path('', home, name='home'),
    path('api_search/', api_search, name='api_search'),
    path("admin-tools/query/", db_query_tool, name="db_query_tool"),  # 新增
    path('products/', product_list, name='product_list'),
    path('products/add/<int:product_id>/', add_to_cart, name='add_to_cart'),
    path('cart/', cart_detail, name='cart_detail'), # 購物車頁面
    path('checkout/', checkout, name='checkout'), # 結帳
    path('purchased_products/', purchased_products, name='purchased_products'),# user_order
    path('delete_order/<int:order_id>/', delete_order, name='delete_order'), # 刪除user_order
    path('delete_order_item/<int:order_item_id>/', delete_order_item, name='delete_order_item'), # 刪除user order_item
    path('cart/update/<int:product_id>/', update_cart_item, name='update_cart_item'),
    path('cart/remove/<int:product_id>/', remove_cart_item, name='remove_cart_item'),
    path("ready_form/", ready_form, name="ready_form"),
    path("payment_error/", payment_error, name="payment_error"),
    path("payment_callback/",payment_callback,name="payment_callback"),
    # 綠界支付
    path('ecpay_mock_notify/', ecpay_mock_notify, name='ecpay_mock_notify'),
    path('payment_ok/', payment_ok, name='payment_ok'),
    # 商家下載
    path("download_orderPayment_json/", download_orderPayment_json, name="download_orderPayment_json"),
#     path('payment/<int:order_id>/', create_ecpay_payment, name='create_ecpay_payment'),
#     path('payment/callback/', ecpay_callback, name='ecpay_callback'),
    path('payment/<int:order_id>/', create_fake_ecpay_payment, name='create_fake_ecpay_payment'),
    path('fake_ecpay/cashier/<str:transaction_id>/', fake_ecpay_cashier, name='fake_ecpay_cashier'),
    path('fake_ecpay/callback/', fake_ecpay_callback, name='fake_ecpay_callback'),
]
