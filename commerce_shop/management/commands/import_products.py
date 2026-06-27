from commerce_shop.models import Product
from datetime import datetime
from django.utils import timezone
import pandas as pd
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Import products from Excel into SQLite"

    def add_arguments(self, parser):
        parser.add_argument("excel_file", type=str)

    def handle(self, *args, **options):
        Product.objects.all().delete()
        df = pd.read_excel(options["excel_file"])

        columns = ["name", "cateId", "regex_name", "price", "source", "time",
                   "url", "rating", "review_count", "sales", "is_deleted"]

        # 如果 Excel 沒有 is_deleted 欄位，就補 False
        if 'is_deleted' not in df.columns:
            df['is_deleted'] = False

        # 補齊欄位
        columns = [col for col in columns if col in df.columns or col == 'is_deleted']
        df = df.reindex(columns=columns, fill_value=False)

        # 時間轉換
        df["time"] = pd.to_datetime(df["time"], errors="coerce")

        # =========================
        # ⭐ 重要：先依時間排序
        # =========================
        df = df.sort_values(by="time", na_position="first")

        # =========================
        # ⭐ groupby：其他欄位取「最後一筆」
        # =========================
        grouped_df = df.groupby(["name", "price", "source"], as_index=False).agg({
            "cateId": "last",
            "regex_name": "last",
            "time": "last",
            "url": "last",
            "rating": "last",
            "review_count": "last",
            "sales": "last",
            "is_deleted": "last",
        })

        # 計算 stock（出現次數）
        stock_series = df.groupby(["name", "price", "source"]).size().reset_index(name="stock")

        # 合併 stock
        grouped_df = pd.merge(grouped_df, stock_series,
                              on=["name", "price", "source"])

        # =========================
        # 寫入 DB
        # =========================
        for _, row in grouped_df.iterrows():

            time_value = row["time"]
            if pd.notnull(time_value):
                time_value = timezone.make_aware(time_value.to_pydatetime())
            else:
                time_value = None

            Product.objects.create(
                name=row["name"],
                cateId = None if pd.isna(row["cateId"]) else row["cateId"],
                regex_name=row["regex_name"],
                price=row["price"],
                source=row["source"],
                time=time_value,
                url=row["url"],
                rating=row["rating"],
                review_count=row["review_count"],
                sales=row["sales"],
                is_deleted=bool(row["is_deleted"]),
                stock=row["stock"],  # ⭐ 出現次數
            )

        self.stdout.write(self.style.SUCCESS("Products imported successfully"))