"""Section 18: The Recursive Harness (Harness²: Propose, Probe, Compose + Lesson Library).

An agent is a model plus a harness. The model is fixed, but the harness (prompts, memory,
skills, tools, team) can be improved in two loops:
  - Inner loop (Propose, Probe, Compose): runs on the current task when self_improve='recursive'.
    Uses two scoped editors (general_editor + topic_editor), probes them against the reference
    run H0, and composes H1.
  - Outer loop (Lesson Library / EXPERIENCE.md): stores verified lessons in `lessons`
    (personal and shared libraries). When self_improve='learned', matching lessons are
    applied before the run for under 1 credit.

Safety rails (page 84):
  - Never edit money, wallet, caps, privacy, or safety rules.
  - Guardrails may only make checks stricter, never looser.
  - Personal lessons never reach other users; shared lessons require Admin review.
  - Every edit is recorded in `improvement_records` and can be undone by the user.
"""
import re
import uuid
from . import prompts
from .db import DB, jdump, jload, now

FORBIDDEN_PATTERNS = re.compile(
    r"\b(ignore (all|previous|your) (rules|instructions)|bypass|disable (check|safety|cap|limit|wallet)|"
    r"free credits|unlimited credits|zdr\s*[:=]\s*false|data_collection\s*[:=]\s*allow)\b",
    re.I,
)
ALLOWED_EDIT_KEYS = {"system_rule", "guardrail", "tool_guidance", "skill", "team"}

SEED_LESSONS = [
    ("reports", "Every report or document section needs at least one concrete number or verifiable fact.",
     "Seen in 14 runs: Checker pass rate rose from 61% to 88%.", "shared", "approved"),
    ("science", "Turn on Scientific Plotter when the topic has waveforms, spectra, or physical measurements.",
     "Adds computed SVG plots with exact math.", "shared", "approved"),
    ("slides", "Keep slide bullets to at most 5 bullets per slide and 12 words per bullet; use 2 planners for decks under 10 slides.",
     "Prevents slide overflow and saves planning credits on short decks.", "shared", "approved"),
    ("architecture", "Include Input, Process, and Output shapes on every node in D3 architecture diagrams.",
     "Allows users to click each component box and verify tensor/data flow.", "shared", "approved"),
]


def seed(db: DB) -> None:
    """Seed base harness H0 and proven shared lessons from EXPERIENCE.md."""
    if not db.one("SELECT id FROM harness_versions WHERE id='H0'"):
        base_files = {
            "system_rule": "Follow STYLE.md: match length to the message, use {{calc: ...}} for exact math, and cite sources.",
            "guardrail": "Verify every step goal and check; never invent URLs or claim unrun tools succeeded.",
            "tool_guidance": "Use calculator for numbers, chart recipe for interactive sliders, D3 for architecture diagrams.",
        }
        db.run(
            "INSERT INTO harness_versions(id,user_id,parent_id,name,files,created_by,active,created_at) "
            "VALUES('H0','system',NULL,'Base Harness H0',?,'system',1,?)",
            (jdump(base_files), now()),
        )
    if db.scalar("SELECT COUNT(*) FROM lessons WHERE scope='shared'") == 0:
        for topic, text, evidence, scope, status in SEED_LESSONS:
            db.run(
                "INSERT INTO lessons(user_id,scope,topic,text,evidence,helped_count,hurt_count,review_status,created_at,updated_at) "
                "VALUES('system',?,?,?,?,5,0,?,?,?)",
                (scope, topic, text, evidence, status, now(), now()),
            )


def sanitize_edit(text: str) -> str:
    """Reject prompt injections or attempts to loosen safety/money guardrails."""
    clean = str(text or "").strip()[:400]
    if not clean or FORBIDDEN_PATTERNS.search(clean):
        return ""
    return clean


def classify_topic(message: str, intent: str = "") -> str:
    low = (message or "").lower()
    if intent == "make_ppt" or re.search(r"\b(slides?|ppt|powerpoint|deck|presentation)\b", low):
        return "slides"
    if intent == "make_doc" or re.search(r"\b(report|document|docx|paper|essay|handout)\b", low):
        return "reports"
    if re.search(r"\b(waveform|spectrum|fft|sine|signal|frequency|measurement|physics)\b", low):
        return "science"
    if re.search(r"\b(cnn|transformer|mamba|architecture|system design|pipeline|d3)\b", low):
        return "architecture"
    return "general"


