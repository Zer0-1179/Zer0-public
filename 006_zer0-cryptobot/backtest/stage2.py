import sys
sys.argv=['x','/root/Zer0/006_Zer0_CryptoBot/backtest']; sys.path.insert(0,'.')
import entry_1h as E
def V():
    v=[("成行(現行)",dict(kind="market")),("ATR0.3指値/8h/成行",dict(kind="atr",k=0.3,T=8,fb="market")),
       ("ATR0.3指値/12h/成行",dict(kind="atr",k=0.3,T=12,fb="market"))]
    for k in (0.2,0.3):
        for m in (0.25,0.5,0.75,1.0):
            for T in (8,12,24):
                v.append((f"OCO 戻{k}/追{m}/{T}h",dict(kind="oco",k=k,m=m,T=T,fb="market")))
    for w in (0.3,0.5,0.7):
        for T in (8,16,24):
            v.append((f"分割 成行{int(w*100)}%+ATR0.3/{T}h",dict(kind="split",k=0.3,T=T,w=w,fb="cancel")))
    return v
E.variants=V
E.main()
