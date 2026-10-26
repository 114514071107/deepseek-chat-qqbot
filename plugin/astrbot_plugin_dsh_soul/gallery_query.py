"""CLI for Console, never imports or constructs the plugin."""
import json
from pathlib import Path
import random
import sys
from gallery_policy import shared_rows

if __name__=='__main__':
    rows=shared_rows(Path(sys.argv[1])/'sticker_packs')
    if sys.argv[2]=='sample':
        candidates=[r for r in rows if r['tag']==sys.argv[3]]
        row=random.choice(candidates) if candidates else None
        print(json.dumps({'rel':'sticker_packs/'+row['pack']+'/'+row['rel']} if row else {'rel':''}))
    else:
        packs={}
        for row in rows:
            tags=packs.setdefault(row['pack'],{});tags[row['tag']]=tags.get(row['tag'],0)+1
        print(json.dumps({'packs':packs,'policy':'content-bound-shared-only'}))
