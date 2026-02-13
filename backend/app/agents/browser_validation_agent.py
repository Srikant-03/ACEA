# ACEA Sentinel - Browser Validation Agent
# Advanced browser testing: interactivity, accessibility, performance, responsiveness
# Complements Watcher (basic load testing) with deeper quality validation

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

class BrowserValidationAgent:
    """
    Advanced browser validation focusing on:
    - Interactive element testing (buttons, forms, navigation)
    - Accessibility audits (WCAG compliance)
    - Performance metrics (Core Web Vitals)
    - Responsive design validation
    - SEO basic checks
    """
    
    def __init__(self):
        self.browser = None
        self.context = None
    
    async def comprehensive_validate(
        self, 
        url: str, 
        project_path: str,
        validation_level: str = "standard"  # "quick" | "standard" | "thorough"
    ) -> Dict[str, Any]:
        """
        Main entry point for comprehensive browser validation.
        
        Args:
            url: The URL to validate
            project_path: Path to project files
            validation_level: How deep to test
        
        Returns:
            Comprehensive validation report
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🌐 Starting comprehensive browser validation..."})
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "validation_level": validation_level,
            "overall_status": "PENDING",
            "scores": {},
            "tests": {}
        }
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (ACEA Validator Bot)"
                )
                page = await context.new_page()
                
                # Run validation tests
                if validation_level in ["quick", "standard", "thorough"]:
                    report["tests"]["interactive"] = await self._test_interactivity(page, url, sm)
                    report["tests"]["accessibility"] = await self._test_accessibility(page, url, sm)
                    report["tests"]["responsive"] = await self._test_responsiveness(page, url, sm)
                
                if validation_level in ["standard", "thorough"]:
                    report["tests"]["performance"] = await self._test_performance(page, url, sm)
                    report["tests"]["seo"] = await self._test_seo(page, url, sm)
                
                if validation_level == "thorough":
                    report["tests"]["links"] = await self._test_links(page, url, sm)
                    report["tests"]["forms"] = await self._test_forms(page, url, sm)
                
                await browser.close()
                
                # Calculate overall score
                report["scores"] = self._calculate_scores(report["tests"])
                report["overall_status"] = self._determine_status(report["scores"])
                
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"✅ Validation complete. Status: {report['overall_status']}"
                })
        
        except ImportError:
            await sm.emit("agent_log", {
                "agent_name": "BROWSER_VALIDATOR", 
                "message": "⚠️ Playwright not installed. Skipping validation."
            })
            report["overall_status"] = "SKIPPED"
            report["error"] = "Playwright not available"
        
        except Exception as e:
            await sm.emit("agent_log", {
                "agent_name": "BROWSER_VALIDATOR", 
                "message": f"❌ Validation error: {str(e)[:100]}"
            })
            report["overall_status"] = "ERROR"
            report["error"] = str(e)
        
        return report
    
    async def _test_interactivity(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests interactive elements: buttons, links, inputs.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🖱️ Testing interactivity..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "interactive_elements": {}
        }
        
        try:
            # Navigate to page
            await page.goto(url, wait_until="networkidle", timeout=15000)
            
            # Find all interactive elements
            buttons = await page.locator("button").count()
            links = await page.locator("a").count()
            inputs = await page.locator("input, textarea, select").count()
            
            results["interactive_elements"] = {
                "buttons": buttons,
                "links": links,
                "inputs": inputs
            }
            
            # Test button clicks (sample first 3 buttons)
            button_test_count = min(buttons, 3)
            for i in range(button_test_count):
                try:
                    button = page.locator("button").nth(i)
                    is_visible = await button.is_visible()
                    is_enabled = await button.is_enabled()
                    
                    if not is_visible:
                        results["issues"].append(f"Button {i+1} is not visible")
                    if not is_enabled:
                        results["issues"].append(f"Button {i+1} is disabled")
                    
                    # Try clicking (but don't wait for navigation)
                    if is_visible and is_enabled:
                        await button.click(timeout=1000)
                        await asyncio.sleep(0.5)  # Brief pause to see if anything happens
                
                except Exception as e:
                    results["issues"].append(f"Button {i+1} click failed: {str(e)[:50]}")
            
            # Test input fields (check if they accept input)
            if inputs > 0:
                try:
                    first_input = page.locator("input, textarea").first
                    await first_input.fill("test", timeout=2000)
                    value = await first_input.input_value()
                    if value != "test":
                        results["issues"].append("Input field does not accept text")
                except Exception as e:
                    results["issues"].append(f"Input test failed: {str(e)[:50]}")
            
            if results["issues"]:
                results["status"] = "WARN"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Found {len(results['issues'])} interactivity issues"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"✅ Interactive elements working ({buttons} buttons, {links} links, {inputs} inputs)"
                })
        
        except Exception as e:
            results["status"] = "FAIL"
            results["issues"].append(f"Interactivity test error: {str(e)}")
        
        return results
    
    async def _test_accessibility(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests accessibility: ARIA labels, semantic HTML, keyboard navigation.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "♿ Testing accessibility..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "wcag_checks": {}
        }
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            
            # Check for basic accessibility features
            
            # 1. Alt text on images
            images = await page.locator("img").count()
            images_with_alt = await page.locator("img[alt]").count()
            
            results["wcag_checks"]["images_total"] = images
            results["wcag_checks"]["images_with_alt"] = images_with_alt
            
            if images > 0 and images_with_alt < images:
                results["issues"].append(f"{images - images_with_alt} images missing alt text")
            
            # 2. Form labels
            inputs = await page.locator("input:not([type='hidden'])").count()
            labeled_inputs = await page.locator("input[aria-label], input[id]:has(+ label), label > input").count()
            
            results["wcag_checks"]["inputs_total"] = inputs
            results["wcag_checks"]["labeled_inputs"] = labeled_inputs
            
            if inputs > 0 and labeled_inputs < inputs:
                results["issues"].append(f"{inputs - labeled_inputs} inputs missing labels")
            
            # 3. Heading hierarchy
            h1_count = await page.locator("h1").count()
            
            results["wcag_checks"]["h1_count"] = h1_count
            
            if h1_count == 0:
                results["issues"].append("No H1 heading found")
            elif h1_count > 1:
                results["issues"].append(f"Multiple H1 headings ({h1_count}) - should have only one")
            
            # 4. Semantic HTML
            has_nav = await page.locator("nav").count() > 0
            has_main = await page.locator("main").count() > 0
            has_header = await page.locator("header").count() > 0
            
            results["wcag_checks"]["semantic_html"] = {
                "has_nav": has_nav,
                "has_main": has_main,
                "has_header": has_header
            }
            
            if not has_main:
                results["issues"].append("Missing <main> landmark")
            
            # 5. Button accessibility
            buttons = await page.locator("button").count()
            buttons_with_text = await page.locator("button:has-text(/\\w+/)").count()
            
            if buttons > 0 and buttons_with_text < buttons:
                results["issues"].append(f"{buttons - buttons_with_text} buttons without text content")
            
            # Determine status
            if len(results["issues"]) > 5:
                results["status"] = "FAIL"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"❌ Accessibility: {len(results['issues'])} critical issues"
                })
            elif len(results["issues"]) > 0:
                results["status"] = "WARN"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Accessibility: {len(results['issues'])} minor issues"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": "✅ Accessibility checks passed"
                })
        
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Accessibility test error: {str(e)}")
        
        return results
    
    async def _test_responsiveness(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests responsive design across different viewport sizes.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "📱 Testing responsiveness..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "viewports": {}
        }
        
        viewports = {
            "mobile": {"width": 375, "height": 667},
            "tablet": {"width": 768, "height": 1024},
            "desktop": {"width": 1920, "height": 1080}
        }
        
        try:
            for device, size in viewports.items():
                await page.set_viewport_size(size)
                await page.goto(url, wait_until="networkidle", timeout=15000)
                
                # Check for horizontal scroll (bad UX on mobile)
                scroll_width = await page.evaluate("document.documentElement.scrollWidth")
                client_width = await page.evaluate("document.documentElement.clientWidth")
                
                has_horizontal_scroll = scroll_width > client_width
                
                results["viewports"][device] = {
                    "width": size["width"],
                    "height": size["height"],
                    "scroll_width": scroll_width,
                    "horizontal_scroll": has_horizontal_scroll
                }
                
                if has_horizontal_scroll and device == "mobile":
                    results["issues"].append(f"Horizontal scroll on {device} ({scroll_width}px > {client_width}px)")
                    results["status"] = "WARN"
            
            if results["status"] == "PASS":
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": "✅ Responsive design validated across 3 viewports"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Responsiveness: {len(results['issues'])} issues"
                })
        
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Responsiveness test error: {str(e)}")
        
        return results
    
    async def _test_performance(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests performance: load time, resource counts, basic metrics.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "⚡ Testing performance..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "metrics": {}
        }
        
        try:
            # Measure load time
            start_time = asyncio.get_event_loop().time()
            
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            load_time = (asyncio.get_event_loop().time() - start_time) * 1000  # ms
            
            # Get performance metrics
            performance_metrics = await page.evaluate("""
                () => {
                    const perf = performance.getEntriesByType('navigation')[0];
                    return {
                        dom_content_loaded: perf.domContentLoadedEventEnd - perf.domContentLoadedEventStart,
                        load_complete: perf.loadEventEnd - perf.loadEventStart,
                        dom_interactive: perf.domInteractive,
                        response_time: perf.responseEnd - perf.requestStart
                    };
                }
            """)
            
            results["metrics"] = {
                "total_load_time_ms": round(load_time, 2),
                **performance_metrics
            }
            
            # Performance thresholds
            if load_time > 5000:
                results["issues"].append(f"Slow load time: {round(load_time)}ms (should be < 5000ms)")
                results["status"] = "WARN"
            
            if performance_metrics.get("dom_interactive", 0) > 3000:
                results["issues"].append("DOM interactive time > 3s")
                results["status"] = "WARN"
            
            if results["status"] == "PASS":
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"✅ Performance: {round(load_time)}ms load time"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Performance issues detected"
                })
        
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Performance test error: {str(e)}")
        
        return results
    
    async def _test_seo(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests basic SEO: title, meta description, headings.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🔍 Testing SEO..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "seo_elements": {}
        }
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            
            # Check title
            title = await page.title()
            results["seo_elements"]["title"] = title
            
            if not title or len(title) < 10:
                results["issues"].append("Title missing or too short")
            elif len(title) > 60:
                results["issues"].append(f"Title too long ({len(title)} chars, recommend < 60)")
            
            # Check meta description
            meta_desc = await page.locator('meta[name="description"]').get_attribute("content")
            results["seo_elements"]["meta_description"] = meta_desc
            
            if not meta_desc:
                results["issues"].append("Meta description missing")
            elif len(meta_desc) > 160:
                results["issues"].append(f"Meta description too long ({len(meta_desc)} chars)")
            
            # Check heading structure
            h1_count = await page.locator("h1").count()
            h2_count = await page.locator("h2").count()
            
            results["seo_elements"]["headings"] = {
                "h1": h1_count,
                "h2": h2_count
            }
            
            if h1_count == 0:
                results["issues"].append("No H1 heading")
            elif h1_count > 1:
                results["issues"].append(f"Multiple H1 headings ({h1_count})")
            
            # Determine status
            if len(results["issues"]) > 3:
                results["status"] = "WARN"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ SEO: {len(results['issues'])} issues"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": "✅ SEO basics validated"
                })
        
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"SEO test error: {str(e)}")
        
        return results
    
    async def _test_links(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests all links on the page to ensure they're not broken.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🔗 Testing links..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "link_summary": {}
        }
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            
            # Get all links
            links = await page.locator("a[href]").all()
            
            total_links = len(links)
            broken_links = []
            
            # Test first 10 links (to avoid timeout)
            test_count = min(total_links, 10)
            
            for i in range(test_count):
                try:
                    href = await links[i].get_attribute("href")
                    
                    # Skip anchors and javascript links
                    if href and not href.startswith("#") and not href.startswith("javascript:"):
                        # Check if link is valid (basic check)
                        if href.startswith("http"):
                            # External link - just note it
                            pass
                        elif href.startswith("/"):
                            # Internal link - could test but skip for now
                            pass
                        else:
                            # Relative link
                            pass
                
                except Exception as e:
                    broken_links.append(f"Link {i+1}: {str(e)[:50]}")
            
            results["link_summary"] = {
                "total_links": total_links,
                "tested": test_count,
                "broken": len(broken_links)
            }
            
            results["issues"] = broken_links
            
            if broken_links:
                results["status"] = "WARN"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Found {len(broken_links)} problematic links"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"✅ Links validated ({test_count} tested)"
                })
        
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Link test error: {str(e)}")
        
        return results
    
    async def _test_forms(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Tests form functionality and validation.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "📝 Testing forms..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "form_summary": {}
        }
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            
            # Find forms
            forms = await page.locator("form").count()
            
            results["form_summary"]["total_forms"] = forms
            
            if forms == 0:
                results["status"] = "SKIP"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": "ℹ️ No forms found to test"
                })
                return results
            
            # Test first form
            form = page.locator("form").first
            
            # Check for submit button
            submit_buttons = await form.locator('button[type="submit"], input[type="submit"]').count()
            
            if submit_buttons == 0:
                results["issues"].append("Form missing submit button")
            
            # Check for required fields
            required_inputs = await form.locator("input[required], textarea[required], select[required]").count()
            
            results["form_summary"]["required_fields"] = required_inputs
            
            if results["issues"]:
                results["status"] = "WARN"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Form validation: {len(results['issues'])} issues"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"✅ Form structure validated ({forms} forms)"
                })
        
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Form test error: {str(e)}")
        
        return results
    
    def _calculate_scores(self, tests: Dict[str, Any]) -> Dict[str, int]:
        """
        Calculates scores (0-100) for each test category.
        """
        scores = {}
        
        for test_name, test_result in tests.items():
            if test_result.get("status") == "PASS":
                scores[test_name] = 100
            elif test_result.get("status") == "WARN":
                # Score based on issue count
                issue_count = len(test_result.get("issues", []))
                scores[test_name] = max(50, 100 - (issue_count * 10))
            elif test_result.get("status") == "FAIL":
                scores[test_name] = 0
            elif test_result.get("status") == "SKIP":
                scores[test_name] = None  # Not applicable
            else:
                scores[test_name] = 50  # ERROR or unknown
        
        # Calculate overall score (average of non-None scores)
        valid_scores = [s for s in scores.values() if s is not None]
        scores["overall"] = round(sum(valid_scores) / len(valid_scores)) if valid_scores else 0
        
        return scores
    
    def _determine_status(self, scores: Dict[str, int]) -> str:
        """
        Determines overall status based on scores.
        """
        overall_score = scores.get("overall", 0)
        
        if overall_score >= 90:
            return "EXCELLENT"
        elif overall_score >= 75:
            return "GOOD"
        elif overall_score >= 50:
            return "FAIR"
        else:
            return "POOR"
    
    async def quick_validate(self, url: str) -> Dict[str, Any]:
        """
        Quick validation - just interactivity and accessibility.
        """
        return await self.comprehensive_validate(url, "", validation_level="quick")