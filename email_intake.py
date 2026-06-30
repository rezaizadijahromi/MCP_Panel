"""
Email intake — receive (1) -> extract (2) -> propose (3) -> confirm & commit (4).

The webhook parks an actionable proposal; a human reviews it at /email/pending
and clicks Confirm, which is the ONLY point in this whole flow that writes to
the store.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

import app as appmod                 # reuse the Gemini client + model set up there
import project_store as store        # for commit_change on confirm
import email_pending as pending
from email_extract import extract_request
from email_propose import propose_from_extraction

router = APIRouter(prefix="/email", tags=["email"])


class IncomingEmail(BaseModel):
    sender: str
    subject: str = ""
    body: str


# ---------------------------------------------------------------- receive (1-3)
@router.post("/incoming")
async def incoming(email: IncomingEmail):
    print(f"[email] from={email.sender!r} ({len(email.body)} chars)")
    if appmod.GEMINI is None:
        return {"received": True, "error": "no GEMINI_API_KEY configured"}

    extracted = await extract_request(appmod.GEMINI, appmod.MODEL, email.body)
    proposal = propose_from_extraction(extracted)

    if proposal.get("actionable"):
        token = pending.add(proposal)
        proposal["token"] = token
        proposal["review_url"] = "/email/pending"
        print(f"[email] parked {token}: {proposal['changed']} -> awaiting confirm")
    else:
        print(f"[email] no action: {proposal['reason']}")

    return {"received": True, "extracted": extracted, "proposal": proposal}


# ------------------------------------------------------------- confirm (4)
@router.get("/pending", response_class=HTMLResponse)
def pending_page():
    return _pending_page_html()


@router.post("/confirm/{token}")
def confirm(token: str):
    item = pending.pop(token)
    if item is not None:                         # ignore stale / already-used tokens
        store.commit_change(item["project_id"], item["candidate_params"])
        print(f"[email] committed {item['project_id']}: {item['changed']}")
    return RedirectResponse(url="/email/pending", status_code=303)


@router.post("/reject/{token}")
def reject(token: str):
    pending.pop(token)                           # discard; nothing is written
    return RedirectResponse(url="/email/pending", status_code=303)


# ------------------------------------------------------------------- the page
def _pending_page_html() -> str:
    items = pending.all_items()
    if not items:
        cards = "<p>No pending changes.</p>"
    else:
        blocks = []
        for token, p in items:
            changed = ", ".join(f"{k} &rarr; {v}" for k, v in p["changed"].items())
            figs = ", ".join(f"{k}={v}" for k, v in p.get("key_figures", {}).items())
            blocks.append(f"""
            <div class="card">
              <h3>{p['project_name']} <small>({p['product']})</small></h3>
              <p><b>Requested:</b> {changed}</p>
              <p><b>New figures:</b> {figs or '&mdash;'}</p>
              <img src="/output/{p['drawing_file']}" alt="proposed drawing">
              <div class="actions">
                <form method="post" action="/email/confirm/{token}">
                  <button class="ok">Confirm &amp; save</button></form>
                <form method="post" action="/email/reject/{token}">
                  <button class="no">Reject</button></form>
              </div>
            </div>""")
        cards = "\n".join(blocks)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Pending changes</title><style>
  body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem}}
  .card{{border:1px solid #ccc;border-radius:8px;padding:1rem;margin-bottom:1rem}}
  .card img{{max-width:100%;border:1px solid #eee;margin-top:.5rem}}
  .actions{{display:flex;gap:.5rem;margin-top:.5rem}}
  button{{padding:.5rem 1rem;border:0;border-radius:6px;cursor:pointer;color:#fff}}
  .ok{{background:#1f7a3d}} .no{{background:#b03030}}
  small{{color:#777;font-weight:normal}}
</style></head><body>
<h1>Pending email changes</h1>
{cards}
</body></html>"""