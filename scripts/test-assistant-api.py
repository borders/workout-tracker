"""Assistant API integration checks. Local disposable MySQL only; never production.

Start the PHP test server with FIELDWORK_TESTING=1, FIELDWORK_CONFIG
pointing to a disposable database, FIELDWORK_PRIVATE_DIR to a private
temporary directory containing assistant-token. Then run with
ASSISTANT_TEST_TOKEN set to that token.
"""
import json
import os
import uuid
import copy
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor
urlopen=build_opener(HTTPCookieProcessor(CookieJar())).open

root=os.environ.get("ASSISTANT_TEST_ROOT","http://127.0.0.1:8089/workouts/api")
assert urlsplit(root).hostname in ("127.0.0.1","localhost"), "Tests must target localhost"
token=os.environ["ASSISTANT_TEST_TOKEN"]
origin=f"{urlsplit(root).scheme}://{urlsplit(root).netloc}"

def call(path, method="GET", payload=None, auth=True, extra=None):
    headers={"Authorization":"Bearer "+token} if auth else {}
    headers.update(extra or {})
    body=None if payload is None else json.dumps(payload).encode()
    if body is not None:headers["Content-Type"]="application/json"
    try:
        with urlopen(Request(root+"/"+path,data=body,method=method,headers=headers),timeout=10) as r:
            return r.status,json.load(r)
    except HTTPError as e:
        return e.code,json.load(e)

assert call("assistant.php?action=recent",auth=False)[0]==401
assert call("assistant.php?action=recent",extra={"Authorization":"Bearer "+"0"*64})[0]==401
assert call("assistant.php?action=append_set",method="GET")[0]==405
assert call("assistant.php?action=append_set",method="POST",payload={})[0]==400

# Seed an isolated workout through the ordinary sync endpoint.
id="assistant-test-"+uuid.uuid4().hex
workout={"id":id,"date":"2026-10-30","dateLabel":"2026-10-30","location":"test",
         "notes":"","raw":"","flags":[],"sets":[{"id":"prior-set","exercise":"Dumbbell bench press","weight":55,"reps":10,"kind":"reps","notes":"retain","raw":"original","flags":[],"details":{},"future":{"object":{},"array":[],"nested":[{},[],{"0":{}}]}}],"context":{},"futureMetadata":{"object":{},"array":[],"nested":[{},[],{"0":{}}]},"updatedAt":"2026-10-30T12:00:00Z"}
status,hello=call("sync.php?action=handshake",auth=False)
assert status==200,hello
operation={"operationId":str(uuid.uuid4()),"kind":"workouts","id":id,
           "baseRevision":0,"deleted":False,"document":workout}
status,result=call("sync.php?action=push",method="POST",
    payload={"operations":[operation]},auth=False,
    extra={"Origin":origin,"X-CSRF-Token":hello["csrf"]})
assert status==200 and not result["results"][0]["conflict"],result

status,recent=call("assistant.php?action=recent&limit=20")
assert status==200 and any(w["id"]==id for w in recent["workouts"]),recent
key=uuid.uuid4().hex
entry={"workoutId":id,"idempotencyKey":key,"exercise":"Barbell bench press",
       "weight":225,"reps":5,"details":{"buttFlat":True,"feetUp":False},"notes":"test"}
before=datetime.now(timezone.utc)
status,one=call("assistant.php?action=append_set",method="POST",payload=entry)
assert status==200 and one["saved"],one
time.sleep(1.1)
status,two=call("assistant.php?action=append_set",method="POST",payload=entry)
assert status==200 and one==two,"Retry must have identical receipt"
status,reordered=call("assistant.php?action=append_set",method="POST",payload={**entry,"details":{"feetUp":False,"buttFlat":True}})
assert status==200 and reordered==one,"Property order must not change idempotency"
status,reordered_body=call("assistant.php?action=append_set",method="POST",payload=dict(reversed(list(entry.items()))))
assert status==200 and reordered_body==one
for field in ("loggedAt","completedAt"):
    parsed=datetime.fromisoformat(one[field].replace('Z','+00:00'))
    assert before.timestamp()-1 <= parsed.timestamp() <= datetime.now(timezone.utc).timestamp()+1
assert one['loggedAt']==one['completedAt']
status,wrong=call("assistant.php?action=append_set",method="POST",payload={**entry,"reps":4})
assert status==400,wrong
status,recent=call("assistant.php?action=recent&limit=20")
match=next(w for w in recent["workouts"] if w["id"]==id)
assert len(match["sets"])==2 and match["sets"][-1]["reps"]==5,match
assert match['sets'][0]==workout['sets'][0], 'Existing set attributes changed'
assert match['sets'][-1]['loggedAt']==one['loggedAt']
assert match['sets'][-1]['completedAt']==one['completedAt']
# Pull through ordinary sync, as a second device would, to verify the whole document.
status,page=call('sync.php?action=pull&since=0',auth=False)
while not any(r['id']==id for r in page['records']) and page['more']:
    status,page=call('sync.php?action=pull&since='+str(page['cursor']),auth=False)
record=next(r for r in page['records'] if r['id']==id)
saved=record['document'];expected=copy.deepcopy(workout)
expected['sets'].append(match['sets'][-1]);expected['updatedAt']=one['loggedAt']
assert saved==expected, 'Append changed unrelated workout fields or JSON types'
assert record['revision']==one['revision']
# A genuine technique change must remain a rejected key reuse.
status,wrong=call('assistant.php?action=append_set',method='POST',payload={**entry,'details':{'buttFlat':True,'feetUp':True}})
assert status==400
# Browser edits before append are retained; stale edits after append must conflict.
edited=copy.deepcopy(saved);edited['notes']='Browser edit retained'
browser_op={"operationId":str(uuid.uuid4()),"kind":"workouts","id":id,"baseRevision":record['revision'],"deleted":False,"document":edited}
status,result=call('sync.php?action=push',method='POST',payload={'operations':[browser_op]},auth=False,extra={'Origin':origin,'X-CSRF-Token':hello['csrf']})
assert status==200 and not result['results'][0]['conflict']
browser_revision=result['results'][0]['record']['revision']
status,third=call('assistant.php?action=append_set',method='POST',payload={**entry,'idempotencyKey':uuid.uuid4().hex,'reps':3})
assert status==200 and third['saved']
stale_op={**browser_op,'operationId':str(uuid.uuid4()),'baseRevision':browser_revision}
status,conflict=call('sync.php?action=push',method='POST',payload={'operations':[stale_op]},auth=False,extra={'Origin':origin,'X-CSRF-Token':hello['csrf']})
assert status==200 and conflict['results'][0]['conflict']
latest=conflict['results'][0]['record']['document']
assert latest['notes']=='Browser edit retained' and len(latest['sets'])==3
assert latest['sets'][:2]==saved['sets']
assert latest['sets'][-1]['id']==third['setId']
print("PASS: denied anonymous access, validation, gate routing, JSON type preservation, timestamped append, exact/reordered retries, key misuse rejection, ordinary sync pull, and browser-edit interleavings")
