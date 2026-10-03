import requests


class OllamaClient:
    def __init__(
        self,
        model="qwen2.5-coder:7b",
        host="http://localhost:11434",
    ):
        self.model = model
        self.host = host.rstrip("/")

    def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=300,
        )

        response.raise_for_status()

        data = response.json()

        return data["response"]