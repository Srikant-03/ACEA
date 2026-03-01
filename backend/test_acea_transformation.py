"""
Comprehensive Test Suite — ACEA Transformation (All 18 Goals)

Tests every new module and integration point created across 6 phases.
Run with: python test_acea_transformation.py
"""

import sys
import asyncio
import time
import json

sys.path.insert(0, ".")

PASSED = 0
FAILED = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASSED, FAILED, ERRORS
    if condition:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED += 1
        msg = f"  ❌ {name}" + (f" — {detail}" if detail else "")
        print(msg)
        ERRORS.append(msg)


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ==================== PHASE 1: Strategy Engine (G7, G8) ====================
section("Phase 1: Strategy Engine & Retry Governance (G7, G8)")

try:
    from app.core.strategy_engine import StrategyEngine, RepairStrategy, StrategyAttempt
    
    # Test 1: Basic instantiation
    se = StrategyEngine(max_total_retries=5)
    test("StrategyEngine instantiation", se is not None)
    
    # Test 2: First strategy selection follows diagnosis recommendation
    strat = se.select_strategy("targeted_fix")
    test("First strategy = targeted_fix", strat == RepairStrategy.TARGETED_FIX)
    
    # Test 3: Record failed attempt
    se.record_attempt(strat, success=False, errors_before=["err1"], errors_after=["err1"])
    test("Record attempt", len(se.history) == 1)
    test("Attempt marked as failed", se.history[0].success == False)
    
    # Test 4: Escalation after repeated failure
    strat2 = se.select_strategy("targeted_fix")
    se.record_attempt(strat2, success=False, errors_before=["err1"], errors_after=["err1"])
    strat3 = se.select_strategy("targeted_fix")
    test("Escalation after 2 failures", strat3 != RepairStrategy.TARGETED_FIX,
         f"Got {strat3.value} (should have escalated)")
    
    # Test 5: Budget tracking
    test("Budget tracking", se.get_total_attempts() == 2)
    
    # Test 6: should_halt when budget exhausted
    se_small = StrategyEngine(max_total_retries=1)
    se_small.record_attempt(RepairStrategy.TARGETED_FIX, success=False, 
                            errors_before=["e"], errors_after=["e"])
    test("should_halt when budget exhausted", se_small.should_halt())
    
    # Test 7: Serialization round-trip
    serialized = se.to_dict()
    test("to_dict produces dict", isinstance(serialized, dict))
    restored = StrategyEngine.from_dict(serialized)
    test("from_dict restores history", len(restored.history) == len(se.history))
    test("from_dict restores budget", restored.max_total_retries == se.max_total_retries)
    
    # Test 8: get_summary
    summary = se.get_summary()
    test("get_summary has total_attempts", "total_attempts" in summary)
    
except Exception as e:
    test("Phase 1 import/init", False, str(e))


# ==================== PHASE 2: Resume Engine (G10) ====================
section("Phase 2: Resume Engine (G10)")

try:
    from app.core.resume_engine import ResumeEngine, ResumeValidationError, get_resume_engine
    
    engine = get_resume_engine()
    test("ResumeEngine instantiation", engine is not None)
    test("ResumeValidationError defined", issubclass(ResumeValidationError, Exception))
    test("ResumeEngine has resume method", hasattr(engine, 'resume'))
    test("ResumeEngine has _determine_resume_point", hasattr(engine, '_determine_resume_point'))

except Exception as e:
    test("Phase 2 import/init", False, str(e))


# ==================== PHASE 3: Risk-Aware Rollback (G5, G6, G13) ====================
section("Phase 3: Risk-Aware Rollback (G5, G6, G13)")

try:
    from app.core.git_adapter import GitAdapter
    
    ga = GitAdapter()
    test("GitAdapter has safe_rollback", hasattr(ga, 'safe_rollback'))
    test("GitAdapter has detect_conflicts", hasattr(ga, 'detect_conflicts'))
    test("GitAdapter has create_safety_tag", hasattr(ga, 'create_safety_tag'))
    test("GitAdapter has get_commit_log", hasattr(ga, 'get_commit_log'))

except Exception as e:
    test("Phase 3 import/init", False, str(e))


