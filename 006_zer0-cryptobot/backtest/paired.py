import sys
sys.argv=['x','/root/Zer0/006_Zer0_CryptoBot/backtest']; sys.path.insert(0,'.')
import numpy as np, entry_1h as E
d4,h1=E.load(); sigs=E.signals(d4)
def rates(v):
    out=[]
    for s in sigs:
        h=h1[s['coin']]; f,_=E.entry(s,h,v)
        out.append(sum(E.manage(s,h,x)[0] for x in f)/len(f) if f else 0.0)
    return np.array(out)
base=rates(dict(kind='market'))
body=np.array([s['body'] for s in sigs])
rng=np.random.default_rng(0)
print(f"成行 平均{base.mean()*100:.3f}%  標準偏差{base.std()*100:.2f}%  n={len(base)}")
groups=[("実体<0.8",body<0.8),("0.8-1.5",(body>=0.8)&(body<1.5)),("≥1.5",body>=1.5)]
print("件数:", {g:int(m.sum()) for g,m in groups})
for name,v in [("ATR0.1/8h",dict(kind='atr',k=0.1,T=8)),("ATR0.2/8h",dict(kind='atr',k=0.2,T=8)),
               ("ATR0.3/6h",dict(kind='atr',k=0.3,T=6)),("ATR0.3/8h",dict(kind='atr',k=0.3,T=8)),
               ("ATR0.3/10h",dict(kind='atr',k=0.3,T=10)),("ATR0.3/12h",dict(kind='atr',k=0.3,T=12)),
               ("実体0.5/8h",dict(kind='body',k=0.5,T=8)),("実体0.5/10h",dict(kind='body',k=0.5,T=10)),
               ("ATR0.3/8h見送り",dict(kind='atr',k=0.3,T=8,fb='cancel'))]:
    r=rates(v); d=r-base
    t=d.mean()/(d.std(ddof=1)/np.sqrt(len(d)))
    bs=[rng.choice(d,len(d)).mean() for _ in range(4000)]
    p_pos=np.mean(np.array(bs)>0)
    by=" ".join(f"{g}:{d[m].mean()*100:+.2f}" for g,m in groups)
    print(f"{name:<14} 差平均{d.mean()*100:+.3f}%/件 t={t:+.2f} 改善確率(bootstrap){p_pos*100:.0f}%  実体別[{by}]")
