"""
Phase 5: Enhanced Self-Healing Tests
Tests for DiagnosticianAgent, strategy dispatch, and integration with orchestrator.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.diagnostician import (
    DiagnosticianAgent,
    DiagnosticReport,
    FailureCategory,
    RepairStrategy,
    get_diagnostician,
)


# ─── Unit Tests: Fallback Heuristics ───


def test_fallback_diagnosis_import_error():
    """Heuristic correctly categorizes import errors."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["ModuleNotFoundError: No module named 'fastapi'"]
    )
    assert report.category == FailureCategory.IMPORT_ERROR
    assert report.recommended_strategy == RepairStrategy.ADD_MISSING
    assert report.confidence == 0.4


def test_fallback_diagnosis_syntax_error():
    """Heuristic correctly categorizes syntax errors."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["SyntaxError: unexpected token '}' at line 42"]
    )
    assert report.category == FailureCategory.SYNTAX_ERROR
    assert report.recommended_strategy == RepairStrategy.TARGETED_FIX


def test_fallback_diagnosis_type_error():
    """Heuristic correctly categorizes type errors."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["TypeError: Cannot read properties of undefined"]
    )
    assert report.category == FailureCategory.TYPE_ERROR
    assert report.recommended_strategy == RepairStrategy.TARGETED_FIX


def test_fallback_diagnosis_config_error():
    """Heuristic correctly categorizes configuration errors."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["Error in package.json: invalid dependency version"]
    )
    assert report.category == FailureCategory.CONFIGURATION
    assert report.recommended_strategy == RepairStrategy.CONFIGURATION


def test_fallback_diagnosis_dependency_error():
    """Heuristic correctly categorizes dependency errors."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["npm ERR! peer dependency conflict"]
    )
    assert report.category == FailureCategory.DEPENDENCY
    assert report.recommended_strategy == RepairStrategy.ADD_MISSING


def test_fallback_diagnosis_network_error():
    """Heuristic correctly categorizes network errors."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["CORS policy blocked fetch to /api/data"]
    )
    assert report.category == FailureCategory.NETWORK
    assert report.recommended_strategy == RepairStrategy.TARGETED_FIX


def test_fallback_diagnosis_unknown():
    """Unknown errors get UNKNOWN category with TARGETED_FIX strategy."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis(
        ["Something went terribly wrong"]
    )
    assert report.category == FailureCategory.UNKNOWN
    assert report.recommended_strategy == RepairStrategy.TARGETED_FIX


def test_fallback_diagnosis_empty_errors():
    """Empty error list produces Unknown category."""
    diag = DiagnosticianAgent()
    report = diag._fallback_diagnosis([])
    assert report.category == FailureCategory.UNKNOWN


def test_diagnostic_report_to_dict():
    """DiagnosticReport.to_dict() serializes correctly."""
    report = DiagnosticReport(
        category=FailureCategory.IMPORT_ERROR,
        root_cause="Missing React import",
        affected_files=["src/App.tsx"],
        recommended_strategy=RepairStrategy.ADD_MISSING,
        fix_suggestions=["Add import React from 'react'"],
        confidence=0.9,
        reasoning="Error clearly states module not found"
    )
    d = report.to_dict()
    assert d["category"] == "import_error"
    assert d["recommended_strategy"] == "add_missing"
    assert d["affected_files"] == ["src/App.tsx"]
    assert d["confidence"] == 0.9


# ─── Unit Tests: AI Diagnosis ───


