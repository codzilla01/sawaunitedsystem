from app.main import app
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def test_authentication_required(client):
    r = client.get('/api/v1/dashboard')
    assert r.status_code == 401


def test_real_estate_prevents_overlapping_reservations(auth, party):
    project = auth.post('/api/v1/real-estate/projects', json={
        'name':'مشروع تجريبي','country_code':'EG','city':'القاهرة'
    })
    assert project.status_code == 201, project.text
    unit = auth.post(f"/api/v1/real-estate/projects/{project.json()['id']}/units", json={
        'unit_code':'A-101','price':'2500000','currency':'EGP','area_sqm':'120'
    })
    assert unit.status_code == 201, unit.text
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(days=3)
    payload = {'unit_id':unit.json()['id'],'party_id':party['id'],'start_at':start.isoformat(),
               'expires_at':end.isoformat(),'deposit_amount':'50000','currency':'EGP'}
    first = auth.post('/api/v1/real-estate/reservations', json=payload)
    assert first.status_code == 201, first.text
    second_payload = dict(payload)
    second_payload['start_at'] = (start + timedelta(days=1)).isoformat()
    second_payload['expires_at'] = (end + timedelta(days=1)).isoformat()
    second = auth.post('/api/v1/real-estate/reservations', json=second_payload)
    assert second.status_code == 409


def test_food_direct_sale_decrements_stock_brokerage_does_not(auth, party):
    product = auth.post('/api/v1/food/products', json={
        'sku':'RICE-001','name':'أرز اختبار','stock_quantity':'10','currency':'EGP'
    })
    assert product.status_code == 201, product.text
    pid = product.json()['id']
    direct = auth.post('/api/v1/food/orders', json={
        'business_model':'direct','customer_party_id':party['id'],'country_code':'EG','currency':'EGP',
        'lines':[{'product_id':pid,'quantity':'3','unit_price':'100'}]
    })
    assert direct.status_code == 201, direct.text
    fulfilled = auth.post(f"/api/v1/food/orders/{direct.json()['id']}/fulfill")
    assert fulfilled.status_code == 200, fulfilled.text
    product_after = next(x for x in auth.get('/api/v1/food/products').json() if x['id']==pid)
    assert Decimal(str(product_after['stock_quantity'])) == Decimal('7.000')
    brokerage = auth.post('/api/v1/food/orders', json={
        'business_model':'brokerage','customer_party_id':party['id'],'supplier_party_id':party['id'],
        'country_code':'EG','currency':'EGP','commission_rate':'5',
        'lines':[{'product_id':pid,'quantity':'2','unit_price':'100'}]
    })
    assert brokerage.status_code == 201, brokerage.text
    brokerage_done = auth.post(f"/api/v1/food/orders/{brokerage.json()['id']}/fulfill")
    assert brokerage_done.status_code == 200, brokerage_done.text
    product_final = next(x for x in auth.get('/api/v1/food/products').json() if x['id']==pid)
    assert Decimal(str(product_final['stock_quantity'])) == Decimal('7.000')


def test_car_booking_overlap_and_maintenance_block(auth, party):
    car = auth.post('/api/v1/cars', json={
        'registration_no':'س و أ 123','make':'Toyota','model':'Corolla','country_code':'EG',
        'city':'القاهرة','daily_rate':'1200','currency':'EGP'
    })
    assert car.status_code == 201, car.text
    car_id = car.json()['id']
    start = datetime.now(timezone.utc) + timedelta(days=5)
    end = start + timedelta(days=2)
    payload = {'car_id':car_id,'party_id':party['id'],'start_at':start.isoformat(),
               'end_at':end.isoformat(),'currency':'EGP','total_amount':'2400','deposit_amount':'500'}
    first = auth.post('/api/v1/cars/bookings', json=payload)
    assert first.status_code == 201, first.text
    second = auth.post('/api/v1/cars/bookings', json=payload)
    assert second.status_code == 409
    block = auth.post('/api/v1/cars/maintenance', json={
        'car_id':car_id,'start_at':(end+timedelta(days=1)).isoformat(),
        'end_at':(end+timedelta(days=3)).isoformat(),'reason':'صيانة دورية'
    })
    assert block.status_code == 201, block.text
    blocked_booking = auth.post('/api/v1/cars/bookings', json={
        **payload,'start_at':(end+timedelta(days=1)).isoformat(),'end_at':(end+timedelta(days=2)).isoformat()
    })
    assert blocked_booking.status_code == 409