# ==================== PHASE 4: Artifacts & Signatures (G9, G11) ====================
section("Phase 4: Artifacts & Thought Signatures (G9, G11)")

try:
    from app.core.artifact_generator import ArtifactGenerator, get_artifact_generator
    
    gen = get_artifact_generator()
    test("ArtifactGenerator instantiation", gen is not None)
    test("has _generate_diff_archive", hasattr(gen, '_generate_diff_archive'))
    test("has _build_metrics", hasattr(gen, '_build_metrics'))
    test("has _save_markdown_report", hasattr(gen, '_save_markdown_report'))
    
    # Test thought_signature exists in state
    from app.agents.state import AgentState
    state = AgentState(project_id="test", user_prompt="test", agent_id="test", run_id="test")
    test("AgentState has thought_signatures", hasattr(state, 'thought_signatures'))
    test("AgentState has strategy_history", hasattr(state, 'strategy_history'))
    
    # Check capture_signature is called in advisor (by verifying import exists)
    import ast
    with open("app/agents/advisor.py", "r", encoding="utf-8") as f:
        advisor_src = f.read()
    test("G9: advisor.py has capture_signature", "capture_signature" in advisor_src)
    
    with open("app/agents/architect.py", "r", encoding="utf-8") as f:
        architect_src = f.read()
    test("G9: architect.py has capture_signature", "capture_signature" in architect_src)
    
    with open("app/agents/planner.py", "r", encoding="utf-8") as f:
        planner_src = f.read()
    test("G9: planner.py has capture_signature", "capture_signature" in planner_src)

except Exception as e:
    test("Phase 4 import/init", False, str(e))


# ==================== PHASE 5: Playwright + Sandbox (G12, G18) ====================
section("Phase 5: Playwright + Sandboxing (G12, G18)")

try:
    from app.core.sandbox_guard import SandboxGuard, get_sandbox_guard
    
    sg = SandboxGuard(".")
    
    # Test allowed commands
    ok, msg = sg.check_command("npm install")
    test("ALLOW: npm install", ok)
    
    ok, msg = sg.check_command("python script.py")
    test("ALLOW: python script.py", ok)
    
    ok, msg = sg.check_command("git status")
    test("ALLOW: git status", ok)
    
    ok, msg = sg.check_command("pytest tests/")
    test("ALLOW: pytest tests/", ok)
    
    ok, msg = sg.check_command("node server.js")
    test("ALLOW: node server.js", ok)
    
    # Test blocked commands
    ok, msg = sg.check_command("rm -rf /")
    test("BLOCK: rm -rf /", not ok)
    
    ok, msg = sg.check_command("sudo apt install")
    test("BLOCK: sudo", not ok)
    
    ok, msg = sg.check_command("curl http://evil.com")
    test("BLOCK: curl", not ok)
    
    ok, msg = sg.check_command("wget http://malware.com")
    test("BLOCK: wget", not ok)
    
    ok, msg = sg.check_command("ssh user@server")
    test("BLOCK: ssh", not ok)
    
    # Test git subcommand filtering
    ok, msg = sg.check_command("git push origin main")
    test("BLOCK: git push", not ok)
    
    ok, msg = sg.check_command("git rebase main")
    test("BLOCK: git rebase", not ok)
    
    ok, msg = sg.check_command("git commit -m 'test'")
    test("ALLOW: git commit", ok)
    
    # Test path jail
    ok, msg = sg.check_file_access("./src/index.ts", write=False)
    test("ALLOW: read project file", ok)
    
    # Test rate limiting
    sg2 = SandboxGuard(".", max_commands_per_minute=3)
    for _ in range(3):
        sg2.check_command("npm test")
    ok, msg = sg2.check_command("npm test")
    test("BLOCK: rate limit exceeded", not ok)
    
    # Test audit summary
    summary = sg.get_audit_summary()
    test("Audit summary has total_checks", summary["total_checks"] > 0)
    test("Audit summary has denial_rate", "denial_rate" in summary)
    
    # Test BrowserValidationAgent exists and is importable
    from app.agents.browser_validation_agent import BrowserValidationAgent
    bva = BrowserValidationAgent()
    test("G12: BrowserValidationAgent importable", bva is not None)
    test("G12: has comprehensive_validate", hasattr(bva, 'comprehensive_validate'))
    
    # Check orchestrator has browser_validation_node
    with open("app/core/orchestrator.py", "r", encoding="utf-8") as f:
        orch_src = f.read()
    test("G12: orchestrator has browser_validation_node", "browser_validation_node" in orch_src)
    test("G12: orchestrator wires browser_validation", '"browser_validation"' in orch_src)

