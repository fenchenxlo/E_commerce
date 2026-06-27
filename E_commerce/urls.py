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
from django.contrib import admin
from django.urls import path,include
from commerce_shop.views import (
    home,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
#     path("commerce_shop/", include(
#         ("commerce_shop.urls", "commerce_shop"),
#             namespace="commerce_shop"
#         )
#     ),
    path('commerce_shop/', include('commerce_shop.urls')),
    path('e_commerce_account/', include('allauth.urls')),
    path('accounts/', include('allauth.urls')),  # <<--- 這一行很重要
]
