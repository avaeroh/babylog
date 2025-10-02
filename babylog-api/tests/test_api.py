from datetime import datetime, timezone

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200

def test_auth_required(client):
    # No API key -> should be 401 on a protected endpoint
    r = client.get("/last/nappyevent")  # protected
    assert r.status_code == 401

def test_log_and_get_nappy(client, auth_headers):
    # log pee
    r = client.post("/log/nappyevent", headers=auth_headers, json={"type":"pee","notes":"clear"})
    assert r.status_code == 201

    # log poo
    r = client.post("/log/nappyevent", headers=auth_headers, json={"type":"poo","notes":"mushy"})
    assert r.status_code == 201

    # last any nappy event
    r = client.get("/last/nappyevent", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["type"] in ("pee","poo")

    # last poo only
    r = client.get("/last/nappyevent?type=poo", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["type"] == "poo"

def test_log_and_get_feed(client, auth_headers):
    # log breast feed
    r = client.post("/log/feedevent", headers=auth_headers, json={
        "type": "breast", "side": "left", "duration_min": 20, "notes": "latched"
    })
    assert r.status_code == 201

    # fetch last feed
    r = client.get("/last/feedevent", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["type"] == "breast"
    assert body["data"]["side"] == "left"

def test_stats_periods(client, auth_headers):
    # basic stats endpoint (nappy events)
    r = client.get("/stats/nappyevents?period=24h", headers=auth_headers)
    assert r.status_code == 200
    assert "count" in r.json()

def test_invalid_period(client, auth_headers):
    r = client.get("/stats/nappyevents?period=5w", headers=auth_headers)  # unsupported unit
    # our handler maps ValueError -> 400; validation could be 422 depending on config
    assert r.status_code in (400, 422)

def test_delete_last_feed(client, auth_headers):
    # Ensure at least one feed exists
    client.post("/log/feedevent", headers=auth_headers, json={"type":"bottle","volume_ml":60})
    r = client.delete("/last/feedevent", headers=auth_headers)
    assert r.status_code == 204
    # Deleting again should 404 (nothing left)
    r = client.delete("/last/feedevent", headers=auth_headers)
    assert r.status_code == 404

def test_delete_last_nappyevent_any_and_type(client, auth_headers):
    client.post("/log/nappyevent", headers=auth_headers, json={"type":"pee","notes":"clear"})
    client.post("/log/nappyevent", headers=auth_headers, json={"type":"poo","notes":"mushy"})

    # Delete latest any (should remove poo)
    r = client.delete("/last/nappyevent", headers=auth_headers)
    assert r.status_code == 204

    # Now delete latest of type=pee (should remove pee)
    r = client.delete("/last/nappyevent?type=pee", headers=auth_headers)
    assert r.status_code == 204

    # Nothing left of type=pee -> 404
    r = client.delete("/last/nappyevent?type=pee", headers=auth_headers)
    assert r.status_code == 404
