"""Build the desktop vector mark without optional imaging dependencies."""
from pathlib import Path
import math, struct, zlib

ASSETS = Path(__file__).resolve().parents[1] / "assets"

def rounded_distance(x,y,cx,cy,hw,hh,r):
    qx,qy=abs(x-cx)-hw+r,abs(y-cy)-hh+r
    return math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-r

def segment_distance(x,y,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)

def render(size):
    raw=bytearray()
    lines=[((30,20),(30,46)),((21,27),(25,27)),((21,34),(25,34)),
           ((36,27),(43,27)),((36,34),(43,34))]
    for py in range(size):
        raw.append(0)
        for px in range(size):
            samples=[]
            for sy in range(4):
                for sx in range(4):
                    x,y=(px+(sx+.5)/4)*64/size,(py+(sy+.5)/4)*64/size
                    if rounded_distance(x,y,32,32,30,30,14)>0:
                        samples.append((0,0,0,0));continue
                    t=y/64
                    base=tuple(round(a+(b-a)*t) for a,b in zip((49,120,230),(24,81,179)))
                    outline=abs(rounded_distance(x,y,32,33,17,16,4))<1.25
                    ink=outline or min(segment_distance(x,y,a,b) for a,b in lines)<1.15
                    samples.append((*( (247,251,255) if ink else base),255))
            alpha=sum(c[3] for c in samples)
            rgb=[round(sum(c[k]*c[3] for c in samples)/alpha) if alpha else 0 for k in range(3)]
            raw.extend((*rgb,round(alpha/16)))
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",size,size,8,6,0,0,0))+chunk(b"IDAT",zlib.compress(bytes(raw),9))+chunk(b"IEND",b"")

if __name__ == "__main__":
    sizes=(16,24,32,48,64,128,256)
    images=[render(size) for size in sizes]
    (ASSETS/"desktop-mark.png").write_bytes(images[2])
    offset=6+16*len(sizes)
    entries=[]
    for size,png in zip(sizes,images):
        entries.append(struct.pack("<BBBBHHII",size%256,size%256,0,0,1,32,len(png),offset))
        offset+=len(png)
    (ASSETS/"desktop-mark.ico").write_bytes(struct.pack("<HHH",0,1,len(sizes))+b"".join(entries)+b"".join(images))
