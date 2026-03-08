
# Integration tests for Browser Validation Agent
# Tests Playwright-based UI validation: interactivity, accessibility, performance, SEO

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from app.agents.browser_validation_agent import BrowserValidationAgent

class TestBrowserValidationAgent:
    """Test suite for BrowserValidationAgent."""
    
    @pytest.fixture
    def browser_agent(self):
        """Create a BrowserValidationAgent instance for testing."""
        # SocketManager is imported inside comprehensive_validate, so we don't need to patch it here
        # unless we call comprehensive_validate directly.
        return BrowserValidationAgent()
    
    @pytest.mark.asyncio
    async def test_comprehensive_validate_quick_level(self, browser_agent):
        """Test quick validation level runs basic tests only."""
        with patch('playwright.async_api.async_playwright') as mock_playwright, \
             patch('app.core.socket_manager.SocketManager') as MockSM:
             
            mock_p = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            
            mock_playwright.return_value.__aenter__.return_value = mock_p
            MockSM.return_value.emit = AsyncMock()
            
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
        with patch('playwright.async_api.async_playwright') as mock_playwright, \
             patch('app.core.socket_manager.SocketManager') as MockSM:
            mock_p = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            
            mock_playwright.return_value.__aenter__.return_value = mock_p
            MockSM.return_value.emit = AsyncMock()
            
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
        with patch('playwright.async_api.async_playwright') as mock_playwright, \
             patch('app.core.socket_manager.SocketManager') as MockSM:
            mock_p = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            
            mock_playwright.return_value.__aenter__.return_value = mock_p
            MockSM.return_value.emit = AsyncMock()
            
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
    async def test_interactivity_counts_elements(self, browser_agent):
        """Test that interactivity test counts interactive elements."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        
        # Mock element counts
        mock_locator_button = Mock()
        mock_locator_button.count = AsyncMock(return_value=5)
        # Mock button locator filter for regex check (new logic)
        mock_locator_button.filter = Mock(return_value=Mock(count=AsyncMock(return_value=5)))
        mock_locator_button.nth = Mock(return_value=AsyncMock(is_visible=AsyncMock(return_value=True), is_enabled=AsyncMock(return_value=True), click=AsyncMock()))
        
        mock_locator_link = Mock()
        mock_locator_link.count = AsyncMock(return_value=10)
        
        mock_locator_input = Mock()
        mock_locator_input.count = AsyncMock(return_value=3)
        mock_locator_input.first = AsyncMock(input_value=AsyncMock(return_value="test"), fill=AsyncMock())
        
        def locator_side_effect(selector):
            if selector == "button":
                return mock_locator_button
            elif selector == "a":
                return mock_locator_link
            elif "input" in selector:
                # Handle complex selectors
                if "test" in selector: # fill check
                     return mock_locator_input
                return mock_locator_input
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_interactivity(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["interactive_elements"]["buttons"] == 5
        assert result["interactive_elements"]["links"] == 10

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
        
        # New regex filtering for buttons
        mock_btn_text = Mock()
        mock_btn_text.count = AsyncMock(return_value=5)
        mock_btn = Mock()
        mock_btn.count = AsyncMock(return_value=5)
        mock_btn.filter = Mock(return_value=mock_btn_text)
        
        def locator_side_effect(selector):
            if selector == "img":
                return mock_img_locator
            elif 'not([alt])' in selector:
                return mock_img_no_alt
            elif selector == "button":
                return mock_btn
            return Mock(count=AsyncMock(return_value=0))
        
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_accessibility(mock_page, "http://localhost:3000", mock_sm)
        
        assert any("alt" in issue.lower() for issue in result["issues"])
        assert result["wcag_checks"]["images_total"] == 3
        
    @pytest.mark.asyncio
    async def test_test_seo_checks_meta_description(self, browser_agent):
        """Test SEO checks meta description logic."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test Page Title That Is Good Length")
        
        # Mock meta locator
        mock_meta_loc = Mock()
        mock_meta_loc.count = AsyncMock(return_value=1)
        mock_meta_loc.get_attribute = AsyncMock(return_value="Valid description")
        
        def locator_side_effect(selector):
            if 'meta[name="description"]' in selector:
                return mock_meta_loc
            elif selector == "h1":
                return Mock(count=AsyncMock(return_value=1))
            elif selector == "h2":
                return Mock(count=AsyncMock(return_value=0))
            return Mock(count=AsyncMock(return_value=0))
            
        mock_page.locator = Mock(side_effect=locator_side_effect)
        
        mock_sm = Mock(emit=AsyncMock())
        
        result = await browser_agent._test_seo(mock_page, "http://localhost:3000", mock_sm)
        
        assert result["status"] == "PASS"
        assert result["seo_elements"]["meta_description"] == "Valid description"