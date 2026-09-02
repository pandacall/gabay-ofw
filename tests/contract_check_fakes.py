from collections.abc import AsyncGenerator

from fastapi import HTTPException
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai.errors import APIError
from google.genai import types


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


class CannedModel(BaseLlm):
    model: str = "canned"
    responses: list[str]
    call_count: int = 0
    received_content_counts: list[int] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        assert llm_request.model, "llm_request.model must be set by the caller"
        self.received_content_counts.append(len(llm_request.contents))
        response = self.responses[self.call_count]
        self.call_count += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=response)],
            )
        )


class FailingModel(BaseLlm):
    model: str = "failing"
    status_code: int
    reason: str | None = None

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        assert llm_request.model, "llm_request.model must be set by the caller"
        raise APIError(
            self.status_code,
            {
                "message": "provider detail must not reach the user",
                "status": self.reason,
            },
        )
        yield


def auth(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{uid}"}
