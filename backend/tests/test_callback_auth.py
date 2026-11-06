"""Offline signature regressions using SDK-generated fixtures; no providers."""
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator
from plivo.utils.signature_v3 import construct_post_url, get_signature_v3
from app import callback_auth as auth
from app.database import get_db
from app.routers import calls, sms
BASE='https://callbacks.example.com'
TOKEN='fixture-token'
SID='ACfixture'
class DB:
    values={}
    fail=False
    def get(self, model, key):
        if self.fail: raise RuntimeError('offline')
        return SimpleNamespace(value=self.values[key]) if key in self.values else None
    def query(self,*args): raise AssertionError('Rejected callback accessed business data')
@pytest.fixture
def setup(monkeypatch):
    for k in ['TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','PLIVO_AUTH_TOKEN']: monkeypatch.delenv(k,raising=False)
    cfg=SimpleNamespace(secure_runtime=True,public_base_url=BASE,twilio_account_sid=SID,twilio_auth_token=TOKEN,plivo_auth_token=TOKEN)
    monkeypatch.setattr(auth,'settings',cfg)
    db=DB(); app=FastAPI(); app.include_router(sms.router); app.include_router(calls.router)
    app.dependency_overrides[get_db]=lambda:db
    received=[]
    monkeypatch.setattr(sms.sms_engine,'record_inbound',lambda *a,**kw:received.append(kw))
    return TestClient(app),cfg,db,received

def signed(path,params,provider='twilio',token=TOKEN):
    if provider=='twilio': return {'x-twilio-signature':RequestValidator(token).compute_signature(BASE+path,params)}
    url=construct_post_url(BASE+path,dict(params)).decode()
    return {'x-plivo-signature-v3':get_signature_v3(token.encode(),url,b'fixture-nonce').decode(),'x-plivo-signature-v3-nonce':'fixture-nonce'}

@pytest.mark.parametrize('provider,path,params',[
    ('twilio','/sms/inbound',{'AccountSid':SID,'From':'+15550001111','Body':'Hello + world'}),
    ('plivo','/sms/plivo-inbound',{'From':'+15550001111','Text':'Hello + world'})])
def test_valid_proxy_callback_and_body_tampering(setup,provider,path,params):
    client,_,_,received=setup; headers=signed(path,params,provider)
    headers.update({'host':'internal:8000','x-forwarded-host':'evil.invalid','x-forwarded-proto':'http'})
    assert client.post(path,data=params,headers=headers).status_code==200
    params['Body' if provider=='twilio' else 'Text']='changed'
    assert client.post(path,data=params,headers=headers).status_code==403
    assert len(received)==1

@pytest.mark.parametrize('path',['/sms/status','/sms/inbound','/calls/status','/calls/recording','/calls/vm-saved','/calls/twiml/test'])
def test_unsigned_callbacks_blocked(setup,path):
    assert setup[0].post(path,data={'AccountSid':SID,'MessageSid':'fake','CallSid':'fake'}).status_code==403

@pytest.mark.parametrize('mode',['account','url','signature'])
def test_twilio_tampering(setup,mode):
    params={'AccountSid':SID};headers=signed('/sms/inbound',params)
    if mode=='account':params['AccountSid']='foreign-account'
    if mode=='url':headers=signed('/sms/status',params)
    if mode=='signature':headers={}
    assert setup[0].post('/sms/inbound',data=params,headers=headers).status_code==403

def test_twilio_get_query_signature(setup,monkeypatch):
    monkeypatch.setattr(calls,'_refresh',lambda db:None)
    monkeypatch.setattr(calls.voice,'bridge_twiml',lambda *args:'<Response/>')
    path='/calls/twiml/bridge?AccountSid='+SID+'&lead_phone=%2B15550001111'
    assert setup[0].get(path,headers=signed(path,{})).status_code==200
    assert setup[0].get(path+'&lead_id=changed',headers=signed(path,{})).status_code==403

@pytest.mark.parametrize('missing',['x-plivo-signature-v3','x-plivo-signature-v3-nonce'])
def test_missing_plivo_headers(setup,missing):
    params={'Text':'Hello'};headers=signed('/sms/plivo-inbound',params,'plivo');del headers[missing]
    assert setup[0].post('/sms/plivo-inbound',data=params,headers=headers).status_code==403

