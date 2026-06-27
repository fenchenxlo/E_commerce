import re

IPHONE17_CONFIG = {

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

# 🔥 這裡就是你要的 regex function
def match_color(pname, color):
    return re.search(color, pname) is not None


def get_product_image(regex_name, pname):

    for model_name, config in IPHONE17_CONFIG.items():

        # ✔ model match
        if model_name == regex_name:

            # ✔ color match（改成 regex）
            for color, img in config["colors"].items():

                if match_color(pname, color):
                    return f"iphone17/{img}"

            # fallback default
            return f"iphone17/{config['default']}"

    # fallback 全部都沒 match
    return "iphone17/iphone-17-all.jpg"