@pytest.mark.asyncio
async def test_diagnosis_with_ai():
    """Mock Gemini returns diagnosis JSON, verify parsing."""
    diag = DiagnosticianAgent()
    
    mock_response = json.dumps({
        "category": "import_error",
        "root_cause": "Missing 'react' package in node_modules",
        "affected_files": ["src/App.tsx"],
        "recommended_strategy": "add_missing",
        "fix_suggestions": ["Run npm install react", "Add import statement"],
        "confidence": 0.92,
        "reasoning": "Error message indicates missing module"
    })
    
    with patch("app.core.HybridModelClient.HybridModelClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.generate = AsyncMock(return_value=mock_response)
        
        report = await diag.diagnose(
            errors=["ModuleNotFoundError: No module named 'react'"]
        )
        
        assert report.category == FailureCategory.IMPORT_ERROR
        assert report.recommended_strategy == RepairStrategy.ADD_MISSING
        assert report.confidence == 0.92
        assert "src/App.tsx" in report.affected_files


@pytest.mark.asyncio
async def test_diagnosis_ai_failure_falls_back():
    """When AI fails, fallback heuristic is used."""
    diag = DiagnosticianAgent()
    
    with patch("app.core.HybridModelClient.HybridModelClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.generate = AsyncMock(side_effect=Exception("API down"))
        
        report = await diag.diagnose(
            errors=["SyntaxError: unexpected token at line 5"]
        )
        
        # Should use fallback, not crash
        assert report.category == FailureCategory.SYNTAX_ERROR
        assert report.confidence == 0.4
        assert "Fallback" in report.reasoning


# ─── Integration Tests: Strategy Dispatch ───


@pytest.mark.asyncio
async def test_smart_healing_targeted_fix():
    """Integration: diagnostician → targeted fix strategy in orchestrator."""
    from app.agents.virtuoso import VirtuosoAgent
    
    mock_diagnosis = DiagnosticReport(
        category=FailureCategory.SYNTAX_ERROR,
        root_cause="Missing semicolon",
        affected_files=["main.js"],
        recommended_strategy=RepairStrategy.TARGETED_FIX,
        fix_suggestions=["Add semicolon on line 10"],
        confidence=0.9,
        reasoning="Simple syntax fix"
    )
    
    with patch("app.agents.diagnostician.get_diagnostician") as mock_get:
        mock_diag = MagicMock()
        mock_diag.diagnose = AsyncMock(return_value=mock_diagnosis)
        mock_get.return_value = mock_diag
        
        with patch("app.core.socket_manager.SocketManager") as MockSM:
            MockSM.return_value.emit = AsyncMock()
            sm = MockSM()
            
            # Mock virtuoso_agent at module level in orchestrator
            with patch("app.core.orchestrator.virtuoso_agent") as mock_virtuoso:
                mock_virtuoso.repair_files_targeted = AsyncMock(
                    return_value={"main.js": "fixed code;"}
                )
                
                from app.core.orchestrator import _handle_self_healing
                
                result = await _handle_self_healing(
                    sm=sm,
                    errors=["SyntaxError: missing semicolon line 10"],
                    current_files={"main.js": "broken code"},
                    iteration=1,
                    visual_context=None,
                    state=None
                )
                
                mock_virtuoso.repair_files_targeted.assert_called_once()
                assert "main.js" in result


@pytest.mark.asyncio
async def test_smart_healing_add_missing():
    """Integration: diagnostician → add_missing strategy."""
    mock_diagnosis = DiagnosticReport(
        category=FailureCategory.IMPORT_ERROR,
        root_cause="Missing express package",
        affected_files=["server.js"],
        recommended_strategy=RepairStrategy.ADD_MISSING,
        fix_suggestions=["Add express to package.json"],
        confidence=0.85,
        reasoning="Import error"
    )
    
    with patch("app.agents.diagnostician.get_diagnostician") as mock_get:
        mock_diag = MagicMock()
        mock_diag.diagnose = AsyncMock(return_value=mock_diagnosis)
        mock_get.return_value = mock_diag
        
        with patch("app.core.socket_manager.SocketManager") as MockSM:
            MockSM.return_value.emit = AsyncMock()
            sm = MockSM()
            
            with patch("app.core.orchestrator.virtuoso_agent") as mock_virtuoso:
                mock_virtuoso.add_missing_dependencies = AsyncMock(
                    return_value={
                        "server.js": "const express = require('express');",
                        "package.json": '{"dependencies":{"express":"^4.18.0"}}'
                    }
                )
                
                from app.core.orchestrator import _handle_self_healing
                
                result = await _handle_self_healing(
                    sm=sm,
                    errors=["Cannot find module 'express'"],
                    current_files={"server.js": "const express = require('express');"},
                    iteration=1,
                    visual_context=None,
                    state=None
                )
                
                mock_virtuoso.add_missing_dependencies.assert_called_once()
                assert "package.json" in result


@pytest.mark.asyncio
async def test_smart_healing_rollback():
    """Integration: rollback strategy returns unchanged files."""
    mock_diagnosis = DiagnosticReport(
        category=FailureCategory.UNKNOWN,
        root_cause="Everything is broken",
        affected_files=[],
        recommended_strategy=RepairStrategy.ROLLBACK,
        fix_suggestions=[],
        confidence=0.3,
        reasoning="Too broken to fix"
    )
    
    with patch("app.agents.diagnostician.get_diagnostician") as mock_get:
        mock_diag = MagicMock()
        mock_diag.diagnose = AsyncMock(return_value=mock_diagnosis)
        mock_get.return_value = mock_diag
        
        with patch("app.core.socket_manager.SocketManager") as MockSM:
            MockSM.return_value.emit = AsyncMock()
            sm = MockSM()
            
            with patch("app.core.orchestrator.virtuoso_agent"):
                from app.core.orchestrator import _handle_self_healing
                
                original_files = {"app.py": "original code"}
                result = await _handle_self_healing(
                    sm=sm,
                    errors=["Fatal crash"],
                    current_files=original_files,
                    iteration=3,
                    visual_context=None,
                    state=None
                )
                
                # Rollback returns original files unchanged
                assert result == original_files


# ─── Singleton Tests ───


def test_get_diagnostician_singleton():
    """get_diagnostician() returns same instance."""
    import app.agents.diagnostician as mod
    mod._diagnostician = None  # Reset
    
    d1 = get_diagnostician()
    d2 = get_diagnostician()
    assert d1 is d2
    
    mod._diagnostician = None  # Cleanup
