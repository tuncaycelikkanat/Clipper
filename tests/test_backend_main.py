import pytest
from fastapi.testclient import TestClient
from backend.main import app, lifespan

def test_main_lifespan():
    with TestClient(app) as c:
        res = c.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        
        res_root = c.get("/")
        assert res_root.status_code == 200
        assert res_root.json()["name"] == "Clipper API"
