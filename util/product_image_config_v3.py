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

def get_product_image(regex_name, pname):

    for model_name, config in IPHONE17_CONFIG.items():

        if model_name in regex_name:

            for color, img in config["colors"].items():
                if color in pname:
                    return f"static/iphone17/{img}"

            return f"static/iphone17/{config['default']}"

    return "static/iphone17/iphone-17-all.jpg" 