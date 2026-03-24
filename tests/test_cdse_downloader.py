"""CDSE indirici modulu icin unit testler."""
import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cdse_downloader import CDSEDownloader


def _mock_json_response(payload: dict) -> Mock:
    """JSON donebilen basit bir requests.Response mock'u uretir."""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    response.headers = {}
    return response


def test_get_access_token_returns_bearer_token() -> None:
    """Token endpoint yaniti Bearer formata cevrilmelidir."""
    downloader = CDSEDownloader(timeout=5)
    response = _mock_json_response({"access_token": "token-123"})

    with patch("src.cdse_downloader.requests.post", return_value=response) as mock_post:
        token = downloader.get_access_token("demo-user", "demo-pass")

    assert token == "Bearer token-123"
    assert downloader.access_token == "Bearer token-123"
    assert mock_post.call_count == 1
    assert mock_post.call_args.kwargs["data"]["client_id"] == "cdse-public"
    assert mock_post.call_args.kwargs["timeout"] == 5


def test_search_products_parses_catalogue_response() -> None:
    """Arama yaniti standart urun sozluklerine cevrilmelidir."""
    downloader = CDSEDownloader(timeout=10)
    downloader.access_token = "Bearer test-token"
    payload = {
        "value": [
            {
                "Id": "product-001",
                "Name": "S2A_MSIL2A_20250101T101031_N0511_R022_T35SMD_20250101T120102",
                "ContentDate": {
                    "Start": "2025-01-01T10:10:31.000Z",
                    "End": "2025-01-01T10:10:36.000Z",
                },
                "Attributes": [
                    {"Name": "cloudCover", "Value": 12.5},
                ],
                "GeoFootprint": {"type": "Polygon", "coordinates": []},
            }
        ]
    }
    response = _mock_json_response(payload)

    with patch("src.cdse_downloader.requests.get", return_value=response) as mock_get:
        products = downloader.search_products(
            bbox=[26.0, 38.0, 27.0, 39.0],
            start_date="2025-01-01",
            end_date="2025-01-10",
            max_cloud_cover=20,
        )

    assert len(products) == 1
    product = products[0]
    assert product["product_id"] == "product-001"
    assert product["name"].startswith("S2A_MSIL2A")
    assert product["cloud_cover"] == 12.5
    assert product["download_url"].endswith("/product-001")

    request_headers = mock_get.call_args.kwargs["headers"]
    request_params = mock_get.call_args.kwargs["params"]
    assert request_headers["Authorization"] == "Bearer test-token"
    assert "SENTINEL-2" in request_params["$filter"]
    assert "cloudCover" in request_params["$filter"]
