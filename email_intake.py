"""Email intake — receive an email, then extract the requested change (step 2)."""
from fastapi import APIRouter
from pydantic import BaseModel

import app as appmod
from email_extract import extract_request

router = APIRouter(prefix="/email", tags=["email"])


class IncomingEmail(BaseModel):
    sender: str
    subject: str = ""
    body: str


@router.post("/incoming")
async def incoming(email: IncomingEmail):
    print(f"[email] from={email.sender!r} ({len(email.body)} chars)")

    if appmod.GEMINI is None:
        return {"received": True, "error": "no GEMINI_API_KEY configured"}

    extracted = await extract_request(appmod.GEMINI, appmod.MODEL, email.body)
    print(f"[email] extracted: {extracted}")

    return {"received": True, "extracted": extracted}