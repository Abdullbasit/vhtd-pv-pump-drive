"""Fig. 12 (b)-(h): the setup photographs, two pages, large captions."""
from PIL import Image, ImageOps, ImageDraw, ImageFont
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); P = os.path.join(ROOT, 'paper_figs', 'photos')
W, H = 1400, 1050; pad = 36; cap_h = 130
font = ImageFont.truetype('arial.ttf', 52); lab = ImageFont.truetype('arialbd.ttf', 72)
def load(f, crop=None):
    im = ImageOps.exif_transpose(Image.open(os.path.join(P, f)))
    if crop:
        w, h = im.size; im = im.crop((int(crop[0]*w), int(crop[1]*h), int(crop[2]*w), int(crop[3]*h)))
    return im
def wrap(d, text, width):
    words = text.split(); lines = []; cur = ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=font) > width and cur: lines.append(cur); cur = w
        else: cur = t
    lines.append(cur); return lines
def sheet(rows, out):
    WF = 2*W + pad; heights = [H if len(r) == 2 else int(WF*0.76/(4/3)) for r in rows]
    sh = Image.new('RGB', (2*W + 3*pad, sum(heights) + len(rows)*(cap_h + pad) + pad), 'white'); d = ImageDraw.Draw(sh); y = pad
    for r, hh in zip(rows, heights):
        for j, (k, f, cap, crop) in enumerate(r):
            ww = W if len(r) == 2 else WF; im = ImageOps.fit(load(f, crop), (ww, hh), Image.LANCZOS); x = pad + j*(W + pad); sh.paste(im, (x, y))
            d.rectangle((x + 14, y + 14, x + 118, y + 104), fill='white'); d.text((x + 26, y + 16), '(%s)' % k, fill='black', font=lab)
            for li, line in enumerate(wrap(d, '(%s) %s' % (k, cap), ww)):
                d.text((x, y + hh + 14 + li*58), line, fill='black', font=font)
        y += hh + cap_h + pad
    sh.thumbnail((2000, 2700), Image.LANCZOS); sh.save(out, optimize=True, dpi=(220, 220)); print(out, sh.size, os.path.getsize(out))
b = ('b', 'IMG_20260914_170901.jpg', 'PV array (LONGi Hi-MO 7, 12S3P) with the relay box (grey) and the resistor-bank coils beside it', None)
c = ('c', 'IMG_20260914_170914.jpg', 'resistor bank: air-cooled coils on a frame; breakers select 2.8 to 10.4 kW', (0.05, 0.30, 0.95, 0.98))
d_ = ('d', 'IMG_20260914_171647.jpg', 'ESP32 four-relay box: R1 bank contact, R2 string isolator, supply, breaker', (0.0, 0.15, 1.0, 0.90))
e = ('e', 'IMG_20260914_171423.jpg', 'delivery pipe at the well head with the clamp-on ultrasonic flow transducers', None)
f_ = ('f', 'IMG_20260914_181036.jpg', '22 kW IGBT inverter (FS100R12KT3 six-pack): control board, DC link, U V W terminals', (0.0, 0.12, 1.0, 0.88))
g = ('g', 'IMG_20260914_181115.jpg', 'logging station: inverter, laptop on RS485, flow-meter transmitter on the wall', None)
h = ('h', 'IMG_20260914_171344.jpg', 'sprinkler irrigation of the alfalfa field: the water the drive delivers', None)
sheet([[b, c], [d_, e]], os.path.join(ROOT, 'paper_figs', 'fig15b_setup_photos.png'))
sheet([[f_], [g, h]], os.path.join(ROOT, 'paper_figs', 'fig15c_setup_photos.png'))
