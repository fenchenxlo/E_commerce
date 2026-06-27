IPHONE17_CONFIG = {
    # 順序很重要：字串長的、範圍小的（Pro Max）放前面，普通的放後面
    "iPhone 17 Pro Max": {
        "default": "i17promax.jpg",
        "colors": {
            "銀色": "i17promax-silver.jpg",
            "宇宙橙色": "i17promax-cosmic_orange.jpg",
            "藏藍色": "i17promax-deep_blue.jpg",
        }
    },
    "iPhone 17 Pro": {
        "default": "i17pro.jpg",
        "colors": {
            "銀色": "i17pro-silver.jpg",
            "宇宙橙色": "i17pro-cosmic_orange.jpg",
            "藏藍色": "i17pro-deep_blue.jpg",
        }
    },
    "iPhone 17": {
        "default": "i17.jpg",
        "colors": {
            "白色": "i17-white.jpg",
            "黑色": "i17-black.jpg",
            "霧藍色": "i17-mist_blue.jpg",
            "薰衣草色": "i17-lavender.jpg",
            "鼠尾草色": "i17-sage.jpg",
        }
    }
}

def get_product_image(regex_name, pname):
    # 先確保轉成字串，避免 None 造成報錯
    regex_name = str(regex_name or "")
    pname = str(pname or "")
    
    # 合併兩個名稱，這樣不論顏色寫在 regex_name 還是 name 都能被搜到
    full_text = f"{regex_name} {pname}"
	
#    print("full_text: ", full_text)
	
    for model_name, config in IPHONE17_CONFIG.items():
        # 用 in 來比對型號
        if model_name in full_text:
            # 找到了對應型號，接著在合併後的文字裡找顏色
            for color, img in config["colors"].items():
                if color in full_text:
                    return f"static/iphone17/{img}"
            
            # 如果真的找不到任何顏色字眼，回傳該型號的預設圖片
            return f"static/iphone17/{config['default']}"

    # 完全對不上的防錯圖片
    return "static/iphone17/iphone-17-all.jpg"