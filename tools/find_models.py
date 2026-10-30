"""List the local models that exist, from the Hugging Face Hub itself, instead of from blog posts.

    python tools/find_models.py [--since 2026-01-01] [--max-total 45] [--vram-gb 16] [--top 60]

The Hub's public API lists every repository that holds GGUF files, with each file's parameter count. The tool fetches the
1,000 most downloaded, most liked, newest and most recently updated of them, groups the uploads of one base model, and
prints the groups that fit the filters, most downloaded first. The fit column estimates whether the 8-bit file (about
1.07 bytes per parameter) or the 4-bit file (about 0.57) leaves 2 GB of headroom on the card. No key, no cost.
See docs/ENGINE_PLAN.md, "Finding local models".
"""
import argparse
import collections
import json
import re
import sys
import urllib.parse
import urllib.request

API='https://huggingface.co/api/models'
SORTS=('downloads','likes','createdAt','lastModified')
EXPAND=('gguf','createdAt','downloads','likes','lastModified')
SUFFIX=re.compile(r'(?i)[-_.]?(gguf|unsloth|bnb|4bit|8bit|imatrix|i1|mlx|awq|gptq)$')


def fetch(sort,limit):
    query=[('filter','gguf'),('pipeline_tag','text-generation'),('sort',sort),('direction','-1'),('limit',str(limit))]+[('expand[]',e) for e in EXPAND]
    with urllib.request.urlopen(API+'?'+urllib.parse.urlencode(query),timeout=120) as reply: return json.loads(reply.read().decode('utf-8'))


def base_name(repo_id):
    name=repo_id.split('/',1)[1]
    for _ in range(3): name=SUFFIX.sub('',name)
    return re.sub(r'(?i)[-_.]?gguf','',name).lower()


def groups(rows):
    by_base=collections.defaultdict(list)
    for repo_id,row in rows.items():
        total=(row.get('gguf') or {}).get('total')
        if not total: continue
        by_base[base_name(repo_id)].append(row)
    out=[]
    for base,items in by_base.items():
        items.sort(key=lambda r:-r.get('downloads',0));top=items[0];total=top['gguf']['total']/1e9
        active=re.search(r'(?i)A(\d+(?:\.\d+)?)B',top['id']);created=min(r.get('createdAt','')[:10] for r in items)
        out.append({'downloads':sum(r.get('downloads',0) for r in items),'base':base,'total_b':round(total,1),'active_b':float(active.group(1)) if active else None,
                    'architecture':top['gguf'].get('architecture'),'created':created,'uploads':len(items),'top_repo':top['id']})
    out.sort(key=lambda g:-g['downloads'])
    return out


def fit(total_b,vram_gb):
    usable=vram_gb-2
    if total_b*1.07<=usable: return '8-bit on card'
    if total_b*0.57<=usable: return '4-bit on card'
    return 'offload'


def main(argv=None):
    parser=argparse.ArgumentParser(description='List GGUF models on the Hugging Face Hub that fit a card.')
    parser.add_argument('--since',default='2026-01-01');parser.add_argument('--max-total',type=float,default=45.0)
    parser.add_argument('--vram-gb',type=float,default=16.0);parser.add_argument('--top',type=int,default=60);parser.add_argument('--json')
    args=parser.parse_args(argv);rows={}
    for sort in SORTS:
        for row in fetch(sort,1000): rows[row['id']]=row
    found=[g for g in groups(rows) if g['created']>=args.since and g['total_b']<=args.max_total]
    if args.json:
        with open(args.json,'w',encoding='utf-8') as out: json.dump(found,out,indent=0)
    print(f'{len(rows)} repositories, {len(found)} base models since {args.since} up to {args.max_total}B; top {args.top} by downloads')
    print(f"{'downloads':>10} {'total':>6} {'active':>6} {'architecture':<15} {'created':<10} {'fit on '+str(int(args.vram_gb))+' GB':<14} repository")
    for g in found[:args.top]:
        active='-' if g['active_b'] is None else f"{g['active_b']:g}B"
        print(f"{g['downloads']:>10} {g['total_b']:>5.1f}B {active:>6} {str(g['architecture']):<15} {g['created']:<10} {fit(g['total_b'],args.vram_gb):<14} {g['top_repo']}")
    return 0


if __name__=='__main__': sys.exit(main())
