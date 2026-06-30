"""
main.py — full autonomous orchestration cycle.

Run this file directly for a single cycle:
    python main.py

The scheduler (scheduler.py) calls this on a repeating schedule.
"""
import sys
import traceback
import state
from brain.brain import run as brain_run
from utils import get_logger, now_epoch
from skills.discord_notify import notify

log = get_logger("orchestrator")


def run_cycle() -> dict:
    log.info("═══════════════ CYCLE START ═══════════════")

    # ── 1. Brain — Pre-cycle ──────────────────────────────────────────────────
    log.info("Step 1: Brain pre-cycle")
    try:
        brain_pre = brain_run(mode="pre")
    except Exception as e:
        msg = f"Brain pre-cycle crashed: {e}"
        log.error(msg)
        notify(f"🧠❌ {msg}")
        return {"status": "error", "step": "brain_pre", "message": msg}

    if brain_pre.get("status") == "error":
        notify(f"🧠❌ Brain failed: {brain_pre.get('message', '')}")
        return brain_pre

    strategy_version = brain_pre.get("strategy_version", 0)
    brain_notes      = brain_pre.get("brain_notes", "")
    src_summary      = brain_pre.get("source_summary", {})
    sm_snapshot      = brain_pre.get("self_model_snapshot", {})

    if brain_pre.get("status") == "fallback":
        notify("🧠⚠️ Gemini call failed — using previous strategy. Continuing.")
    else:
        msg = (
            f"🧠 Brain v{strategy_version} ready.\n"
            f"📊 {sm_snapshot.get('total_cycles', 0)} cycles · "
            f"trend {sm_snapshot.get('engagement_trend', '?')} · "
            f"audit {sm_snapshot.get('audit_score', 0):.2f}\n"
            f"💡 {brain_notes}"
        )
        if brain_pre.get("source_discovery_triggered"):
            msg += (
                f"\n🔍 Source discovery ran: "
                f"+{src_summary.get('discovered', 0)} added, "
                f"{src_summary.get('pruned', 0)} pruned."
            )
        notify(msg)

    # ── 2. Research & Draft ───────────────────────────────────────────────────
    log.info("Step 2: Research & Draft")
    try:
        from skills.research_draft import run as research_run
        draft = research_run()
    except Exception as e:
        msg = f"Research crashed: {e}"
        log.error(msg)
        notify(f"🔎❌ {msg}")
        return {"status": "error", "step": "research", "message": msg}

    if draft.get("status") != "ok":
        notify(f"🔎❌ Research failed: {draft.get('message', '')}")
        return draft

    draft_path = draft["draft_path"]
    topic      = draft["topic"]
    notify(f'🔎 Research complete: "{topic}" → {draft_path}')

    # ── 3. Post ───────────────────────────────────────────────────────────────
    log.info("Step 3: Stealth Post")
    try:
        from skills.stealth_post import run as post_run
        post_result = post_run(draft_path)
    except Exception as e:
        msg = f"Post crashed: {e}\n{traceback.format_exc()}"
        log.error(msg)
        notify(f"❌ Post crashed: {e}")
        return {"status": "error", "step": "post", "message": str(e)}

    if post_result.get("status") != "ok":
        notify(f"❌ Post failed: {post_result.get('message', '')}")
        return post_result

    notify(f"✅ Posted (ID: {post_result.get('post_id', '?')})")

    # ── 4. Feed Engagement ────────────────────────────────────────────────────
    log.info("Step 4: Feed Engagement")
    try:
        from skills.feed_engager import run as engage_run
        engage_result = engage_run()
    except Exception as e:
        log.error("Engagement crashed: %s", e)
        engage_result = {"status": "error", "comments": 0, "likes": 0,
                         "story_views": 0, "engagement": 0}

    notify(
        f"📈 Engagement: {engage_result.get('comments', 0)} comments · "
        f"{engage_result.get('likes', 0)} likes · "
        f"{engage_result.get('story_views', 0)} story views"
    )

    # ── 5. Follow / Unfollow ──────────────────────────────────────────────────
    log.info("Step 5: Follow Manager")
    try:
        from skills.follow_manager import run as follow_run
        follow_result = follow_run()
    except Exception as e:
        log.error("Follow manager crashed: %s", e)
        follow_result = {"status": "error", "followed": 0, "unfollowed": 0}

    notify(
        f"👥 Follows: +{follow_result.get('followed', 0)} new · "
        f"-{follow_result.get('unfollowed', 0)} unfollowed · "
        f"follow-back {follow_result.get('follow_back_rate', 0):.1%}"
    )

    # ── 6. Log Performance ────────────────────────────────────────────────────
    log.info("Step 6: Log Performance")
    try:
        from skills.log_performance import run as log_run
        log_run(draft_path=draft_path,
                post_result=post_result,
                engage_result=engage_result,
                follow_result=follow_result,
                strategy_version=strategy_version)
    except Exception as e:
        log.error("Log performance crashed: %s", e)

    # ── 7. Brain — Post-cycle ─────────────────────────────────────────────────
    log.info("Step 7: Brain post-cycle")
    try:
        brain_post = brain_run(
            mode="post",
            post_result=post_result,
            engage_result=engage_result,
            follow_result=follow_result,
            draft_path=draft_path,
            strategy_version=strategy_version,
        )
    except Exception as e:
        log.error("Brain post-cycle crashed: %s", e)
        brain_post = {}

    insight        = brain_post.get("insight", "")
    new_confidence = brain_post.get("new_confidence", 0)
    sm             = brain_post.get("self_model", {})

    if insight:
        notify(
            f"🧠 Post-cycle insight: {insight}\n"
            f"📊 Confidence: {new_confidence:.2f} · "
            f"Hour acc: {sm.get('hour_prediction_accuracy', 0):.1%} · "
            f"Topic acc: {sm.get('topic_prediction_accuracy', 0):.1%}"
        )

    # ── 8. Deep Audit (if due) ────────────────────────────────────────────────
    if brain_post.get("deep_audit_triggered"):
        log.info("Step 8: Deep Audit triggered!")
        try:
            brain_run(mode="deep-audit")
        except Exception as e:
            log.error("Deep audit crashed: %s", e)
            notify(f"🧠📊❌ Deep audit crashed: {e}")

    # ── 9. Final notice ───────────────────────────────────────────────────────
    freq = state.get("brain_strategy", {}).get("posting", {}).get("frequency_hours", 8) or 8
    notify(f"🕒 Cycle {sm.get('total_cycles', '?')} complete. Next run in {freq} h.")

    log.info("═══════════════ CYCLE DONE ═══════════════")
    return {
        "status": "ok",
        "strategy_version": strategy_version,
        "brain_notes": brain_notes,
        "post_id": post_result.get("post_id"),
        "engage_result": engage_result,
        "follow_result": follow_result,
        "insight": insight,
        "new_confidence": new_confidence,
        "deep_audit_triggered": brain_post.get("deep_audit_triggered", False),
    }

if __name__ == "__main__":
    result = run_cycle()
    if result.get("status") != "ok":
        sys.exit(1)
