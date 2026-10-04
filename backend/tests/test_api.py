"""End-to-end: import history, read a message, save it, plan, edit, approve. No API keys."""


def test_health(client, repo):
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "database": repo.describe()["backend"],
        "today": "2026-10-04",
    }


def test_full_workflow(client, sample_csv):
    imported = client.post(
        "/api/orders/import", files={"file": ("sales.csv", sample_csv, "text/csv")}
    ).json()
    assert imported["imported"] > 500 and imported["errors"] == []

    extracted = client.post(
        "/api/orders/extract",
        json={"text": "Hello, 1 chocolate cake and 6 cinnamon rolls on Tuesday please. - Anil"},
    ).json()
    assert extracted["provider"] == "rules"
    assert extracted["order_date"] == "2026-10-06"
    lines = [{"product_id": i["product_id"], "quantity": i["quantity"]} for i in extracted["items"]]

    order_body = {
        "order_date": extracted["order_date"],
        "items": lines,
        "customer_name": extracted["customer_name"],
        "source": "message",
        "original_input": extracted["original_input"],
        "extraction_confidence": extracted["confidence"],
    }
    created = client.post("/api/orders", json=order_body)
    assert created.status_code == 201
    assert {o["status"] for o in created.json()["created"]} == {"confirmed"}
    assert client.post("/api/orders", json=order_body).status_code == 409

    plan = client.post("/api/kitchen-plans/generate", json={}).json()
    assert plan["target_date"] == "2026-10-06"  # Monday is a closed day, so Tuesday
    rolls = next(i for i in plan["items"] if i["product_id"] == "cinnamon-roll")
    assert rolls["confirmed_quantity"] == 6
    assert plan["customer_requests"][0]["customer_name"] == "Anil"

    modified = client.post(
        f"/api/kitchen-plans/{plan['id']}/modify",
        json={"quantities": {"cinnamon-roll": rolls["recommended_quantity"] + 2}},
    ).json()
    assert modified["status"] == "modified"

    approved = client.post(f"/api/kitchen-plans/{plan['id']}/approve", json={}).json()
    assert approved["status"] == "approved"
    again = client.post(f"/api/kitchen-plans/{plan['id']}/approve", json={})
    assert again.status_code == 409

    assert client.get("/api/kitchen-plans").json()[0]["status"] == "approved"
    evaluation = client.get("/api/forecasts/evaluation").json()
    assert evaluation["sufficient_data"] and len(evaluation["metrics"]) == 2


def test_validation_errors(client):
    bad = client.post("/api/orders/import", files={"file": ("x.csv", b"foo,bar\n1,2\n")})
    assert bad.status_code == 422 and "missing required column" in bad.json()["detail"]

    unknown = client.post(
        "/api/orders",
        json={"order_date": "2026-10-06", "items": [{"product_id": "nope", "quantity": 1}]},
    )
    assert unknown.status_code == 422

    past = client.post("/api/kitchen-plans/generate", json={"target_date": "2026-01-01"})
    assert past.status_code == 422
    assert client.get("/api/kitchen-plans/missing").status_code == 404


def test_providers_report_local_fallbacks(client):
    body = client.get("/api/settings/providers").json()
    assert body["extraction"]["active"] == "rules"
    assert body["forecasting"]["active"] == "weekday_average"


def test_sample_import_is_labelled_and_export_contains_records(client):
    assert client.get("/api/business").json()["sample_data_loaded"] is False
    result = client.post("/api/orders/import-sample").json()
    assert result["imported"] > 0
    assert client.get("/api/business").json()["sample_data_loaded"] is True

    res = client.get("/api/export")
    assert res.status_code == 200
    assert "attachment" in res.headers["content-disposition"]
    body = res.json()
    assert len(body["orders"]) == result["imported"]
    assert {"business", "products", "customers", "forecasts", "kitchen_plans"} <= set(body)
