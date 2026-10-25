# ============================================================
# 【新增】把超商取貨門市資訊從 Order 搬到 Payment
#
# 1. Payment 新增 cvs_store_name / cvs_store_address
# 2. 【重點】舊資料：把 Order 的門市資訊複製到該訂單的 COD Payment
#    （訂單沒有 COD Payment 的舊門市資料無處可放，會被捨棄）
# 3. Order 移除 cvs_store_name / cvs_store_address
# ============================================================

from django.db import migrations, models


def copy_cvs_from_order_to_payment(apps, schema_editor):
    Payment = apps.get_model("commerce_shop", "Payment")

    for payment in Payment.objects.filter(
        payment_method="COD"
    ).select_related("order"):
        if payment.order.cvs_store_name:
            payment.cvs_store_name = payment.order.cvs_store_name
            payment.cvs_store_address = payment.order.cvs_store_address
            payment.save(
                update_fields=["cvs_store_name", "cvs_store_address"]
            )


def copy_cvs_from_payment_to_order(apps, schema_editor):
    # 還原（migrate 退版）時，把 Payment 的門市資訊寫回 Order
    Payment = apps.get_model("commerce_shop", "Payment")

    for payment in Payment.objects.filter(
        payment_method="COD"
    ).exclude(cvs_store_name="").select_related("order"):
        order = payment.order
        order.cvs_store_name = payment.cvs_store_name
        order.cvs_store_address = payment.cvs_store_address
        order.save(
            update_fields=["cvs_store_name", "cvs_store_address"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("commerce_shop", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="cvs_store_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="超商取貨付款:使用者確認的取貨門市名稱",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="cvs_store_address",
            field=models.CharField(
                blank=True,
                default="",
                help_text="超商取貨付款:使用者確認的取貨門市地址",
                max_length=200,
            ),
        ),
        migrations.RunPython(
            copy_cvs_from_order_to_payment,
            copy_cvs_from_payment_to_order,
        ),
        migrations.RemoveField(
            model_name="order",
            name="cvs_store_name",
        ),
        migrations.RemoveField(
            model_name="order",
            name="cvs_store_address",
        ),
    ]
