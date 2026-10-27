"""Analysis tool (seed, 26 October 2026). GEPA rewrites this program; it runs in the sandbox on train.csv only.

It measures, on the training sessions only, whether moves tend to continue (momentum) or to undo themselves (reversal),
at several window lengths, and how strong each effect is against noise. It prints a short report for the roles.
"""
import csv
import math

with open('train.csv',newline='',encoding='utf-8') as handle:
    returns=[float(row['return']) for row in csv.DictReader(handle)]
n=len(returns)
mean=sum(returns)/n
sd=math.sqrt(sum((r-mean)**2 for r in returns)/(n-1))
print(f'train sessions {n}; mean return {mean:.6f}; sd {sd:.6f}')


def correlation(xs,ys):
    mx=sum(xs)/len(xs);my=sum(ys)/len(ys)
    sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys));sxx=sum((x-mx)**2 for x in xs);syy=sum((y-my)**2 for y in ys)
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else 0.0


print('window: correlation of the past window sum with the next return (t value); positive = continuation, negative = reversal')
for window in (1,2,3,5,10,20):
    past=[sum(returns[t-window+1:t+1]) for t in range(window-1,n-1)]
    nxt=[returns[t+1] for t in range(window-1,n-1)]
    rho=correlation(past,nxt);m=len(past)
    t_value=rho*math.sqrt((m-2)/max(1e-12,1-rho*rho))
    print(f'  {window:>2}: {rho:+.4f} (t {t_value:+.2f}, n {m})')
print('streaks: mean next return after k sessions in a row up or down (count)')
for k in range(1,6):
    after_up=[returns[t+1] for t in range(k-1,n-1) if all(r>0 for r in returns[t-k+1:t+1])]
    after_down=[returns[t+1] for t in range(k-1,n-1) if all(r<0 for r in returns[t-k+1:t+1])]
    up=f'{sum(after_up)/len(after_up):+.6f} ({len(after_up)})' if after_up else 'none'
    down=f'{sum(after_down)/len(after_down):+.6f} ({len(after_down)})' if after_down else 'none'
    print(f'  {k} up: {up}; {k} down: {down}')
