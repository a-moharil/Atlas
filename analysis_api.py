"""Opt-in remote model analysis; only called on user-submitted article text."""
import json, os, urllib.request

def analyse_full_text(payload):
    text=str(payload.get('text','')).strip()
    if len(text)<800: raise ValueError('Provide at least 800 characters of the article text; a headline is not enough.')
    if len(text)>18000: raise ValueError('Maximum length 18,000 characters.')
    key=os.environ.get('ATLAS_OPENAI_API_KEY','')
    if not key:
        return {'available':False,'explanation':'Deep analysis requires ATLAS_OPENAI_API_KEY in the server environment. No external model was contacted.'}
    model=os.environ.get('ATLAS_AI_MODEL','gpt-4.1-mini')
    rubric=(
        'You are a rigorous comparative media analyst. Analyze ONLY the user-supplied text and do not infer additional reporting. '
        'Return valid JSON with keys: overview (max 65 words), reported_claims (array <=4 of attributed claims), '
        'evidence_limitations (array <=3), perspective_missing (array <=3 of potentially omitted perspectives), '
        'article_framing (one of Lean Left, Center/Descriptive, Lean Right, Mixed, Undetermined), '
        'framing_confidence (Low, Medium, High), framing_rationale (specific wording and interpretation limits), '
        'rhetorical_cues (array <=4), questions_for_verification (array <=3). '
        'Geopolitics rarely fits the US left/right axis: use Undetermined unless direct textual evidence warrants a rating. '
        'Criticism of a leader/country does not by itself imply left/right. Academic writing is not automatically neutral. '
        'Separate reported claims from substantiated facts. Never fabricate external facts.'
    )
    payload={'model':model,'response_format':{'type':'json_object'},'temperature':0.1,
             'messages':[{'role':'system','content':rubric},{'role':'user','content':text}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=45) as response:
            result=json.load(response)
        return {'available':True,'analysis':json.loads(result['choices'][0]['message']['content']),
                'method':'User-requested analysis of pasted text, not independently fact-checked.', 'model':model}
    except Exception as e:
        raise ValueError('Article analysis unavailable: '+str(e)[:180]) from e

def compare_feed_excerpts(records):
    """On-demand, carefully bounded synthesis of feed metadata, NOT full articles."""
    if len(records)<2:
        return {'available':False,'explanation':'At least two substantively related publisher excerpts are required for cross-source synthesis.'}
    key=os.environ.get('ATLAS_OPENAI_API_KEY','')
    if not key:
        return {'available':False,'explanation':'Cross-source model comparison requires ATLAS_OPENAI_API_KEY. The app has not transmitted any source material.'}
    model=os.environ.get('ATLAS_AI_MODEL','gpt-4.1-mini')
    sources=[{'source':r['source'],'title':r['title'],'feed_excerpt':r.get('summary',''),'published':r.get('published')} for r in records[:5]]
    rubric=(
        'Compare ONLY the RSS headline/excerpt records supplied; these are NOT full articles and some may address different events. '
        'Output JSON with keys: core_subject (one sentence), confirmed_common_elements (array of only details present in >=2 sources), '
        'source_specific_claims (array of objects {source,claim}), framing_differences (array of cited differences in word choice/selection), '
        'possible_missing_perspectives (array of cautious questions), contradictions (array of explicitly contradictory claims if any), '
        'limits (one sentence explaining tiny excerpt evidence). '
        'Never infer ideological classification from outlet source alone; do not assert differences if insufficient evidence, do not hallucinate.'
    )
    payload={'model':model,'response_format':{'type':'json_object'},'temperature':0.1,
             'messages':[{'role':'system','content':rubric},{'role':'user','content':json.dumps(sources,ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=45) as response:
            result=json.load(response)
        return {'available':True,'model':model,'analysis':json.loads(result['choices'][0]['message']['content']),
                'method':'User-requested model synthesis of supplied feed excerpts, not article full text or fact-checking.'}
    except Exception as e:
        raise ValueError('Comparison unavailable: '+str(e)[:180]) from e
