"""Content-bound shared gallery policy. No network, DB writes or image inference.

QQ official v4.29.1 normalizes received attachments to Image; no reviewed
per-attachment sticker discriminator is available. Unknown always fails closed.
An actual sticker format would still not prove that its content is non-private.
"""
import hashlib
import json
from pathlib import Path


def auto_collectible(event, attachment):
    # No permissive extras, filenames, MIME, GIF, face text or visual guesses.
    # A future supported adapter integration needs its own versioned evidence
    # contract and attachment-by-attachment tests before changing this result.
    return False


def _json(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def shared_file(packs, pack, relative, *, content=False):
    """Return verified bytes' path, or None. Recheck at the final send boundary.

    Local owner approvals are explicit, per-file SHA256, with a source reference.
    The bundled public catalog contains only reviewed public Git blob hashes;
    it never grants permission based on a directory/manifest/tag alone.
    """
    try:
        if not isinstance(pack,str) or not isinstance(relative,str):return None
        if pack.startswith('_') or '/' in pack or '\\' in pack:return None
        root=Path(packs).resolve(); file=(root/pack/relative).resolve()
        file.relative_to(root/pack)
        if not file.is_file() or file.stat().st_size>4*1024*1024:return None
        data=file.read_bytes()
        policy=_json(root/'shared_gallery_v1.json')
        entry=policy.get('files',{}).get(pack+'/'+relative.replace('\\','/'),{}) if policy.get('version')==1 else {}
        if (entry.get('basis')=='owner-explicit-share' and isinstance(entry.get('source'),str)
                and entry['source'].strip() and entry.get('sha256')==hashlib.sha256(data).hexdigest()):
            return data if content else str(file)
        catalog=_json(Path(__file__).with_name('public-gallery-source.json'))
        digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        # Reviewed public distribution snapshots prove content independently of
        # a local folder/manifest. Automatically collected upstream folders are
        # explicitly excluded when building this versioned public catalog.
        for published in catalog.get('published_sources',[]):
            if published.get('repository') and published.get('revision') and digest in published.get('git_blobs',[]):
                return data if content else str(file)
        manifest=_json(root/pack/'manifest.json'); source=manifest.get('source',{})
        if (isinstance(source,dict) and source.get('type')=='github'
                and 'https://github.com/'+str(source.get('repo'))==catalog.get('source')):
            if digest in catalog.get('git_blobs',[]):return data if content else str(file)
    except (OSError,ValueError,TypeError,AttributeError):pass
    return None


def shared_rows(packs):
    """Read-only, same policy for bot tools and authenticated Console views."""
    import sqlite3
    from contextlib import closing
    result=[];checked={}
    root=Path(packs)
    if not root.is_dir():return result
    for pack in sorted(root.iterdir()):
        db=pack/'index.db'
        if not db.is_file():continue
        try:
            with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
                for rel,tag,caption,keywords,mtime in conn.execute("SELECT path,tag,caption,COALESCE(keywords,''),mtime FROM memes"):
                    key=(pack.name,rel)
                    if key not in checked:checked[key]=shared_file(root,*key)
                    if checked[key]:result.append(dict(pack=pack.name,rel=rel,tag=tag or '',caption=caption or '',keywords=keywords or '',mtime=mtime or 0))
        except (OSError,sqlite3.Error):continue
    return result
