"""Enrich existing catalog without downloading audio or altering projects/favorites."""
import hashlib
import json
import shutil
import sys
import urllib.parse
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from library import Library, now, catalog_lock
from search_engine import profile


def main():
    lib=Library()
    with catalog_lock(lib.root):
        enrich(lib)


def enrich(lib):
    target=lib.data/'catalog.json'; data=json.loads(target.read_text())
    scratch=lib.data/'discovery-research'; archives={}
    for p in scratch.glob('*.zip'):
        archives.setdefault(p.stem.rsplit('-',1)[-1],p)
    with lib.db() as db:
        # Keep the user's favorite/prepared copy as canonical if files repeat.
        preferred={r[0] for r in db.execute('SELECT asset_id FROM downloads')} | {r[0] for r in db.execute("SELECT asset_id FROM feedback WHERE value='favorite'")}
    grouped={}
    for a in data['assets']:
        if a['kind']=='sfx' and a.get('archive_member'):
            grouped.setdefault(a['download_url'],[]).append(a)
    hashed=0; errors=[]
    for url,records in grouped.items():
        path=archives.get(hashlib.sha256(url.encode()).hexdigest()[:12])
        if not path: continue
        try:
            with zipfile.ZipFile(path) as z:
                for a in records:
                    with z.open(a['archive_member']) as source:
                        digest=hashlib.file_digest(source,'sha256').hexdigest()
                    a['indexed_sha256']=digest;hashed+=1
        except (OSError,KeyError,zipfile.BadZipFile) as e:errors.append(str(e))
    hashes={}; duplicates=0
    source_counts=Counter(a['source_url'] for a in data['assets'])
    for a in sorted(data['assets'],key=lambda a:a['id'] not in preferred):
        digest=a.get('indexed_sha256')
        if digest and digest in hashes:
            a['duplicate_of']=hashes[digest];duplicates+=1
        elif digest:
            hashes[digest]=a['id'];a.pop('duplicate_of',None)
        if a['kind']=='sfx' and (a['title'].isdigit() or len(a['title'])<=2):
            a['title']=a.get('album','Efeito')+' · '+a['title']
        if a['kind']=='sfx' and 'collection_tags' in a:
            a['metadata_scope']='member' if a.get('archive_member') or source_counts[a['source_url']]>1 else 'individual'
            a['member_text']=a.get('archive_member') or urllib.parse.unquote(Path(urllib.parse.urlparse(a['download_url']).path).name)
        a['scene_profile']=profile(a)
        if a['kind']=='sfx' and 'collection_tags' in a:
            a['tags']=[v['label'] for v in a['scene_profile']['facets'].values()]
    data['enriched_at']=now()
    backup=lib.data/'catalog-backups'/('before-enrichment-'+data['enriched_at'].replace(':','-')+'.json')
    shutil.copy2(target,backup)
    temporary=target.with_suffix('.enriched.part');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2));temporary.replace(target)
    with lib.db() as db:
        for a in data['assets']:db.execute('UPDATE assets SET body=? WHERE id=?',(json.dumps(a,ensure_ascii=False),a['id']))
    report={'created':now(),'pack_members_hashed':hashed,'exact_duplicates_hidden':duplicates,'profiled':len(data['assets']),'errors':errors,'stats':lib.stats()}
    (lib.data/'enrichment-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
