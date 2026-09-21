"""FastAPI app: serve the page, stream a run over SSE, judge one typed prompt."""

import contextlib
import json
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException, Query
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


def _token_matches(given: str, expected: str) -> bool:
    # compare_digest raises TypeError on non-ASCII str, so compare bytes.
    return secrets.compare_digest(given.encode(), expected.encode())


def create_app(
    judge,
    load: Callable = load_corpus,
    token: str | None = None,
    max_cost: float = 0.50,
) -> FastAPI:
    token = token or secrets.token_urlsafe(16)
    running = False  # one paid run at a time, whoever asks

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await judge.aclose()

    app = FastAPI(title="Jev Wall", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PAGE.read_text(encoding="utf-8")

    @app.get("/taxonomy")
    async def get_taxonomy() -> list[dict]:
        return taxonomy.as_json()

    @app.get("/session")
    async def get_session() -> dict:
        return {"token": token}

    @app.get("/stream")
    async def stream(
        limit: int = DEFAULT_LIMIT,
        full: bool = False,
        stream_token: str = Query("", alias="token"),
    ) -> StreamingResponse:
        nonlocal running
        if not _token_matches(stream_token, token):
            raise HTTPException(status_code=403, detail="missing or wrong session token")

        def as_sse(iterator: AsyncIterator[str]) -> StreamingResponse:
            return StreamingResponse(
                iterator, media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
            )

        async def busy() -> AsyncIterator[str]:
            yield _sse({"type": "fatal", "message": "A run is already in progress."})

        if running:
            return as_sse(busy())
        running = True

        async def messages() -> AsyncIterator[str]:
            nonlocal running
            try:
                async with contextlib.aclosing(
                    run(load(None if full else limit), judge, max_cost=max_cost)
                ) as events:
                    async for event in events:
                        yield _sse(event)
            except (CostLimitError, CorpusError) as error:
                yield _sse({"type": "fatal", "message": str(error)})
            except Exception as error:  # noqa: BLE001 - an unexpected failure must reach the page
                yield _sse({"type": "fatal", "message": f"Run failed: {error}"})
            finally:
                running = False

        return as_sse(messages())

    @app.post("/judge")
    async def judge_one(
        request: JudgeRequest, judge_token: str = Header("", alias="X-Jevwall-Token")
    ) -> dict:
        if not _token_matches(judge_token, token):
            raise HTTPException(status_code=403, detail="missing or wrong session token")
        try:
            return asdict(await judge.judge(request.text))
        except JudgeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return app
