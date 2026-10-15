from pathlib import Path
import struct
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root=Path(__file__).resolve().parents[1]; assets=root/'assets'; svg=assets/'devotionflow.svg'
renderer=QSvgRenderer(str(svg))
if not renderer.isValid(): raise RuntimeError('Invalid DevotionFlow SVG logo')
pngs=[]
for size in (16,24,32,48,64,128,256,512,1024):
    image=QImage(QSize(size,size),QImage.Format.Format_ARGB32_Premultiplied); image.fill(Qt.transparent)
    painter=QPainter(image); renderer.render(painter); painter.end()
    if size in (16,32,48,256):
        buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); image.save(buffer,'PNG'); pngs.append((size,bytes(buffer.data())))
    if size==1024: image.save(str(assets/'devotionflow.png'),'PNG')
header=struct.pack('<HHH',0,1,len(pngs)); entries=[]; offset=6+16*len(pngs)
for size,data in pngs:
    entries.append(struct.pack('<BBBBHHII',size if size<256 else 0,size if size<256 else 0,0,0,1,32,len(data),offset)); offset+=len(data)
(assets/'devotionflow.ico').write_bytes(header+b''.join(entries)+b''.join(data for _,data in pngs))
print('Generated PNG, ICO and macOS source icon from the SVG logo')
