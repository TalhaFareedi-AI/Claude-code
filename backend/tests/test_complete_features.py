"""Tests for the completed Chatbot Harness & Platform Plan features (Sections 5, 6, 7, 9, 13, 16, 18)."""
from pathlib import Path
import httpx
import pytest

from app import plans, postprocess, prompts, recursive, skills, team, wallet
from app.main import create_app
from app.tools import docx_builder, pdf_builder, pptx_builder, science_plot
from test_harness import answer_text, go, last
from test_team import pro, reply_with_plan


async def test_understand_and_separate_prompt_enhancer_slot(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    # Distinct enhancer model triggers a second enhancer call
    _, events = await go(
        harness, user,
        message="Explain how a neural network learns",
        mode="deep", confirm=True, teacher_enabled=False,
        team={
            "plan_depth": "light",
            "understand": {"enabled": True, "model": "deepseek/deepseek-v4.1-flash"},
            "enhancer": {"enabled": True, "model": "qwen/qwen3.8-flash"},
        },
    )
    assert last(events, "run_done")["status"] == "done"
    agents = [e["agent"] for e in events if e["type"] == "agent_start"]
    assert "understand" in agents and "enhancer" in agents
    assert any(e["type"] == "prompt_enhanced" for e in events)


async def test_up_to_five_planners_supported_when_enabled(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    cfg = team.normalize_team({"allow_five_planners": True, "planners": {"count": 5, "allow_five": True}})
    assert cfg["planners"]["count"] == 5
    _, events = await go(
        harness, user,
        message="Plan a comprehensive 5-part study course",
        mode="deep", confirm=True, teacher_enabled=False,
        team={"allow_five_planners": True, "planners": {"count": 5, "allow_five": True}, "plan_depth": "light"},
    )
    assert last(events, "run_done")["status"] == "done"
    started = [e["agent"] for e in events if e["type"] == "agent_start" and e["agent"].startswith("planner")]
    assert len(started) == 5
    assert any(e["type"] == "agent_start" and e["agent"] == "plan_judge" for e in events)


async def test_architecture_agent_creates_interactive_d3_diagram_and_svg(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    _, events = await go(
        harness, user,
        message="Design a small CNN architecture for handwritten digits with a D3 diagram",
        mode="deep", confirm=True, teacher_enabled=False,
        team={"architecture_agent": "auto", "plan_depth": "light"},
    )
    assert last(events, "run_done")["status"] == "done"
    d3_arts = [e for e in events if e["type"] == "artifact" and e["kind"] == "d3_diagram"]
    assert len(d3_arts) >= 1
    spec = d3_arts[0]["data"]
    assert spec["title"] == "Small CNN for handwritten digits"
    assert len(spec["nodes"]) >= 5
    assert all("input" in n and "process" in n and "output" in n for n in spec["nodes"])
    assert spec["badge"] == "Interactive architecture diagram"
    assert any(e["type"] == "file_created" and e["file"]["name"].endswith(".svg") for e in events)


async def test_critic_subagents_run_in_parallel_and_emit_verdict_cards(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    _, events = await go(
        harness, user,
        message="Calculate compound interest and check assumptions",
        mode="deep", confirm=True, teacher_enabled=False,
        team={
            "plan_depth": "light",
            "critics": {"mode": "always", "roles": ["devil", "math", "edge_cases"], "max_per_step": 3},
        },
    )
    assert last(events, "run_done")["status"] == "done"
    reports = [e for e in events if e["type"] == "critic_report"]
    assert len(reports) >= 3
    assert {r["role"] for r in reports} == {"devil", "math", "edge_cases"}
    assert all(r["verdict"] in ("pass", "problem", "note") for r in reports)


async def test_recursive_harness_learned_and_inner_loop_and_undo(harness, db, fake, monkeypatch):
    user = pro(harness, db)
    reply_with_plan(fake, monkeypatch)
    # 1. Learned mode applies matching lessons from EXPERIENCE.md
    _, ev_learned = await go(
        harness, user,
        message="Write a report on solar panel efficiency measurements",
        mode="deep", confirm=True, teacher_enabled=False,
        team={"plan_depth": "light", "self_improve": {"mode": "learned", "k": 1}},
    )
    assert last(ev_learned, "run_done")["status"] == "done"
    imp_learned = [e for e in ev_learned if e["type"] == "harness_improved"]
    assert len(imp_learned) == 1 and imp_learned[0]["mode"] == "learned"

    # 2. Recursive mode runs Propose (general + topic editors) -> Probe -> Compose -> H1
    _, ev_rec = await go(
        harness, user,
        message="Write a technical report on battery storage",
        mode="deep", confirm=True, teacher_enabled=False,
        team={"plan_depth": "light", "self_improve": {"mode": "recursive", "k": 1}},
    )
    assert last(ev_rec, "run_done")["status"] == "done"
    imp_rec = [e for e in ev_rec if e["type"] == "harness_improved" and e["mode"] == "recursive"]
    assert len(imp_rec) == 1
    rec_id = imp_rec[0]["id"]
    h1_id = imp_rec[0]["new_harness"]
    assert h1_id.startswith("H1_")
    assert db.one("SELECT * FROM harness_versions WHERE id=?", (h1_id,))["active"] == 1

    # 3. Undo reverts H1 back to H0
    undone = recursive.undo_improvement(db, user, rec_id)
    assert undone["ok"] is True and undone["restored"] == "H0"
    assert db.one("SELECT * FROM harness_versions WHERE id=?", (h1_id,))["active"] == 0
    assert db.one("SELECT * FROM improvement_records WHERE id=?", (rec_id,))["undone"] == 1


async def test_scientific_plotter_generates_waveform_and_fft_spectrum_with_badge(harness, db, fake):
    user = pro(harness, db)
    _, events = await go(
        harness, user,
        message="Plot a 5 Hz sine waveform and its FFT frequency spectrum",
        mode="normal", teacher_enabled=False,
    )
    assert last(events, "run_done")["status"] == "done"
    plots = [e for e in events if e["type"] == "artifact" and e["kind"] == "science_plot"]
    assert len(plots) == 1
    pdata = plots[0]["data"]
    assert pdata["badge"] == "Computed plot"
    assert pdata["freq"] == 5.0
    assert len(pdata["xs"]) > 100 and len(pdata["fft_freqs"]) > 5
    assert "<svg" in pdata["svg"] and "FFT Frequency Spectrum" in pdata["svg"]


def test_professional_docx_templates_pptx_themes_and_pdf_export(tmp_path):
    doc_data = {
        "title": "Solar Cell Efficiency Study",
        "template": "research_paper",
        "abstract": "This paper analyzes silicon and perovskite solar cells.",
        "sections": [
            {"heading": "Introduction", "paragraphs": ["Solar efficiency has risen steadily."], "bullets": ["Silicon: 26%", "Tandem: 33%"]},
            {"heading": "Measurements", "paragraphs": ["Measured across 10 panels."], "bullets": ["Low degradation"]},
        ],
        "references": ["1. NREL Solar Efficiency Chart (2026)."],
    }
    docx_out = docx_builder.build(doc_data, tmp_path / "paper.docx", template="research_paper")
    assert docx_out.exists() and docx_out.stat().st_size > 1000

    pdf_out = pdf_builder.build_from_doc(doc_data, tmp_path / "paper.pdf")
    assert pdf_out.exists() and pdf_out.read_bytes().startswith(b"%PDF-1.4")

    deck_data = {
        "title": "Solar Deck",
        "theme": "academic",
        "slides": [
            {"title": "Overview", "bullets": ["Sunlight to electricity", "High efficiency"], "notes": "Intro slide"},
            {"title": "Key Numbers", "bullets": ["26% silicon ceiling", "33% perovskite tandem"], "notes": "Numbers"},
        ],
    }
    for theme in ("academic", "business", "minimal"):
        pptx_out = pptx_builder.build(deck_data, tmp_path / f"deck-{theme}.pptx", theme=theme)
        assert pptx_out.exists() and pptx_out.stat().st_size > 5000


def test_all_12_developer_skills_style_md_and_latex_check():
    sk = skills.all_skills()
    expected_12 = {
        "architect", "researcher", "prompt-smith", "coder", "reviewer", "explainer",
        "chart-maker", "d3-diagram-maker", "scientific-plotter", "docx-writer",
        "pptx-designer", "document-reviewer",
    }
    assert expected_12 <= set(sk.keys())
    assert skills.match_keywords("draw an interactive architecture diagram") == "d3-diagram-maker"
    assert skills.match_keywords("plot a 5 Hz sine wave and fft spectrum") == "scientific-plotter"
    assert "teach_level" in prompts.get("style")
    assert postprocess.check_latex("Formula: $$ x(t) = \\sin(2\\pi f t)").endswith("$$")
    assert postprocess.check_latex("Inline \\( a + b").endswith("\\)")


async def test_pdf_export_api_and_lessons_api(db, fake):
    app = create_app(llm=None, db=db)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        h = {"x-user-id": "u_pdf_test"}
        r_les = await client.get("/api/lessons", headers=h)
        assert r_les.status_code == 200 and len(r_les.json()["lessons"]) >= 4
        up = await client.put("/api/upload", params={"name": "study-notes.md"}, content=b"# Study Notes\n\n- Point one\n- Point two", headers=h)
        assert up.status_code == 200
        fid = up.json()["id"]
        pdf_res = await client.post(f"/api/files/{fid}/pdf", headers=h)
        assert pdf_res.status_code == 200
        assert pdf_res.json()["file"]["kind"] == "pdf"
        dl = await client.get(pdf_res.json()["url"], headers=h)
        assert dl.status_code == 200 and dl.content.startswith(b"%PDF-1.4")