def test_plivo_v2_no_downgrade(setup):
    assert setup[0].post('/sms/plivo-status',data={'Status':'delivered'},headers={'x-plivo-signature-v2':'old','x-plivo-signature-v2-nonce':'old'}).status_code==403

def test_plivo_voice_query_signed(setup):
    path='/calls/plivo/status?lead_id=fixture';params={'CallStatus':'completed'};headers=signed(path,params,'plivo')
    assert setup[0].post(path,data=params,headers=headers).status_code==200
    assert setup[0].post(path+'2',data=params,headers=headers).status_code==403

@pytest.mark.parametrize('url',['','http://callbacks.example.com','https://user:pass@example.com','https://example.com?x=1'])
def test_invalid_canonical_config(setup,url):
    setup[1].public_base_url=url;params={'AccountSid':SID}
    assert setup[0].post('/sms/inbound',data=params,headers=signed('/sms/inbound',params)).status_code==503

def test_db_failure_does_not_use_stale_credentials(setup):
    setup[2].fail=True
    assert setup[0].post('/sms/inbound',data={'AccountSid':SID}).status_code==503

def test_stored_credentials_env_precedence(setup,monkeypatch):
    client,_,db,_=setup;db.values={'cfg:twilio_auth_token':'stored'};params={'AccountSid':SID}
    assert client.post('/sms/inbound',data=params,headers=signed('/sms/inbound',params,token='stored')).status_code==200
    monkeypatch.setenv('TWILIO_AUTH_TOKEN',TOKEN)
    assert client.post('/sms/inbound',data=params,headers=signed('/sms/inbound',params,token='stored')).status_code==403
    assert client.post('/sms/inbound',data=params,headers=signed('/sms/inbound',params)).status_code==200

@pytest.mark.parametrize('field,path,params',[('twilio_auth_token','/sms/inbound',{'AccountSid':SID}),('plivo_auth_token','/sms/plivo-inbound',{'Text':'hello'})])
def test_missing_credentials(setup,field,path,params):
    setattr(setup[1],field,'')
    assert setup[0].post(path,data=params).status_code==503

def test_signalwire_account_not_guessed(setup):
    params={'AccountSid':'signalwire-project'}
    assert setup[0].post('/sms/inbound',data=params,headers=signed('/sms/inbound',params)).status_code==403

def test_duplicate_params_and_json_rejected(setup):
    assert setup[0].post('/sms/inbound',content='AccountSid=a&AccountSid=b',headers={'content-type':'application/x-www-form-urlencoded'}).status_code==400
    assert setup[0].post('/sms/inbound',json={'AccountSid':SID}).status_code==415

def test_all_callback_routes_guarded_sender_untouched():
    for router in [sms.router,calls.router]:
        for route in router.routes:
            path=route.path;deps=[d.dependency for d in route.dependencies]
            if path.startswith('/calls/plivo/') or path in ['/sms/plivo-inbound','/sms/plivo-status']:assert auth.require_plivo_callback in deps,path
            if path.startswith('/calls/twiml/') or path in ['/sms/status','/sms/inbound','/calls/vm-saved','/calls/dial-status','/calls/amd-transfer-result','/calls/status','/calls/recording']:assert auth.require_twilio_callback in deps,path
            if path=='/sms/send':assert auth.require_twilio_callback not in deps

def test_cleared_stored_token_does_not_reuse_live_settings(setup):
    setup[2].values={'cfg:twilio_auth_token':''}
    assert setup[0].post('/sms/inbound',data={'AccountSid':SID}).status_code==503

def test_plivo_rejects_other_token_and_missing_config(setup):
    params={'Text':'Hello'}
    assert setup[0].post('/sms/plivo-inbound',data=params,headers=signed('/sms/plivo-inbound',params,'plivo',token='foreign')).status_code==403

def test_root_only_canonical_url(setup):
    setup[1].public_base_url=BASE+'/ambiguous-prefix';params={'AccountSid':SID}
    assert setup[0].post('/sms/inbound',data=params,headers=signed('/sms/inbound',params)).status_code==503
