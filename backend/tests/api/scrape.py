from httpx import AsyncClient
from prometheus_client.parser import text_string_to_metric_families

REQUESTS = "flagstaff_http_requests_total"
TIMED = "flagstaff_http_request_duration_seconds_count"


async def scrape(http: AsyncClient) -> str:
    response = await http.get("/metrics")
    assert response.status_code == 200
    return response.text


# The value of the one sample with exactly these labels, or None if there is no such series.
def sample(exposition: str, name: str, **labels: str) -> float | None:
    for family in text_string_to_metric_families(exposition):
        for found in family.samples:
            if found.name == name and found.labels == labels:
                return found.value
    return None


def family_names(exposition: str) -> set[str]:
    return {family.name for family in text_string_to_metric_families(exposition)}
