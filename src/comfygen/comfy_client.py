from __future__ import annotations

from pathlib import Path

import httpx

SAVE_WORKFLOW_PATH_TEMPLATE = "{base_url}/userdata/workflows%2F{filename}?overwrite=true"


class ComfyClient:
    def __init__(self, base_url: str, http_client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client()

    def health_check(self, timeout: float = 2.0) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/system_stats", timeout=timeout)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def system_stats(self) -> dict:
        response = self._client.get(f"{self.base_url}/system_stats", timeout=10.0)
        response.raise_for_status()
        return response.json()

    def upload_image(self, file_path: Path) -> str:
        with file_path.open("rb") as f:
            response = self._client.post(
                f"{self.base_url}/upload/image",
                files={"image": (file_path.name, f, "application/octet-stream")},
                timeout=30.0,
            )
        response.raise_for_status()
        return response.json()["name"]

    def save_workflow(self, filename: str, workflow: dict) -> None:
        url = SAVE_WORKFLOW_PATH_TEMPLATE.format(base_url=self.base_url, filename=filename)
        response = self._client.post(url, json=workflow, timeout=15.0)
        response.raise_for_status()
