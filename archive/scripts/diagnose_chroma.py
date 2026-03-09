from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CHROMA_DIR = ROOT / 'Corpus' / 'Chroma'
print('CHROMA_DIR=', CHROMA_DIR)

try:
    import chromadb
    from chromadb.config import Settings
except Exception as e:
    print('chromadb import failed:', e)
    raise

client = chromadb.Client(Settings(persist_directory=str(CHROMA_DIR), anonymized_telemetry=False))
print('Client created')

try:
    col = client.get_collection('acquittify_corpus')
    print('Collection retrieved')
except Exception as e:
    print('get_collection failed, trying get_or_create:', e)
    col = client.get_or_create_collection(name='acquittify_corpus')
    print('Collection created')

def try_count(c):
    try:
        print('count ->', c.count())
    except Exception as e:
        print('count failed:', e)

try_count(col)

def try_get(c):
    for attempt in [
        lambda: c.get(include=['metadatas','documents'], limit=3),
        lambda: c.get(include=['metadatas','documents']),
    ]:
        try:
            out = attempt()
            print('get succeeded, keys:', list(out.keys()))
            m = out.get('metadatas')
            d = out.get('documents')
            print('metadatas len ->', len(m) if m else 0)
            if m and isinstance(m, list):
                print('meta[0] keys:', list(m[0].keys()))
            if d and isinstance(d, list):
                print('doc[0] excerpt:', (d[0] or '')[:200].replace('\n',' '))
            return
        except Exception as e:
            print('get attempt failed:', e)

try_get(col)

def try_query(c, qstr):
    try:
        out = c.query(query_texts=[qstr], n_results=5, include=['metadatas','documents'])
        docs = out.get('documents', [[]])[0]
        metas = out.get('metadatas', [[]])[0]
        print('query returned', len(docs), 'docs')
        if metas:
            print('meta[0] keys:', list(metas[0].keys()))
            print('meta[0] title:', metas[0].get('title'))
        if docs:
            print('doc[0] excerpt:', (docs[0] or '')[:300].replace('\n',' '))
    except Exception as e:
        print('query failed:', e)

try_query(col, 'warrant')
try_query(col, 'search warrant vehicle')

print('Done')