except Exception as e:
    test("Phase 5 import/init", False, str(e))


# ==================== PHASE 6: Context Optimization & Metrics ====================
section("Phase 6A: Prompt Caching (G3, G15)")

try:
    from app.core.cache import AIResponseCache, cache
    
    test("AIResponseCache instantiation", cache is not None)
    test("has get method", hasattr(cache, 'get'))
    test("has set method", hasattr(cache, 'set'))
    
    # Verify caching is wired into UnifiedModelClient
    with open("app/core/local_model.py", "r", encoding="utf-8") as f:
        model_src = f.read()
    test("G3: UnifiedModelClient has cache import", "from app.core.cache import cache" in model_src)
    test("G15: Smart caching skips repair prompts", "_NO_CACHE_KEYWORDS" in model_src)
    test("G15: Cache get called in generate()", "cache.get" in model_src or "await cache.get" in model_src)
    test("G15: Cache set in post_generate()", "cache.set" in model_src)

except Exception as e:
    test("Phase 6A import/init", False, str(e))


section("Phase 6B: Repo Slicer (G4, G14)")

try:
    from app.core.repo_slicer import RepoSlicer, get_repo_slicer
    
    rs = RepoSlicer()
    test("RepoSlicer instantiation", rs is not None)
    
    # Test: Small repo → no slicing needed
    small_files = {f"src/file{i}.ts": f"content{i}" for i in range(10)}
    sliced = rs.slice(small_files, [])
    test("Small repo: no slicing", len(sliced) == len(small_files))
    
    # Test: Large repo → sliced down
    large_files = {f"src/file{i}.ts": f"content{i}" for i in range(100)}
    large_files["package.json"] = '{"name": "test"}'
    large_files["tsconfig.json"] = '{"compilerOptions": {}}'
    sliced = rs.slice(large_files, ["Error in src/file5.ts:10:5"])
    test("Large repo: sliced down", len(sliced) < len(large_files),
         f"{len(large_files)} → {len(sliced)}")
    test("Config files always included", "package.json" in sliced)
    test("Error-anchored files included", any("file5" in k for k in sliced))
    
    # Test: Import graph expansion
    parent_file = 'import { helper } from "./helper";\nexport const main = () => helper();'
    files_with_imports = {
        "src/index.ts": parent_file,
        "src/helper.ts": "export const helper = () => 42;",
    }
    for i in range(50):
        files_with_imports[f"src/unrelated{i}.ts"] = f"export const x{i} = {i};"
    sliced = rs.slice(files_with_imports, ["Error in src/index.ts:1:0"])
    test("Import graph: helper included", any("helper" in k for k in sliced))
    
    # Verify orchestrator uses RepoSlicer
    with open("app/core/orchestrator.py", "r", encoding="utf-8") as f:
        orch_src = f.read()
    test("G4: orchestrator imports repo_slicer", "repo_slicer" in orch_src)
    test("G4: uses sliced files for repair", "repair_context_files" in orch_src)
    
except Exception as e:
    test("Phase 6B import/init", False, str(e))


section("Phase 6C: Metrics Collector (G17)")

