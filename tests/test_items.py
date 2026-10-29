def product(name="RTX 4060"):
    return {"name": name, "price": 12999.00, "category": "GPU",
            "model": "4060", "stock_quantity": 5,
            "description": "Test product", "product_type": "Graphics card"}


def test_list_empty(client):
    response = client.get("/api/items")
    assert response.status_code == 200
    assert response.json() == []


def test_crud_product(client):
    created = client.post("/api/items", json=product())
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json()["name"] == "RTX 4060"

    assert len(client.get("/api/items").json()) == 1
    assert client.get(f"/api/items/{item_id}").json()["id"] == item_id

    updated = client.put(f"/api/items/{item_id}", json=product("RTX 4070"))
    assert updated.status_code == 200
    assert updated.json()["name"] == "RTX 4070"

    deleted = client.delete(f"/api/items/{item_id}")
    assert deleted.status_code == 204
    assert client.get("/api/items").json() == []


def test_validation_and_missing(client):
    bad = product()
    bad["price"] = -10
    assert client.post("/api/items", json=bad).status_code == 422
    assert client.get("/api/items/999").status_code == 404
    assert client.put("/api/items/999", json=product()).status_code == 404
    assert client.delete("/api/items/999").status_code == 404
