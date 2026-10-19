from httpx import AsyncClient

from tests.api.conftest import Headers
from tests.api.scrape import REQUESTS, TIMED, family_names, sample, scrape


async def test_serves_prometheus_text_without_a_key(http: AsyncClient) -> None:
    response = await http.get("/metrics")

    assert response.headers["content-type"].startswith("text/plain; version=")
    assert {
        "python_info",
        "flagstaff_http_requests",
        "flagstaff_http_request_duration_seconds",
    } <= family_names(response.text)


async def test_counts_requests_by_route_template_and_status(
    http: AsyncClient, as_admin: Headers
) -> None:
    for project in ("storefront", "billing"):
        await http.get(f"/projects/{project}", headers=as_admin)
    await http.get("/projects", headers=as_admin)

    exposition = await scrape(http)

    route = "/projects/{project_key}"
    assert sample(exposition, REQUESTS, method="GET", route=route, status="404") == 2.0
    assert sample(exposition, REQUESTS, method="GET", route="/projects", status="200") == 1.0
    assert sample(exposition, TIMED, method="GET", route=route) == 2.0


async def test_keeps_unknown_paths_and_methods_to_one_series_each(http: AsyncClient) -> None:
    for path in ("/wp-login.php", "/.env"):
        await http.get(path)
    await http.request("PROPFIND", "/projects")

    exposition = await scrape(http)

    assert sample(exposition, REQUESTS, method="GET", route="unmatched", status="404") == 2.0
    assert sample(exposition, REQUESTS, method="OTHER", route="/projects", status="405") == 1.0