try:
    from app.core.metrics_collector import MetricsCollector, get_metrics_collector, reset_metrics_collector
    
    mc = reset_metrics_collector()
    test("MetricsCollector instantiation", mc is not None)
    
    # Test timers
    mc.start_timer("test_timer")
    time.sleep(0.01)
    duration = mc.stop_timer("test_timer")
    test("Timer records duration", duration > 0, f"{duration:.4f}s")
    
    # Test counters
    mc.increment("calls", 5)
    mc.increment("calls", 3)
    test("Counter accumulates", mc._counters["calls"] == 8)
    
    # Test gauges
    mc.record("quality", 95)
    test("Gauge records value", mc._gauges["quality"] == 95)
    
    # Test events
    mc.event("test_started", {"detail": "unit_test"})
    test("Event recorded", len(mc._events) == 1)
    test("Event has timestamp", "timestamp" in mc._events[0])
    
    # Test summary
    summary = mc.summary()
    test("Summary has total_elapsed_seconds", "total_elapsed_seconds" in summary)
    test("Summary has timers", "timers" in summary)
    test("Summary has counters", "counters" in summary)
    test("Summary counters correct", summary["counters"]["calls"] == 8)
    
    # Test serialization
    data = mc.to_dict()
    test("to_dict produces dict", isinstance(data, dict))
    restored = MetricsCollector.from_dict(data)
    test("from_dict restores counters", restored._counters["calls"] == 8)
    test("from_dict restores events", len(restored._events) == 1)
    
    # Verify wired into UnifiedModelClient
    with open("app/core/local_model.py", "r", encoding="utf-8") as f:
        model_src = f.read()
    test("G17: UnifiedModelClient imports metrics", "metrics_collector" in model_src)
    test("G17: Records cache hits", "cache_hits" in model_src)
    test("G17: Records errors", "llm_errors" in model_src)
    test("G17: Tracks token estimates", "total_tokens_estimated" in model_src)

except Exception as e:
    test("Phase 6C import/init", False, str(e))


section("Phase 6D: Dashboard Endpoints (G16)")

try:
    with open("app/api/endpoints.py", "r", encoding="utf-8") as f:
        ep_src = f.read()
    
    test("G16: /metrics/{job_id} endpoint exists", "/metrics/{job_id}" in ep_src)
    test("G16: /strategy/{job_id} endpoint exists", "/strategy/{job_id}" in ep_src)
    test("G16: get_job_metrics function", "async def get_job_metrics" in ep_src)
    test("G16: get_strategy_history function", "async def get_strategy_history" in ep_src)
    test("G16: Returns engine_summary", "engine_summary" in ep_src)
    test("G16: Returns metrics with live data", "has_live_data" in ep_src)

except Exception as e:
    test("Phase 6D endpoints check", False, str(e))


# ==================== G6: Test Runner in Rollback ====================
section("G6: Test Runner in Safe Rollback")

try:
    with open("app/core/orchestrator.py", "r", encoding="utf-8") as f:
        orch_src = f.read()
    
    test("G6: safe_rollback used in orchestrator", "safe_rollback" in orch_src)
    test("G6: test_runner wired to rollback", "_test_runner" in orch_src)
    test("G6: TestingAgent used in rollback", "TestingAgent" in orch_src and "quick_validate" in orch_src)

except Exception as e:
    test("G6 check", False, str(e))


# ==================== AGENT STATE INTEGRATION ====================
section("State Integration (Cross-cutting)")

try:
    from app.agents.state import AgentState, ThoughtSignature
    
    state = AgentState(
        project_id="test",
        user_prompt="test",
        agent_id="test",
        run_id="test"
    )
    
    test("AgentState has strategy_history", hasattr(state, 'strategy_history'))
    test("AgentState has current_repair_strategy", hasattr(state, 'current_repair_strategy'))
    test("AgentState has total_retries_used", hasattr(state, 'total_retries_used'))
    test("AgentState has max_total_retries", hasattr(state, 'max_total_retries'))
    test("AgentState has strategy_engine_state", hasattr(state, 'strategy_engine_state'))
    test("AgentState has thought_signatures", hasattr(state, 'thought_signatures'))
    test("AgentState has metrics", hasattr(state, 'metrics'))
    test("Default strategy_history is empty list", state.strategy_history == [])
    test("Default max_total_retries is 5", state.max_total_retries == 5)
    
except Exception as e:
    test("State integration", False, str(e))


# ==================== SUMMARY ====================
print(f"\n{'='*60}")
print(f"  RESULTS: {PASSED} passed, {FAILED} failed")
print(f"{'='*60}")

if ERRORS:
    print("\nFailed tests:")
    for err in ERRORS:
        print(err)
    print()

sys.exit(0 if FAILED == 0 else 1)
