import sys
sys.argv=['x','/root/Zer0/006_Zer0_CryptoBot/backtest']; sys.path.insert(0,'.')
import numpy as np, entry_1h as E
d4,h1=E.load(); sigs=E.signals(d4)
def per_sig(v):
    out=[]
    for s in sigs:
        h=h1[s['coin']]; f,_=E.entry(s,h,v)
        if not f: out.append((None,0.0)); continue
        r=sum(E.manage(s,h,x)[0] for x in f)/len(f)
        out.append(('limit' if f[0][3] else 'fb', r))
    return out
base=[r for _,r in per_sig(dict(kind='market'))]
print("市場(成行)平均 %.3f%%/件" % (np.mean(base)*100))
for k in (0.1,0.2,0.3,0.4):
  for T in (4,6,8,10,12,16):
    res=per_sig(dict(kind='atr',k=k,T=T,fb='market'))
    L=[(r-b) for (t,r),b in zip(res,base) if t=='limit']
    F=[(r-b) for (t,r),b in zip(res,base) if t=='fb']
    tot=np.mean([r for _,r in res])*100
    print(f"ATR{k} {T:>2}h 全体{tot:+.3f}%  指値約定{len(L):>3}件 差{np.mean(L)*100:+.3f}%/件  期限成行{len(F):>3}件 差{np.mean(F)*100:+.3f}%/件")
