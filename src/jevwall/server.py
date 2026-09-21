"""FastAPI app: serve the page, stream a run over SSE, judge one typed prompt."""

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from jevwall import taxonomy
from jevwall.corpus import DEFAULT_LIMIT, CorpusError, load_corpus
from jevwall.export import PAGE
from jevwall.judge import MAX_CHARS, JudgeError
from jevwall.runner import CostLimitError, run


class JudgeRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        if len(value) > MAX_CHARS:
            raise ValueError(f"text must be at most {MAX_CHARS} characters")
        return value


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def create_app(judge, load: Callable = load_corpus) -> FastAPI:
    app = FastAPI(title="Jev Wall")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PAGE.read_text()

    @app.get("/taxonomy")
    async def get_taxonomy() -> list[dict]:
        return taxonomy.as_json()

    @app.get("/stream")
    async def stream(
        limit: int = DEFAULT_LIMIT, full: bool = False, max_cost: float = 0.50
    ) -> StreamingResponse:
        async def messages() -> AsyncIterator[str]:
            try:
                async for event in run(load(None if full else limit), judge, max_cost=max_cost):
                    yield _sse(event)
            except (CostLimitError, CorpusError) as error:
                yield _sse({"type": "fatal", "message": str(error)})

        return StreamingResponse(
            messages(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/judge")
    async def judge_one(request: JudgeRequest) -> dict:
        try:
            return asdict(await judge.judge(request.text))
        except JudgeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return app
