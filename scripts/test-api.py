"""Destructive integration checks: use a dedicated disposable MySQL database only.
Run against the local PHP test server with FIELDWORK_TESTING=1, never production.
"""
import copy
import json
import os
import uuid
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
from urllib.parse import urlsplit

base = os.environ.get('SYNC_TEST_URL', 'http://127.0.0.1:8089/workouts/api/sync.php')
assert urlsplit(base).hostname in ('localhost', '127.0.0.1'), 'Integration tests require a disposable local server'
origin = '{0.scheme}://{0.netloc}'.format(urlsplit(base))
client = build_opener(HTTPCookieProcessor(CookieJar()))
def request(action, body=None, headers=None):
    headers = headers or {}
    data = None if body is None else json.dumps(body).encode()
    if data is not None: headers = {'Content-Type': 'application/json', **headers}
    try:
        with client.open(Request(base+'?action='+action, data=data, headers=headers)) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)
status, hello = request('handshake')
assert status == 200, hello
headers = {'Origin': origin, 'X-CSRF-Token': hello['csrf']}
identifier = 'api-test-'+uuid.uuid4().hex
workout = {'id': identifier, 'date':'2026-10-26', 'dateLabel':'2026-10-26','location':'test','notes':'original','raw':'','flags':[],'sets':[],'updatedAt':'2026-10-26T12:00:00Z','context':{},'futureMetadata':{'emptyObject':{},'emptyArray':[]}}
def operation(doc, revision=0):
    return {'operationId':str(uuid.uuid4()),'kind':'workouts','id':doc['id'],'baseRevision':revision,'deleted':False,'document':doc}
op = operation(workout)
assert request('push', {'operations':[op]}, {'Origin':origin})[0] == 403
assert request('push', {'operations':[op]}, {**headers,'Origin':'https://untrusted.example'})[0] == 403
assert request('push', {'operations':[{'bad':'payload'}]}, headers)[0] == 400
status, response = request('push', {'operations':[op]}, headers)
assert status == 200, response
accepted = response['results'][0]
assert not accepted['conflict']
assert accepted['record']['document']['futureMetadata'] == {'emptyObject':{},'emptyArray':[]}
revision = accepted['record']['revision']
assert request('push', {'operations':[op]}, headers)[1] == response, 'Retries must be idempotent'
changed = copy.deepcopy(op); changed['document']['notes'] = 'reused operation ID'
assert request('push', {'operations':[changed]}, headers)[0] == 400
losing = operation({**workout,'notes':'offline edit'}, 0)
status, conflict = request('push', {'operations':[losing]}, headers)
assert status == 200 and conflict['results'][0]['conflict']
assert conflict['results'][0]['record']['document']['notes'] == 'original'
resolved = operation({**workout,'notes':'resolved'}, revision)
status, response = request('push', {'operations':[resolved]}, headers)
assert status == 200 and not response['results'][0]['conflict']
resolved_revision = response['results'][0]['record']['revision']
# Crossing 500 current records exercises pull pagination and monotonic cursors.
for start in range(0, 505, 25):
    batch = [operation({**workout,'id':identifier+'-'+str(i)}) for i in range(start, min(start+25,505))]
    status, response = request('push', {'operations':batch}, headers)
    assert status == 200 and all(not item['conflict'] for item in response['results']), response
cursor = 0; seen = set(); pages = 0
while True:
    status, page = request('pull&since='+str(cursor))
    assert status == 200, page
    assert page['cursor'] >= cursor
    cursor = page['cursor']; pages += 1
    seen.update(record['id'] for record in page['records'])
    if not page['more']: break
assert pages >= 2 and identifier in seen
assert all(identifier+'-'+str(i) in seen for i in range(505))
assert request('pull&since=999999999999')[0] == 409
# Tombstones are revisioned, visible, and do not lose their operation history.
delete={'operationId':str(uuid.uuid4()),'kind':'workouts','id':identifier,'baseRevision':resolved_revision,'deleted':True,'document':None}
status, result = request('push', {'operations':[delete]}, headers)
assert status == 200 and result['results'][0]['record']['deleted']
print('PASS: real PHP/MySQL API, CSRF/origin rejection, validation, retry idempotency, operation-ID misuse, CAS conflicts/resolution, pagination, and tombstones')
