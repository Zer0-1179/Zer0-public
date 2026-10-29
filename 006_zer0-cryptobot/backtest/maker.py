import sys
sys.argv=['x','/root/Zer0/006_Zer0_CryptoBot/backtest']; sys.path.insert(0,'.')
import numpy as np, entry_1h as E
d4,h1=E.load(); sigs=E.signals(d4)
def rates(v):
    out=[];nf=0
    for s in sigs:
        h=h1[s['coin']]; f,_=E.entry(s,h,v)
        if f and f[0][3]: nf+=1
        out.append(sum(E.manage(s,h,x)[0] for x in f)/len(f) if f else 0.0)
    return np.array(out),nf
base,_=rates(dict(kind='market'))
for k in (0.0,0.05,0.1):
  for fb in ('market','cancel'):
    row=[]
    for T in (1,2,4,6,8,12,16):
        r,nf=rates(dict(kind='atr',k=k,T=T,fb=fb)); d=r-base
        t=d.mean()/(d.std(ddof=1)/np.sqrt(len(d)))
        row.append(f"{T}h:{d.mean()*100:+.3f}(t{t:+.1f},約定{nf})")
    print(f"k={k} 期限後{fb}: "+"  ".join(row))