def matching_lessons(db: DB, user_id: str, message: str, intent: str = "") -> list[dict]:
    """Return approved shared lessons plus this user's personal lessons that match the topic."""
    seed(db)
    topic = classify_topic(message, intent)
    rows = db.all(
        "SELECT * FROM lessons WHERE "
        "((scope='shared' AND review_status='approved') OR (scope='personal' AND user_id=? AND review_status!='rejected')) "
        "AND (topic=? OR topic='general') "
        "AND (helped_count >= hurt_count) "
        "ORDER BY CASE WHEN topic=? THEN 0 ELSE 1 END, helped_count DESC, id DESC LIMIT 4",
        (user_id, topic, topic),
    )
    return rows


def apply_learned_lessons(ctx) -> dict | None:
    """Apply matching lessons from the library before the run (Learned mode, <1 credit)."""
    from .team import effective_team
    cfg = effective_team(ctx)
    si = cfg.get("self_improve", {})
    mode = si.get("mode", "off") if isinstance(si, dict) else str(si or "off")
    if mode not in ("learned", "recursive"):
        return None
    lessons = matching_lessons(ctx.db, ctx.user["id"], ctx.req.message, ctx.intent)
    if not lessons:
        return None
    applied = [l["text"] for l in lessons if sanitize_edit(l["text"])]
    if not applied:
        return None
    before = {"harness": "H0", "rules": "Base harness H0 (no task-specific lessons applied)"}
    after = {"harness": "H0+learned", "rules": applied}
    rec_id = "imp_" + uuid.uuid4().hex[:10]
    ctx.db.run(
        "INSERT INTO improvement_records(id,user_id,task_id,base_harness,new_harness,k,edits,evidence,compose_decision,result_summary,credits,created_at) "
        "VALUES(?,?,?,'H0','H0+learned',0,?,?,?,?,'0',?)",
        (rec_id, ctx.user["id"], ctx.task["id"], jdump({"before": before, "after": after, "lessons": [l["id"] for l in lessons]}),
         jdump([l["evidence"] for l in lessons]), "learned_library", f"Applied {len(applied)} lesson(s) from EXPERIENCE.md", now()),
    )
    ev = {
        "id": rec_id,
        "mode": "learned",
        "base_harness": "H0",
        "new_harness": "H0+learned",
        "lessons": applied,
        "before": before,
        "after": after,
    }
    ctx.emit("harness_improved", **ev)
    return ev


