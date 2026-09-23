"""Setup figure, compact 4-panel: (a) schematic, (b) array with relay box and bank, (c) relay-box interior, (d) inverter."""
from PIL import Image, ImageOps, ImageDraw, ImageFont
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); P = os.path.join(ROOT, 'paper_figs', 'photos')
lab = ImageFont.truetype('arialbd.ttf', 64)
def photo(f, crop=None, size=(1400, 1050)):
    im = ImageOps.exif_transpose(Image.open(os.path.join(P, f)))
    if crop: w, h = im.size; im = im.crop((int(crop[0]*w), int(crop[1]*h), int(crop[2]*w), int(crop[3]*h)))
    return ImageOps.fit(im, size, Image.LANCZOS)
sch = Image.open(os.path.join(ROOT, 'paper_figs', 'fig15_setup_schematic.png')).convert('RGB')
W = 2 * 1400 + 40; sch_h = int(sch.height * W / sch.width); sch = sch.resize((W, sch_h), Image.LANCZOS)
pads = [('b', photo('IMG_20260914_170901.jpg')), ('c', photo('IMG_20260914_171647.jpg', (0.0, 0.15, 1.0, 0.90))), ('d', photo('IMG_20260914_181036.jpg', (0.0, 0.12, 1.0, 0.88)))]
# layout: schematic full width on top, three photos below (b) (c) (d) each 1/3 width
pw = (W - 80) // 3; ph = int(pw * 3 / 4)
sheet = Image.new('RGB', (W + 80, sch_h + ph + 120), 'white'); d = ImageDraw.Draw(sheet)
sheet.paste(sch, (40, 40))
y = sch_h + 80
for i, (k, im) in enumerate(pads):
    im = ImageOps.fit(im, (pw, ph), Image.LANCZOS); x = 40 + i * (pw + 40); sheet.paste(im, (x, y))
    d.rectangle((x + 12, y + 12, x + 112, y + 92), fill='white'); d.text((x + 24, y + 14), '(%s)' % k, fill='black', font=lab)
sheet.thumbnail((2400, 2400), Image.LANCZOS); sheet.save(os.path.join(ROOT, 'paper_figs', 'fig16_setup_composite.png'), optimize=True, dpi=(300, 300)); print('composite', sheet.size)