def test_contract_lifecycle_and_payment_currency(auth, party):
    contract = auth.post('/api/v1/contracts', json={
        'contract_no':'SAWA-TEST-001','title':'اتفاقية اختبار','business_unit_code':'REAL_ESTATE',
        'country_code':'EG','party_id':party['id'],'contract_type':'marketing','currency':'EGP',
        'total_value':'150000','start_date':'2026-12-01','end_date':'2027-12-01'
    })
    assert contract.status_code == 201, contract.text
    cid=contract.json()['id']
    for state in ['review','approved','sent','signed','active']:
        res=auth.post(f'/api/v1/contracts/{cid}/transition',params={'new_status':state})
        assert res.status_code == 200, res.text
    bad = auth.post(f'/api/v1/contracts/{cid}/transition',params={'new_status':'draft'})
    assert bad.status_code == 409
    payment = auth.post('/api/v1/finance/payments', json={
        'direction':'receipt','party_id':party['id'],'contract_id':cid,
        'business_unit_code':'REAL_ESTATE','country_code':'EG','amount':'5000',
        'currency':'MAD','method':'cash'
    })
    assert payment.status_code == 422
    good = auth.post('/api/v1/finance/payments', json={
        'direction':'receipt','party_id':party['id'],'contract_id':cid,
        'business_unit_code':'REAL_ESTATE','country_code':'EG','amount':'5000',
        'currency':'EGP','method':'cash'
    })
    assert good.status_code == 201, good.text


def test_unit_access_is_enforced_for_non_admin(client):
    from app.database import Base
    from app.main import app
    # An authenticated sales user without unit assignments must not read restricted module data.
    from app.database import get_db
    # use the test client's backing dependency session through the app dependency override
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    from app.models import User
    from app.security import hash_password
    db.add(User(email='sales@test.local',full_name='Sales User',password_hash=hash_password('Testing!123'),role='sales'))
    db.commit(); db.close()
    try: next(generator)
    except StopIteration: pass
    login=client.post('/api/v1/auth/login',json={'email':'sales@test.local','password':'Testing!123'})
    assert login.status_code==200
    response=client.get('/api/v1/real-estate/projects')
    assert response.status_code==403


def test_user_response_never_exposes_password_hash(auth):
    r = auth.get('/api/v1/users')
    assert r.status_code == 200
    assert r.json()
    assert 'password_hash' not in r.json()[0]
    assert 'mfa_secret_encrypted' not in r.json()[0]
    assert 'mfa_pending_secret_encrypted' not in r.json()[0]
    assert 'mfa_last_counter' not in r.json()[0]


def test_party_scope_is_required_for_non_admin(client):
    # Create a restricted user and assign the real-estate module.
    from app.database import get_db
    from app.models import User, BusinessUnit, UserBusinessUnit
    from app.security import hash_password
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    u = User(email='re-sales@test.local', full_name='RE Sales', password_hash=hash_password('Testing!123'), role='sales')
    db.add(u); db.flush()
    re = db.query(BusinessUnit).filter_by(code='REAL_ESTATE').first()
    db.add(UserBusinessUnit(user_id=u.id, business_unit_id=re.id)); db.commit(); db.close()
    try: next(generator)
    except StopIteration: pass
    r=client.post('/api/v1/auth/login',json={'email':'re-sales@test.local','password':'Testing!123'})
    assert r.status_code==200
    missing_scope=client.post('/api/v1/parties',json={'display_name':'بدون نشاط','country_code':'EG'})
    assert missing_scope.status_code==422
    scoped=client.post('/api/v1/parties',json={'display_name':'عميل عقاري','country_code':'EG','business_unit_codes':['REAL_ESTATE']})
    assert scoped.status_code==201, scoped.text
    listed=client.get('/api/v1/parties')
    assert listed.status_code==200 and len(listed.json())==1



def test_document_upload_is_private_and_download_requires_session(auth, party):
    upload = auth.post('/api/v1/documents', data={
        'entity_type':'party','entity_id':party['id'],'business_unit_code':'REAL_ESTATE'
    }, files={'file':('test-contract.pdf', b'%PDF-1.4\n%test pdf bytes', 'application/pdf')})
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()['id']
    download = auth.get(f'/api/v1/documents/{doc_id}/download')
    assert download.status_code == 200
    assert download.content.startswith(b'%PDF')


def test_admin_can_add_business_unit_and_country(auth):
    unit = auth.post('/api/v1/reference/business-units', json={
        'code':'SAWA_TEST','name_ar':'نشاط اختباري','name_en':'Test Venture'
    })
    assert unit.status_code == 201, unit.text
    country = auth.post('/api/v1/reference/countries', json={
        'code':'QA','name_ar':'قطر','name_en':'Qatar','default_currency':'QAR','timezone':'Asia/Qatar'
    })
    assert country.status_code == 201, country.text
