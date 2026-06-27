import pandas as pd
from django.core.management.base import BaseCommand
from commerce_shop.models import Product
from datetime import datetime
from django.utils import timezone

class Command(BaseCommand):
    help = "Import products from Excel into SQLite"

    def add_arguments(self, parser):
        parser.add_argument("excel_file", type=str)

    def handle(self, *args, **options):
        df = pd.read_excel(options["excel_file"])
        columns = ["name", "cateId", "regex_name", "price", "source", "time", "url", "rating", "review_count", "sales", "is_deleted"]
        
	# 如果 Excel 沒有 is_deleted 欄位，就新增並填 False
        if 'is_deleted' not in df.columns:
            df['is_deleted'] = False

	# 重新整理欄位順序，如果缺欄位自動填 False
        columns = [col for col in columns if col in df.columns or col == 'is_deleted']
        df = df.reindex(columns=columns, fill_value=False)

	#df = df[columns]
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        
        for _, row in df.iterrows():
            
            time_value = row["time"]
            if pd.notnull(time_value):
                time_value = timezone.make_aware(time_value.to_pydatetime())
            else:
                time_value = None
                
            Product.objects.create(
                name=row["name"],
                cateId=row["cateId"],
                regex_name=row["regex_name"],
                price=row["price"],
                source=row["source"],
                time=time_value,
                url=row["url"],
                rating=row["rating"],
                review_count=row["review_count"],
                sales=row["sales"],
                is_deleted=bool(row["is_deleted"]),
            )
        self.stdout.write(self.style.SUCCESS("Products imported successfully"))