# Integration tests for Browser Validation Agent
# Tests Playwright-based UI validation: interactivity, accessibility, performance, SEO

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


class TestBrowserValidationAgent:
    """Test suite for BrowserValidationAgent."""
    
    @pytest.fixture
    def browser_agent(self):
        """Create a BrowserValidationAgent instance for testing."""
        import sys
        import importlib.util
        
        # Mock dependencies
        with patch.dict('sys.modules', {
            'app.core.socket_manager': Mock(SocketManager=Mock(return_value=Mock(emit=AsyncMock())))
        }):
            spec = importlib.util.spec_from_file_location(
                "browser_validation_agent",
                "/mnt/user-data/uploads/browser_validation_agent.py"
            )
            agent_module = importlib.util.module_from_spec(spec)
            sys.modules['browser_validation_agent'] = agent_module
            spec.loader.exec_module(agent_module)
            
            return agent_module.BrowserValidationAgent()
    
    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page object."""
        page = AsyncMock()
        page.goto = AsyncMock()
        page.locator = Mock()
        page.screenshot = AsyncMock()
        return page
    
    @pytest.mark.asyncio
    async def test_comprehensive_validate_quick_level(self, browser_agent):
        """Test quick validation level runs basic tests only."""
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_p = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            
            mock_playwright.return_value.__aenter__.return_value = mock_p
            
            # Mock test methods
            browser_agent._test_interactivity = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_accessibility = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_responsiveness = AsyncMock(return_value={"status": "PASS", "issues": []})
            
            result = await browser_agent.comprehensive_validate(
                "http://localhost:3000",
                "/project",
                validation_level="quick"
            )
            
            assert result["validation_level"] == "quick"
            assert "interactive" in result["tests"]
            assert "accessibility" in result["tests"]
            assert "responsive" in result["tests"]
            # Quick level should NOT include these
            assert "performance" not in result["tests"]
            assert "seo" not in result["tests"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_validate_standard_level(self, browser_agent):
        """Test standard validation level includes more tests."""
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_p = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            
            mock_playwright.return_value.__aenter__.return_value = mock_p
            
            # Mock test methods
            browser_agent._test_interactivity = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_accessibility = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_responsiveness = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_performance = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_seo = AsyncMock(return_value={"status": "PASS", "issues": []})
            
            result = await browser_agent.comprehensive_validate(
                "http://localhost:3000",
                "/project",
                validation_level="standard"
            )
            
            assert result["validation_level"] == "standard"
            assert "interactive" in result["tests"]
            assert "performance" in result["tests"]
            assert "seo" in result["tests"]
            # Standard should NOT include thorough-only tests
            assert "links" not in result["tests"]
            assert "forms" not in result["tests"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_validate_thorough_level(self, browser_agent):
        """Test thorough validation level includes all tests."""
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_p = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            
            mock_playwright.return_value.__aenter__.return_value = mock_p
            
            # Mock all test methods
            browser_agent._test_interactivity = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_accessibility = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_responsiveness = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_performance = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_seo = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_links = AsyncMock(return_value={"status": "PASS", "issues": []})
            browser_agent._test_forms = AsyncMock(return_value={"status": "PASS", "issues": []})
            
            result = await browser_agent.comprehensive_validate(
                "http://localhost:3000",
                "/project",
                validation_level="thorough"
            )
            
            assert result["validation_level"] == "thorough"
            assert "links" in result["tests"]
            assert "forms" in result["tests"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_validate_handles_playwright_missing(self, browser_agent):
        """Test graceful handling when Playwright is not installed."""
        with patch('playwright.async_api.async_playwright', side_effect=ImportError("playwright not found")):
            result = await browser_agent.comprehensive_validate(
                "http://localhost:3000",
                "/project"
            )
            
            assert result["overall_status"] == "SKIPPED"
            assert "error" in result
            assert "Playwright" in result["error"]
    
    @pytest.mark.asyncio
    async def test_test_interactivity_counts_elements(self, browser_agent):
        """Test that interactivity test counts interactive elements."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        # Mock element counts
        mock_locator_button = Mock()
        mock_locator_button.count = AsyncMock(return_value=5)
        
        mock_locator_link = Mock()
        mock_locator_link.count = AsyncMock(return_value=10)
        
        mock_locator_input = Mock()
        mock_locator_input.count = AsyncMock(return_value=3)
        
        def locator_side_effect(selector):
            if selector == "button":
                return mock_locator_button
            elif selector == "a":
                return mock_locator_link
            elif selector == "input, textarea, select":
                return mock_locator_input
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_interactivity(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["interactive_elements"]["buttons"] == 5
        assert result["interactive_elements"]["links"] == 10
        assert result["interactive_elements"]["inputs"] == 3
    
    @pytest.mark.asyncio
    async def test_test_interactivity_detects_disabled_buttons(self, browser_agent):
        """Test that interactivity test detects disabled buttons."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        # Mock 2 buttons: one visible+enabled, one disabled
        mock_button1 = AsyncMock()
        mock_button1.is_visible = AsyncMock(return_value=True)
        mock_button1.is_enabled = AsyncMock(return_value=True)
        mock_button1.click = AsyncMock()
        
        mock_button2 = AsyncMock()
        mock_button2.is_visible = AsyncMock(return_value=True)
        mock_button2.is_enabled = AsyncMock(return_value=False)
        
        mock_button_locator = Mock()
        mock_button_locator.count = AsyncMock(return_value=2)
        mock_button_locator.nth = Mock(side_effect=[mock_button1, mock_button2])
        
        def locator_side_effect(selector):
            if selector == "button":
                return mock_button_locator
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_interactivity(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["status"] == "WARN"
        assert any("disabled" in issue.lower() for issue in result["issues"])
    
    @pytest.mark.asyncio
    async def test_test_interactivity_tests_input_fields(self, browser_agent):
        """Test that interactivity test validates input fields."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        mock_input = AsyncMock()
        mock_input.fill = AsyncMock()
        mock_input.input_value = AsyncMock(return_value="test")
        
        mock_input_locator = Mock()
        mock_input_locator.first = mock_input
        
        def locator_side_effect(selector):
            if selector == "button":
                return Mock(count=AsyncMock(return_value=0))
            elif selector == "a":
                return Mock(count=AsyncMock(return_value=0))
            elif selector == "input, textarea, select":
                return Mock(count=AsyncMock(return_value=1))
            elif selector == "input, textarea":
                return mock_input_locator
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_interactivity(mock_page, "http://localhost:3000", mock_sm)
        
        mock_input.fill.assert_called_once_with("test", timeout=2000)
        mock_input.input_value.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_test_accessibility_checks_alt_text(self, browser_agent):
        """Test that accessibility test checks for missing alt text."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        # 3 images, 1 without alt
        mock_img_locator = Mock()
        mock_img_locator.count = AsyncMock(return_value=3)
        
        mock_img_no_alt = Mock()
        mock_img_no_alt.count = AsyncMock(return_value=1)
        
        def locator_side_effect(selector):
            if selector == "img":
                return mock_img_locator
            elif selector == "img:not([alt])":
                return mock_img_no_alt
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_accessibility(mock_page, "http://localhost:3000", mock_sm)
        
        assert any("alt" in issue.lower() for issue in result["issues"])
        assert result["wcag_checks"]["images"]["missing_alt"] == 1
    
    @pytest.mark.asyncio
    async def test_test_accessibility_checks_aria_labels(self, browser_agent):
        """Test that accessibility test validates ARIA labels."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        # Mock ARIA checks
        def locator_side_effect(selector):
            if selector == "img":
                return Mock(count=AsyncMock(return_value=0))
            elif selector == "img:not([alt])":
                return Mock(count=AsyncMock(return_value=0))
            elif selector == "button, a, [role='button']":
                return Mock(count=AsyncMock(return_value=5))
            elif selector == "button:not([aria-label]):not([aria-labelledby]), a:not([aria-label]):not([aria-labelledby]), [role='button']:not([aria-label]):not([aria-labelledby])":
                return Mock(count=AsyncMock(return_value=2))
            elif selector == "[role]":
                return Mock(count=AsyncMock(return_value=3))
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_accessibility(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["wcag_checks"]["interactive_elements"]["missing_labels"] == 2
    
    @pytest.mark.asyncio
    async def test_test_performance_measures_page_load(self, browser_agent):
        """Test that performance test measures page load time."""
        mock_page = AsyncMock()
        
        # Mock performance metrics
        mock_page.evaluate = AsyncMock(return_value={
            "loadTime": 1200,
            "domContentLoaded": 800,
            "firstPaint": 600
        })
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_performance(mock_page, "http://localhost:3000", mock_sm)
        
        assert "load_time_ms" in result["metrics"]
        assert result["metrics"]["load_time_ms"] == 1200
    
    @pytest.mark.asyncio
    async def test_test_responsiveness_checks_mobile_viewport(self, browser_agent):
        """Test that responsiveness test validates mobile viewport."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.screenshot = AsyncMock()
        
        # Mock viewport meta tag check
        mock_meta = Mock()
        mock_meta.count = AsyncMock(return_value=1)
        mock_page.locator = Mock(return_value=mock_meta)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_responsiveness(mock_page, "http://localhost:3000", mock_sm)
        
        # Should test both desktop and mobile
        assert mock_page.set_viewport_size.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_test_seo_checks_title_and_meta(self, browser_agent):
        """Test that SEO test validates title and meta tags."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test Page")
        
        # Mock meta description
        mock_meta_desc = AsyncMock()
        mock_meta_desc.get_attribute = AsyncMock(return_value="This is a description")
        mock_meta_locator = Mock()
        mock_meta_locator.first = mock_meta_desc
        
        def locator_side_effect(selector):
            if 'meta[name="description"]' in selector:
                return mock_meta_locator
            elif selector == "h1":
                return Mock(count=AsyncMock(return_value=1))
            elif selector == "h2":
                return Mock(count=AsyncMock(return_value=3))
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_seo(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["seo_elements"]["title"] == "Test Page"
        assert result["seo_elements"]["meta_description"] == "This is a description"
        assert result["seo_elements"]["headings"]["h1"] == 1
    
    @pytest.mark.asyncio
    async def test_test_seo_detects_multiple_h1(self, browser_agent):
        """Test that SEO test detects multiple H1 tags."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")
        
        def locator_side_effect(selector):
            if selector == "h1":
                return Mock(count=AsyncMock(return_value=3))  # Multiple H1s
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_seo(mock_page, "http://localhost:3000", mock_sm)
        
        assert any("multiple h1" in issue.lower() for issue in result["issues"])
    
    @pytest.mark.asyncio
    async def test_test_forms_validates_structure(self, browser_agent):
        """Test that form test validates form structure."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        mock_form = Mock()
        mock_submit_locator = Mock()
        mock_submit_locator.count = AsyncMock(return_value=1)
        mock_required_locator = Mock()
        mock_required_locator.count = AsyncMock(return_value=2)
        
        mock_form.locator = Mock(side_effect=lambda selector: {
            'button[type="submit"], input[type="submit"]': mock_submit_locator,
            'input[required], textarea[required], select[required]': mock_required_locator
        }.get(selector, Mock(count=AsyncMock(return_value=0))))
        
        mock_form_locator = Mock()
        mock_form_locator.count = AsyncMock(return_value=1)
        mock_form_locator.first = mock_form
        
        mock_page.locator = Mock(return_value=mock_form_locator)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_forms(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["form_summary"]["total_forms"] == 1
        assert result["form_summary"]["required_fields"] == 2
    
    def test_calculate_scores_pass_status(self, browser_agent):
        """Test score calculation for PASS status."""
        tests = {
            "interactive": {"status": "PASS", "issues": []},
            "accessibility": {"status": "PASS", "issues": []},
            "performance": {"status": "PASS", "issues": []}
        }
        
        scores = browser_agent._calculate_scores(tests)
        
        assert scores["interactive"] == 100
        assert scores["accessibility"] == 100
        assert scores["performance"] == 100
        assert scores["overall"] == 100
    
    def test_calculate_scores_warn_status(self, browser_agent):
        """Test score calculation for WARN status with issues."""
        tests = {
            "interactive": {"status": "WARN", "issues": ["Issue 1", "Issue 2"]},
            "accessibility": {"status": "PASS", "issues": []}
        }
        
        scores = browser_agent._calculate_scores(tests)
        
        # 2 issues = 100 - (2 * 10) = 80
        assert scores["interactive"] == 80
        assert scores["accessibility"] == 100
        assert scores["overall"] == 90  # Average
    
    def test_calculate_scores_fail_status(self, browser_agent):
        """Test score calculation for FAIL status."""
        tests = {
            "interactive": {"status": "FAIL", "issues": ["Critical error"]},
            "accessibility": {"status": "PASS", "issues": []}
        }
        
        scores = browser_agent._calculate_scores(tests)
        
        assert scores["interactive"] == 0
        assert scores["accessibility"] == 100
        assert scores["overall"] == 50
    
    def test_calculate_scores_skip_status(self, browser_agent):
        """Test that SKIP status is excluded from overall score."""
        tests = {
            "interactive": {"status": "PASS", "issues": []},
            "forms": {"status": "SKIP", "issues": []}
        }
        
        scores = browser_agent._calculate_scores(tests)
        
        assert scores["forms"] is None
        assert scores["overall"] == 100  # Only counts PASS
    
    def test_determine_status_excellent(self, browser_agent):
        """Test status determination for excellent scores."""
        scores = {"overall": 95}
        
        status = browser_agent._determine_status(scores)
        
        assert status == "EXCELLENT"
    
    def test_determine_status_good(self, browser_agent):
        """Test status determination for good scores."""
        scores = {"overall": 80}
        
        status = browser_agent._determine_status(scores)
        
        assert status == "GOOD"
    
    def test_determine_status_fair(self, browser_agent):
        """Test status determination for fair scores."""
        scores = {"overall": 60}
        
        status = browser_agent._determine_status(scores)
        
        assert status == "FAIR"
    
    def test_determine_status_poor(self, browser_agent):
        """Test status determination for poor scores."""
        scores = {"overall": 40}
        
        status = browser_agent._determine_status(scores)
        
        assert status == "POOR"


class TestBrowserValidationIntegration:
    """Integration tests for real-world validation scenarios."""
    
    @pytest.fixture
    def browser_agent(self):
        """Create browser agent instance."""
        import sys
        import importlib.util
        
        with patch.dict('sys.modules', {
            'app.core.socket_manager': Mock(SocketManager=Mock(return_value=Mock(emit=AsyncMock())))
        }):
            spec = importlib.util.spec_from_file_location(
                "browser_int",
                "/mnt/user-data/uploads/browser_validation_agent.py"
            )
            agent_module = importlib.util.module_from_spec(spec)
            sys.modules['browser_int'] = agent_module
            spec.loader.exec_module(agent_module)
            
            return agent_module.BrowserValidationAgent()
    
    @pytest.mark.asyncio
    async def test_quick_validate_shortcut(self, browser_agent):
        """Test that quick_validate uses quick validation level."""
        with patch.object(browser_agent, 'comprehensive_validate', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = {"overall_status": "GOOD"}
            
            result = await browser_agent.quick_validate("http://localhost:3000")
            
            mock_validate.assert_called_once_with("http://localhost:3000", "", validation_level="quick")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])