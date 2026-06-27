import os
import pandas as pd

class mergeFiles:
    """批次清理欄位類別"""
    def __init__(self,keyWord,base_path=r'C:\Users\USER\Downloads'):
        self.keyWord = keyWord
        self.input_folder = base_path + r'\輸出檔案區'  # 替換為(清理過的)資料夾路徑
        self.output_folder = base_path + r"\輸出" + keyWord + "檔案區"    # 合併後輸出
        self.output_file = 'merged_' + keyWord + '.xlsx'  # 輸出的檔案名稱，可以改成 .json 格式
        
        
    # 讀取指定資料夾中的所有xlsx或json檔案，並合併成一個檔案
    # 合併並輸出為 Excel 檔案
    #    **`merge_excel_files`** 函數：
    #    * `keyWord` : 是檔名的keywrod,如: iphone17
    #    * `input_folder`：是資料夾的路徑，裡面存放著 `.xlsx` 或 `.json` 檔案。
    #    * `output_file`：合併後儲存的檔案名稱，可以是 `.xlsx` 或 `.json` 格式。
    #    * `output_format`：這個參數決定了輸出的格式，可以是 `'xlsx'` 或 `'json'`。
    def merge_excel_files(self,output_format='xlsx'):
        # 用來儲存所有合併後的資料
        all_data = []
        
        # 若 output 資料夾不存在就建立
        os.makedirs(self.output_folder, exist_ok=True)
        
        # 遍歷資料夾，找出所有的 .xlsx 檔案
        for file_name in os.listdir(self.input_folder):
            if file_name.endswith('.xlsx'):  # 只處理 .xlsx 檔案
                file_path = os.path.join(self.input_folder, file_name)
                    
                if self.keyWord in file_name:
                    # 讀取 Excel 檔案
                    df = pd.read_excel(
                        file_path,
                        keep_default_na=False
                    )

                    print(f"讀取檔案: {file_path}")                
                    
                    # 將讀取的資料加入 all_data 列表
                    all_data.append(df)

        # 將所有資料合併成一個 DataFrame
        combined_df = pd.concat(all_data, ignore_index=True)

        output_path = os.path.join(self.output_folder, self.output_file)
        
        # 根據使用者需求，輸出為 .xlsx 或 .json 檔案
        if output_format == 'xlsx':
            # 輸出為 Excel 檔案
            combined_df.to_excel(output_path, index=False)
            print(f"合併完成，檔案已儲存為 {self.output_file}")
        elif output_format == 'json':
            # 輸出為 JSON 檔案
            combined_df.to_json(output_path, orient='records', lines=True)
            print(f"合併完成，檔案已儲存為 {self.output_file}")

# 使用範例：
# keyWord = 'iphone17'
# input_folder = r'C:\Users\USER\Downloads\輸出檔案區'  # 替換為(清理過的)資料夾路徑
# output_folder = r"C:\Users\USER\Downloads\輸出" + keyWord + "檔案區"    # 合併後輸出
# output_file = 'merged_' + keyWord + '.xlsx'  # 輸出的檔案名稱，可以改成 .json 格式

  
# merge_excel_files(keyWord, input_folder, output_file, output_folder,output_format='xlsx')

# 如果你想輸出為 JSON 檔案，可以使用：
# merge_excel_files(input_folder, 'merged_data.json', output_format='json')