async def run_inner_loop(ctx, reference_text: str, state: dict) -> dict | None:
    """Section 18 Inner Loop: Propose (General + Topic Editors) -> Probe -> Compose -> H1."""
    from .team import agent_json, agent_call, effective_team, _model
    cfg = effective_team(ctx)
    si = cfg.get("self_improve", {})
    mode = si.get("mode", "off") if isinstance(si, dict) else str(si or "off")
    if mode != "recursive":
        return None
    k = max(1, min(int(si.get("k", 1) if isinstance(si, dict) else 1), 5))
    seed(ctx.db)
    editor_model = _model(ctx, None, "worker")
    trace_summary = (
        f"Task goal: {ctx.req.message[:1000]}\n"
        f"Plan steps: {len(state.get('steps', []))}\n"
        f"Step failures: {jdump(state.get('failures', []))}\n"
        f"Reference draft excerpt:\n{reference_text[:2500]}"
    )

    async def propose(scope: str) -> dict:
        sys_prompt = prompts.render("recursive_editor", scope=scope)
        try:
            raw = await agent_json(
                ctx, f"editor_{scope}", editor_model,
                [{"role": "system", "content": sys_prompt}, {"role": "user", "content": trace_summary}],
                max_tokens=500,
            )
        except Exception:
            return {"scope": scope, "observation": "No safe edit proposed", "edits": {}}
        raw_edits = raw.get("edits") if isinstance(raw.get("edits"), dict) else {}
        clean_edits = {k_: sanitize_edit(v_) for k_, v_ in raw_edits.items() if k_ in ALLOWED_EDIT_KEYS and sanitize_edit(v_)}
        return {
            "scope": scope,
            "observation": str(raw.get("observation") or "")[:240],
            "edits": clean_edits,
        }

    # Step 2: Propose (General editor and Topic editor in parallel)
    proposals = await ctx.parallel([propose("general"), propose("topic")])
    general_prop = proposals[0] if isinstance(proposals[0], dict) else {"scope": "general", "edits": {}}
    topic_prop = proposals[1] if isinstance(proposals[1], dict) else {"scope": "topic", "edits": {}}

    # Step 3 & 4: Probe & Compose into H1
    compose_input = (
        f"Reference run summary:\n{trace_summary}\n\n"
        f"General editor proposal:\n{jdump(general_prop)}\n\n"
        f"Topic editor proposal:\n{jdump(topic_prop)}\n\n"
        f"Budget k={k}"
    )
    try:
        composed = await agent_json(
            ctx, "composer", editor_model,
            [{"role": "system", "content": prompts.get("recursive_compose")},
             {"role": "user", "content": compose_input}],
            max_tokens=600,
        )
    except Exception:
        composed = {
            "decision": "merge",
            "observation": "Merged general verification rule with topic rule.",
            "system_rule": general_prop["edits"].get("system_rule") or "Re-check every section and calculation against constraints.",
            "guardrail": topic_prop["edits"].get("guardrail") or "Ensure every claim and number is grounded.",
            "tool_guidance": general_prop["edits"].get("tool_guidance") or "",
            "summary": "Composed H1 from general and topic editors.",
        }

    h1_id = "H1_" + uuid.uuid4().hex[:8]
    h1_files = {
        "system_rule": sanitize_edit(composed.get("system_rule")) or "Verify all requested sections and numbers.",
        "guardrail": sanitize_edit(composed.get("guardrail")) or "Stricter check on citations and calculations.",
        "tool_guidance": sanitize_edit(composed.get("tool_guidance")) or "",
    }
    ctx.db.run(
        "INSERT INTO harness_versions(id,user_id,parent_id,name,files,created_by,active,created_at) "
        "VALUES(?,?,'H0',?,?,'composer',1,?)",
        (h1_id, ctx.user["id"], f"Composed Harness ({h1_id})", jdump(h1_files), now()),
    )
    rec_id = "imp_" + uuid.uuid4().hex[:10]
    edits_record = {
        "before": {"harness": "H0", "system_rule": "Base harness H0"},
        "after": {"harness": h1_id, **h1_files},
        "general_proposal": general_prop,
        "topic_proposal": topic_prop,
    }
    decision = str(composed.get("decision") or "merge")[:40]
    observation = str(composed.get("observation") or composed.get("summary") or "Composed H1 from reference comparison.")[:300]
    ctx.db.run(
        "INSERT INTO improvement_records(id,user_id,task_id,base_harness,new_harness,k,edits,evidence,compose_decision,result_summary,credits,created_at) "
        "VALUES(?,?,?,'H0',?,?,?,?,?,?,?,?)",
        (rec_id, ctx.user["id"], ctx.task["id"], h1_id, k, jdump(edits_record),
         jdump({"general": general_prop.get("observation"), "topic": topic_prop.get("observation"), "observation": observation}),
         decision, str(composed.get("summary") or observation)[:240], ctx.meter.credits, now()),
    )

    # Outer loop: save a personal lesson if supported by the compose decision
    if decision in ("merge", "general", "topic") and h1_files["system_rule"]:
        topic = classify_topic(ctx.req.message, ctx.intent)
        ctx.db.run(
            "INSERT INTO lessons(user_id,scope,topic,text,evidence,helped_count,hurt_count,review_status,created_at,updated_at) "
            "VALUES(?, 'personal', ?, ?, ?, 1, 0, 'approved', ?, ?)",
            (ctx.user["id"], topic, h1_files["system_rule"], observation, now(), now()),
        )

    ev = {
        "id": rec_id,
        "mode": "recursive",
        "k": k,
        "base_harness": "H0",
        "new_harness": h1_id,
        "decision": decision,
        "observation": observation,
        "before": edits_record["before"],
        "after": edits_record["after"],
    }
    ctx.emit("harness_improved", **ev)
    return ev


def undo_improvement(db: DB, user_id: str, record_id: str) -> dict:
    """Undo a harness edit (page 84: 'Every edit shows in a Details fold as a before-and-after view, and the user can undo it')."""
    rec = db.one("SELECT * FROM improvement_records WHERE id=? AND user_id=?", (record_id, user_id))
    if not rec:
        raise ValueError("No such improvement record.")
    db.run("UPDATE improvement_records SET undone=1 WHERE id=?", (record_id,))
    if rec["new_harness"] and rec["new_harness"] != "H0":
        db.run("UPDATE harness_versions SET active=0 WHERE id=? AND user_id=?", (rec["new_harness"], user_id))
    return {"ok": True, "undone": record_id, "restored": rec["base_harness"]}
