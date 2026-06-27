from PIL import Image, ImageDraw, ImageFont
import os

colors = {
    "black": "#1c1c1e",
    "white": "#f2f2f2",
    "lavender": "#c9c3ff",
    "mist_blue": "#a7c7e7",
    "sage": "#b7c9a8",
    "cosmic_orange": "#ff7a3d",
    "deep_blue": "#1e3a8a"
}

output_dir = "static/iphone17"
os.makedirs(output_dir, exist_ok=True)

for name, color in colors.items():

    img = Image.new("RGB", (800, 800), color)
    draw = ImageDraw.Draw(img)

    text = f"iPhone 17\n{name.upper()}"

    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except:
        font = ImageFont.load_default()

    bbox = draw.multiline_textbbox((0, 0), text, font=font)

    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    draw.multiline_text(
        ((800 - w) / 2, (800 - h) / 2),
        text,
        fill="white",
        font=font,
        align="center"
    )

    img.save(os.path.join(output_dir, f"{name}.png"))

print("圖片產生完成！")