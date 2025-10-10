from datetime import datetime, timedelta, timezone
from uuid import uuid4

def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_required(client):
    # No API key -> should be 401 on a protected endpoint
    r = client.get("/v1/event/nappy/last")
    assert r.status_code == 401


def test_create_generic_get_update_delete_event(client, auth_headers):
    # Create generic event
    r = client.post(
        "/v1/events",
        headers=auth_headers,
        json={
            "type": "nappy",
            "notes": "initial",
            "tags": ["night"],
            "metadata": {"detail": "poo"},
        },
    )
    assert r.status_code == 201
    created = r.json()
    event_id = created["id"]
    assert created["type"] == "nappy"
    assert created["notes"] == "initial"
    assert created["tags"] == ["night"]
    assert created["metadata"]["detail"] == "poo"

    # Get by id
    r = client.get(f"/v1/events/{event_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == event_id

    # Patch (update)
    r = client.patch(
        f"/v1/events/{event_id}",
        headers=auth_headers,
        json={"notes": "updated", "tags": ["night", "change"], "metadata": {"detail": "pee"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "updated"
    assert body["tags"] == ["night", "change"]
    assert body["metadata"]["detail"] == "pee"

    # Delete
    r = client.delete(f"/v1/events/{event_id}", headers=auth_headers)
    assert r.status_code == 204

    # Getting again should 404
    r = client.get(f"/v1/events/{event_id}", headers=auth_headers)
    assert r.status_code == 404


def test_typed_create_and_last(client, auth_headers):
    # Create via typed convenience endpoints
    r = client.post("/v1/event/nappy", headers=auth_headers, json={"notes": "pee"})
    assert r.status_code == 201
    r = client.post("/v1/event/feeding", headers=auth_headers, json={"notes": "bottle 120ml"})
    assert r.status_code == 201

    # Last nappy
    r = client.get("/v1/event/nappy/last", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["type"] == "nappy"
    assert "human" in body  # humanized delta string is present


def test_delete_last_by_type(client, auth_headers):
    client.post("/v1/event/nappy", headers=auth_headers, json={"notes": "pee"})
    client.post("/v1/event/nappy", headers=auth_headers, json={"notes": "poo"})

    # Delete latest nappy
    r = client.delete("/v1/event/nappy/last", headers=auth_headers)
    assert r.status_code == 204

    # Delete latest nappy again (now only one left)
    r = client.delete("/v1/event/nappy/last", headers=auth_headers)
    assert r.status_code == 204

    # Nothing left -> 404
    r = client.delete("/v1/event/nappy/last", headers=auth_headers)
    assert r.status_code == 404


def test_list_events_filters_and_pagination(client, auth_headers):
    # Create three events with explicit timestamps for deterministic pagination
    base = datetime.now(timezone.utc)
    e1 = {"type": "nappy", "notes": "a", "ts": (base - timedelta(minutes=3)).isoformat()}
    e2 = {"type": "nappy", "notes": "b", "ts": (base - timedelta(minutes=2)).isoformat()}
    e3 = {"type": "feeding", "notes": "c", "ts": (base - timedelta(minutes=1)).isoformat()}
    for payload in (e1, e2, e3):
        r = client.post("/v1/events", headers=auth_headers, json=payload)
        assert r.status_code == 201

    # Filter by type
    r = client.get("/v1/events?type=nappy&limit=10", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert all(item["type"] == "nappy" for item in data["items"])
    assert len(data["items"]) == 2

    # Pagination with limit=2, default sort ts:desc
    r = client.get("/v1/events?limit=2", headers=auth_headers)
    assert r.status_code == 200
    page1 = r.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    # Next page using cursor
    cursor = page1["next_cursor"]
    r = client.get(f"/v1/events?limit=2&cursor={cursor}", headers=auth_headers)
    assert r.status_code == 200
    page2 = r.json()
    # We inserted 3 events total; 2 on first page -> 1 left
    assert len(page2["items"]) == 1


def test_stats_events(client, auth_headers):
    # Seed some events
    client.post("/v1/event/nappy", headers=auth_headers, json={"notes": "pee"})
    client.post("/v1/event/feeding", headers=auth_headers, json={"notes": "bottle"})

    # Global stats
    r = client.get("/v1/stats/events?period=24h", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "24h"
    assert "count" in body

    # Type-filtered stats
    r = client.get("/v1/stats/events?period=24h&type=nappy", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["extras"]["type"] == "nappy"


def test_invalid_period(client, auth_headers):
    r = client.get("/v1/stats/events?period=5w", headers=auth_headers)  # unsupported unit
    # ValueError is mapped to 400 by the app's exception handler
    assert r.status_code == 400


def test_invalid_sort_param(client, auth_headers):
    # invalid sort format should fail validation (422)
    r = client.get("/v1/events?sort=ts:sideways", headers=auth_headers)
    assert r.status_code == 422


def test_get_missing_event_404(client, auth_headers):
    rand = str(uuid4())
    r = client.get(f"/v1/events/{rand}", headers=auth_headers)
    assert r.status_code == 404


def test_admin_reset(client, auth_headers):
    # Seed a couple events
    r = client.post("/v1/event/nappy", headers=auth_headers, json={"notes": "pee"})
    assert r.status_code == 201
    r = client.post("/v1/event/feeding", headers=auth_headers, json={"notes": "bottle"})
    assert r.status_code == 201

    # Verify there is data
    r = client.get("/v1/events?limit=100", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 2

    # Reset
    r = client.post("/v1/admin/reset", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 2

    # Verify empty
    r = client.get("/v1/events?limit=100", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 0
