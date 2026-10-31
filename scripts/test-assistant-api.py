"""Assistant API integration checks. Local disposable MySQL only; never production.

Start the PHP test server with FIELDWORK_TESTING=1, FIELDWORK_CONFIG
pointing to a disposable database, FIELDWORK_PRIVATE_DIR to a private
temporary directory containing assistant-token. Then run with
ASSISTANT_TEST_TOKEN set to that token.
"""
import json
import os
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

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
         "notes":"","raw":"","flags":[],"sets":[],"updatedAt":"2026-10-30T12:00:00Z"}
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
       "weight":225,"reps":5,"details":{"buttFlat":True},"notes":"test"}
status,one=call("assistant.php?action=append_set",method="POST",payload=entry)
assert status==200 and one["saved"],one
status,two=call("assistant.php?action=append_set",method="POST",payload=entry)
assert status==200 and one==two,"Retry must have identical receipt"
status,wrong=call("assistant.php?action=append_set",method="POST",payload={**entry,"reps":4})
assert status==400,wrong
status,recent=call("assistant.php?action=recent&limit=20")
match=next(w for w in recent["workouts"] if w["id"]==id)
assert len(match["sets"])==1 and match["sets"][0]["reps"]==5,match
print("PASS: denied anonymous access, validation, read, atomic append, exact retry, key misuse rejection")
