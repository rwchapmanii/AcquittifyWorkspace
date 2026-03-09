from acquittify_router import classify_question
from acquittify_retriever import retrieve
from app import OLLAMA_URL, MODEL, PROJECT_ROOT

q = "What suppression arguments are available for a car search where the officer had no warrant?"
print('Running smoke test (script)...')
try:
    cls = classify_question(q, OLLAMA_URL, MODEL)
    print('Classification:', cls)
except Exception as e:
    print('Router error:', e)
    cls = {'primary_area': 'Search and Seizure'}

docs = retrieve(q, cls.get('primary_area'), k=5, chroma_dir=PROJECT_ROOT / 'Corpus' / 'Chroma')
print('Retrieved', len(docs), 'docs')
for i,d in enumerate(docs[:3]):
    print('\n--- DOC', i)
    print('title:', d.get('title'))
    print('source_type:', d.get('source_type'))
    print('chunk_index:', d.get('chunk_index'))
    print('score:', d.get('score'))
    print('excerpt:', d.get('text')[:300].replace('\n',' '))

print('Done')
