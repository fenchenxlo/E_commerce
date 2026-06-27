import pandas as pd
# from database.sqlite3_tools import Sqlite3Tools
import sqlite3
from pathlib import Path
import re


class XlsxToSQLite:
    def __init__(self, xlsx_path: str, db_path: str = "products.db"):        
        self.xlsx_path = Path(xlsx_path)
        self.db_path = Path(db_path)
        self.table_name = "products"

    # 1️⃣ 讀取 Excel
    def load_xlsx(self) -> pd.DataFrame:
#         return pd.read_excel(self.xlsx_path)
        return pd.read_excel(
            self.xlsx_path, engine='openpyxl',
            keep_default_na=False
        )
#         print(f"讀取檔案: {file_path}")

    # 2️⃣ 推斷 source
    def infer_source(self, row) -> str:
        url = str(row.get("url", "")).lower()
        bu = str(row.get("BU", "")).lower()
        pid = str(row.get("Id", ""))
        isPChome = str(row.get("isPChome", ""))
        
        # 1. url 最準
        if "pchome" in url:
            return "pchome"
        if "yahoo" in url:
            return "yahoo"

        # 2. BU
        if bu == "ec":
            return "pchome"

        # 3. Id pattern（PChome）
        if re.match(r"^[A-Z0-9]{5,}-\d+[A-Z0-9]+$", pid):
            return "pchome"

        # 4. couponActid
        coupon = row.get("couponActid")
        if pd.notna(coupon) and str(coupon) not in ("[]", "nan", ""):
            return "pchome"
        
        if isPChome == '':
            return "yahoo"
        
        return "unknown"

    # 3️⃣ 清理 / 正規化
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [c.strip() for c in df.columns]

        # 自動填 source（覆蓋原本空值）
        df["source"] = df.apply(self.infer_source, axis=1)

        # couponActid
        if "couponActid" in df.columns:
            df["couponActid"] = df["couponActid"].astype(str)

        # 價格
        for col in ["price", "originPrice"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # review_count
        if "review_count" in df.columns:
            df["review_count"] = pd.to_numeric(
                df["review_count"], errors="coerce"
            )

        return df

    # 4️⃣ 建表
    def create_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        """建立資料表"""
        sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id TEXT,
                cateId TEXT,
                picS TEXT,
                picB TEXT,
                name TEXT,
                regex_name TEXT,
                describe TEXT,
                price INTEGER,
                originPrice INTEGER,
                author TEXT,
                brand TEXT,
                publishDate TEXT,
                isPChome INTEGER,
                isNC17 INTEGER,
                couponActid TEXT,
                BU TEXT,
                source TEXT,
                time TEXT,
                url TEXT,
                rating TEXT,
                review_count INTEGER,
                sales TEXT
            );
            """
        cursor.execute(sql)

        conn.commit()
        conn.close()

    # 5️⃣ 寫入 SQLite
    def insert_to_sqlite(self, df: pd.DataFrame, if_exists="append"):
        conn = sqlite3.connect(self.db_path)
        df.to_sql(self.table_name, conn, if_exists=if_exists, index=False)
        conn.close()

    # 6️⃣ 一鍵執行
    def run(self, if_exists="append"):
        df = self.load_xlsx()
        df = self.clean_dataframe(df)
        self.create_table()
        self.insert_to_sqlite(df, if_exists=if_exists)

if __name__ == "__main__":
    xlsxPath = r"C:\Users\USER\Downloads\輸出iphone17檔案區\output_iphone17_with_regex_name.xlsx"
    dbPath = r"C:\Users\USER\AppData\Local\DBG\banana\youtube-成果發表\products.db"
            
    loader = XlsxToSQLite(
        xlsx_path=xlsxPath,
        db_path=dbPath
    )
    
#     sql3tool = Sqlite3Tools()
#     conn = sql3tool.connect_db(dbPath)
#     print('連線Sqlite3')
#     sql3tool.create_table(conn)
#     sql3tool.conn_close(conn)
#     print('關閉Sqlite3')
    loader.run(if_exists="append")
    
    print('寫入SQLite 完成~')
    
