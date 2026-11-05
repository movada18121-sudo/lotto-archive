"""ลบพื้นเขียว (#00FF00) ออกจากภาพ แล้วตัดขอบใส ต้องมี Pillow:  py -m pip install --user pillow

  py tools/keyout.py assets/siamsi.png assets/siamsi_cut.png
"""
import sys

from PIL import Image


def keyout(src, dst, low=40, high=110):
    im = Image.open(src).convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            green = g - max(r, b)          # ยิ่งมากยิ่งเป็นพื้นเขียว
            if green <= low:
                continue
            alpha = 0 if green >= high else int(255 * (1 - (green - low) / (high - low)))
            g = max(r, b)                  # ลดขอบเขียวที่ติดวัตถุ (despill)
            px[x, y] = (r, g, b, min(a, alpha))
    box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if box:
        im = im.crop(box)
    im.save(dst)
    print(f"saved {dst} {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    keyout(sys.argv[1], sys.argv[2])
