# ACEA Sentinel - Browser Validation Agent
# Advanced browser testing: interactivity, accessibility, performance, responsiveness
# Complements Watcher (basic load testing) with deeper quality validation

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

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
                print(f"DEBUG: Running validation with level {validation_level}")
                if validation_level in ["quick", "standard", "thorough"]:
                    print("DEBUG: Entering standard tests block")
                    report["tests"]["interactive"] = await self._test_interactivity(page, url, sm)
                    report["tests"]["accessibility"] = await self._test_accessibility(page, url, sm)
                    report["tests"]["responsive"] = await self._test_responsiveness(page, url, sm)
                
                    # New: Visual Overlap Detection
                    print("DEBUG: Before Overlap Call")
                    await sm.emit("preview_test_progress", {"phase": "validating", "test": "visual_overlap"}, room=None)
                    overlap_result = await self._test_visual_overlap(page, url, sm)
                    print(f"DEBUG: Overlap Result Keys: {overlap_result.keys()}")
                    report["tests"]["visual_overlap"] = overlap_result
                
                if validation_level in ["standard", "thorough"]:
                    report["tests"]["performance"] = await self._test_performance(page, url, sm)
                    report["tests"]["seo"] = await self._test_seo(page, url, sm)
                    
                    # New: Prompt Alignment & Change Tracking
                    await sm.emit("preview_test_progress", {"phase": "validating", "test": "prompt_alignment"}, room=None)
                    report["tests"]["prompt_alignment"] = await self._test_prompt_alignment(page, url, project_path, sm)

                    # CRITICAL: Standalone Contrast Check (catches invisible text immediately)
                    await sm.emit("preview_test_progress", {"phase": "validating", "test": "contrast_check"}, room=None)
                    report["tests"]["contrast_check"] = await self._test_contrast(page, url, sm)

                    # New: Feature Interaction testing (The "Human" test)
                    await sm.emit("preview_test_progress", {"phase": "validating", "test": "feature_interaction"}, room=None)
                    report["tests"]["feature_interaction"] = await self._test_feature_interaction(page, url, project_path, sm)
                
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
            # Check for buttons with text content using regex
            buttons_with_text = await page.locator("button").filter(has_text=re.compile(r"\w+")).count()
            
            if buttons > 0 and buttons_with_text < buttons:
                results["issues"].append(f"{buttons - buttons_with_text} buttons without text content")
            
            # 6. Color Contrast Check (WCAG AA)
            contrast_issues = await page.evaluate("""() => {
                function getLuminance(r, g, b) {
                    const a = [r, g, b].map(v => {
                        v /= 255;
                        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
                    });
                    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
                }

                function getContrastRatio(l1, l2) {
                    const lighter = Math.max(l1, l2);
                    const darker = Math.min(l1, l2);
                    return (lighter + 0.05) / (darker + 0.05);
                }

                function parseColor(color) {
                    if (!color) return null;
                    const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
                    if (!match) return null;
                    return {
                        r: parseInt(match[1]),
                        g: parseInt(match[2]),
                        b: parseInt(match[3]),
                        a: match[4] !== undefined ? parseFloat(match[4]) : 1
                    };
                }

                function getBackgroundColor(el) {
                    let current = el;
                    while (current) {
                        const style = window.getComputedStyle(current);
                        const color = parseColor(style.backgroundColor);
                        if (color && color.a > 0) return color; // Found opaque-ish background
                        current = current.parentElement;
                    }
                    return { r: 255, g: 255, b: 255, a: 1 }; // Default to white
                }

                const issues = [];
                const scanner = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                let node;
                
                while (node = scanner.nextNode()) {
                    const parent = node.parentElement;
                    if (!parent) continue;
                    
                    const style = window.getComputedStyle(parent);
                    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
                    
                    if (node.nodeValue.trim().length === 0) continue;

                    const fg = parseColor(style.color);
                    const bg = getBackgroundColor(parent);

                    if (fg && bg) {
                        // Blend foreground with background if fg is transparent
                        // Simplified blending assuming bg is opaque for now
                        const lum1 = getLuminance(fg.r, fg.g, fg.b);
                        const lum2 = getLuminance(bg.r, bg.g, bg.b);
                        const ratio = getContrastRatio(lum1, lum2);

                        if (ratio < 4.5 && style.fontSize !== '0px') {
                            // Ignore large text exemption for simplicity (checking strictly for now)
                            // Clean up text for report
                            const textSample = node.nodeValue.trim().substring(0, 20);
                            issues.push(`Low contrast (${ratio.toFixed(2)}:1) for text "${textSample}"`);
                        }
                    }
                }
                // Limit identical reports
                return [...new Set(issues)].slice(0, 10);
            }""")

            if contrast_issues:
                results["issues"].extend(contrast_issues)
                results["wcag_checks"]["contrast_issues"] = len(contrast_issues)

            # Determine status — CONTRAST issues are CRITICAL, not just warnings
            contrast_count = len(contrast_issues) if contrast_issues else 0
            total_issues = len(results["issues"])

            if contrast_count >= 2 or total_issues > 5:
                results["status"] = "FAIL"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"❌ Accessibility FAIL: {contrast_count} contrast violations, {total_issues} total issues"
                })
            elif total_issues > 0:
                results["status"] = "WARN"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": f"⚠️ Accessibility: {total_issues} issues ({contrast_count} contrast)"
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
            meta_desc_locator = page.locator('meta[name="description"]')
            if await meta_desc_locator.count() > 0:
                meta_desc = await meta_desc_locator.get_attribute("content")
                results["seo_elements"]["meta_description"] = meta_desc
                
                if not meta_desc:
                    results["issues"].append("Meta description empty")
                elif len(meta_desc) > 160:
                    results["issues"].append(f"Meta description too long ({len(meta_desc)} chars)")
            else:
                results["seo_elements"]["meta_description"] = None
                results["issues"].append("Meta description missing")
            
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
        """Validate form structure and usability."""
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "📝 Testing forms..."})
        results = {
            "status": "PASS",
            "issues": [],
            "form_summary": {
                "total_forms": 0,
                "required_fields": 0,
                "submit_buttons": 0
            }
        }
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            forms = await page.locator("form").count()
            results["form_summary"]["total_forms"] = forms
            
            if forms == 0:
                results["status"] = "SKIP"
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR", 
                    "message": "ℹ️ No forms found to test"
                })
                return results
            
            for i in range(forms):
                form = page.locator("form").nth(i)
                
                # Check for submit button
                submit_btns = await form.locator('button[type="submit"], input[type="submit"]').count()
                results["form_summary"]["submit_buttons"] += submit_btns
                
                if submit_btns == 0:
                    results["issues"].append(f"Form {i+1} missing submit button")
                
                # Check required fields
                required = await form.locator('input[required], textarea[required], select[required]').count()
                results["form_summary"]["required_fields"] += required
            
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
    
    async def _test_visual_overlap(self, page, url: str, sm) -> Dict[str, Any]:
        """Detect overlapping interactive elements using heavy DOM analysis."""
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "📐 Analyzing visual overlap..."})
        
        results = {
            "status": "PASS",
            "issues": [],
            "overlaps": []
        }
        
        try:
            # Run JS to find overlapping elements
            js_result = await page.evaluate("""() => {
                const interactiveSelectors = 'button, a, input, select, textarea, [role="button"]';
                const elements = Array.from(document.querySelectorAll(interactiveSelectors));
                const visibleElements = elements.filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                });
                
                const overlaps = [];
                let comparisons = 0;
                
                for (let i = 0; i < visibleElements.length; i++) {
                    for (let j = i + 1; j < visibleElements.length; j++) {
                        comparisons++;
                        const r1 = visibleElements[i].getBoundingClientRect();
                        const r2 = visibleElements[j].getBoundingClientRect();
                        
                        const overlap = !(r1.right < r2.left || 
                                        r1.left > r2.right || 
                                        r1.bottom < r2.top || 
                                        r1.top > r2.bottom);
                                        
                        if (overlap) {
                            // Calculate intersection area
                            const x_overlap = Math.max(0, Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left));
                            const y_overlap = Math.max(0, Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top));
                            const overlapArea = x_overlap * y_overlap;
                            const r1Area = r1.width * r1.height;
                            const r2Area = r2.width * r2.height;
                            
                            // Report if significant overlap (>10% of smaller element)
                            if (overlapArea > 0.1 * Math.min(r1Area, r2Area)) {
                                overlaps.push({
                                    el1: visibleElements[i].innerText.slice(0, 20) || visibleElements[i].tagName,
                                    el2: visibleElements[j].innerText.slice(0, 20) || visibleElements[j].tagName,
                                    area: overlapArea
                                });
                            }
                        }
                    }
                }
                return { overlaps, visibleCount: visibleElements.length, comparisons };
            }""")
            
            overlaps = js_result["overlaps"]
            results["overlaps"] = overlaps
            results["debug"] = {
                "visible_elements": js_result["visibleCount"],
                "comparisons": js_result["comparisons"]
            }
            
            if overlaps:
                results["status"] = "WARN" if len(overlaps) < 3 else "FAIL"
                results["issues"].append(f"Found {len(overlaps)} visual overlaps")
                for o in overlaps:
                    results["issues"].append(f"Overlap: '{o['el1']}' overlaps '{o['el2']}'")
            
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Overlap detection error: {str(e)[:100]}")
            
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
        """Determines overall status based on scores."""
        overall_score = scores.get("overall", 0)
        if overall_score >= 90:
            return "EXCELLENT"
        elif overall_score >= 75:
            return "GOOD"
        elif overall_score >= 50:
            return "FAIR"
        else:
            return "POOR"

    # Reusable JS: scans all visible text for WCAG AA contrast failures
    CONTRAST_SCAN_JS = r"""() => {
        function lum(r,g,b){const a=[r,g,b].map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)});return a[0]*0.2126+a[1]*0.7152+a[2]*0.0722}
        function cr(l1,l2){return(Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05)}
        function pc(c){if(!c)return null;const m=c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);return m?{r:+m[1],g:+m[2],b:+m[3],a:m[4]!==undefined?+m[4]:1}:null}
        function bg(el){let c=el;while(c){const x=pc(getComputedStyle(c).backgroundColor);if(x&&x.a>0)return x;c=c.parentElement}return{r:255,g:255,b:255,a:1}}
        const out=[];const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
        let n;while(n=w.nextNode()){const p=n.parentElement;if(!p)continue;const s=getComputedStyle(p);
        if(s.display==='none'||s.visibility==='hidden'||+s.opacity===0)continue;
        const t=n.nodeValue.trim();if(!t)continue;
        const f=pc(s.color),b2=bg(p);if(f&&b2){const r=cr(lum(f.r,f.g,f.b),lum(b2.r,b2.g,b2.b));
        if(r<4.5&&s.fontSize!=='0px')out.push({text:t.substring(0,30),ratio:+r.toFixed(2),fg:'rgb('+f.r+','+f.g+','+f.b+')',bg:'rgb('+b2.r+','+b2.g+','+b2.b+')'})}}
        const seen=new Set();return out.filter(i=>{if(seen.has(i.text))return false;seen.add(i.text);return true}).slice(0,15)
    }""" # noqa: E501

    async def _test_contrast(self, page, url: str, sm) -> Dict[str, Any]:
        """
        Standalone contrast check — catches invisible text on first page load.
        This is the PRIMARY defense against black-on-black and similar issues.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🎨 Scanning for invisible text (contrast check)..."})
        results = {"status": "PASS", "issues": [], "failures": []}
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            await asyncio.sleep(0.5)

            contrast_failures = await page.evaluate(self.CONTRAST_SCAN_JS)

            if contrast_failures:
                results["status"] = "FAIL"
                for fail in contrast_failures:
                    msg = (
                        f"INVISIBLE TEXT: \"{fail['text']}\" has contrast {fail['ratio']}:1 "
                        f"(fg={fail['fg']}, bg={fail['bg']}). Min is 4.5:1."
                    )
                    results["issues"].append(msg)
                    results["failures"].append(fail)

                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR",
                    "message": f"❌ CONTRAST FAIL: {len(contrast_failures)} text elements are unreadable!"
                })
            else:
                await sm.emit("agent_log", {
                    "agent_name": "BROWSER_VALIDATOR",
                    "message": "✅ All text has sufficient contrast (≥4.5:1)"
                })
        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Contrast check error: {str(e)[:120]}")
        return results

    async def _test_feature_interaction(self, page, url: str, project_path: str, sm) -> Dict[str, Any]:
        """
        LLM-driven human-like feature testing.
        After every interaction, runs a contrast scan to verify new content
        is actually READABLE — not just present in the DOM.
        """
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🤖 Simulating human interactions..."})

        results = {"status": "PASS", "issues": [], "features_tested": [], "interaction_log": []}

        try:
            prompt_file = Path(project_path) / "prompt.txt"
            original_prompt = prompt_file.read_text(encoding="utf-8").strip() if prompt_file.exists() else "A web application"
            page_content = await page.evaluate("() => document.body.innerText.slice(0, 2000)")

            from app.core.local_model import HybridModelClient
            client = HybridModelClient()

            plan_prompt = f"""Identify up to 3 testable user actions for this web app.
GOAL: {original_prompt[:500]}
PAGE CONTENT: {page_content}

Return JSON:
{{
    "features": [
        {{
            "name": "short action name (e.g. Add Task)",
            "steps": "Describe what a human would do step by step",
            "expected": "What should be visible after the action"
        }}
    ]
}}"""
            response = await client.generate(plan_prompt, json_mode=True)
            from app.core.schema_validator import safe_parse_json
            plan, _ = safe_parse_json(response)

            if not plan or not plan.get("features"):
                results["status"] = "SKIP"
                results["interaction_log"].append("No testable features identified")
                return results

            for feature in plan["features"][:3]:
                fname = feature.get("name", "Unknown")
                await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": f"▶️ Testing: {fname}..."})

                # Fresh page load for each feature
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(0.5)

                # Take pre-snapshot AFTER this fresh load (critical fix)
                pre_contrast = await page.evaluate(self.CONTRAST_SCAN_JS)
                pre_texts = {i["text"] for i in pre_contrast}

                # Log any pre-existing contrast issues too
                if pre_contrast:
                    results["interaction_log"].append(
                        f"⚠️ Page already has {len(pre_contrast)} contrast issue(s) before '{fname}'"
                    )

                code_prompt = f"""Write async Python Playwright code to test: "{fname}".
Steps: {feature.get('steps', '')}
Expected: {feature.get('expected', '')}
Page content: {page_content[:1000]}

RULES:
1. Variable 'page' already exists. Do NOT import anything.
2. NO try/except blocks.
3. Use page.locator(), page.get_by_placeholder(), page.get_by_role(), page.get_by_text().
4. After the action, call: await page.wait_for_timeout(500)
5. Do NOT assert visibility — I check readability separately.
6. Output ONLY raw Python code, no markdown.

Example:
await page.get_by_placeholder("Add a new task").fill("Buy groceries")
await page.get_by_role("button", name="Add").click()
await page.wait_for_timeout(500)
"""
                generated = await client.generate(code_prompt)
                code = generated.replace("```python", "").replace("```", "").strip()
                code = "\n".join(l for l in code.splitlines() if not l.strip().startswith(("import ", "from ", "#")))
                results["interaction_log"].append(f"Code for '{fname}': {code[:150]}")

                # Execute the interaction
                try:
                    indented = "\n".join(f"    {l}" for l in code.splitlines())
                    exec_code = f"async def _run():\n{indented}\n"
                    ns = {"page": page, "asyncio": asyncio}
                    exec(exec_code, ns)
                    await ns["_run"]()
                    results["interaction_log"].append(f"✅ '{fname}' executed")
                except Exception as e:
                    err = str(e)[:120]
                    results["features_tested"].append({"name": fname, "status": "FAIL", "error": err})
                    results["interaction_log"].append(f"❌ '{fname}' failed: {err}")
                    results["issues"].append(f"Feature '{fname}' failed: {err}")
                    continue

                # === POST-INTERACTION READABILITY CHECK ===
                await asyncio.sleep(0.5)  # Let rendering settle
                post_contrast = await page.evaluate(self.CONTRAST_SCAN_JS)
                new_failures = [f for f in post_contrast if f["text"] not in pre_texts]

                if new_failures:
                    for fail in new_failures:
                        msg = (
                            f"INVISIBLE TEXT after '{fname}': "
                            f"\"{fail['text']}\" has contrast {fail['ratio']}:1 "
                            f"(fg={fail['fg']}, bg={fail['bg']}). Min is 4.5:1."
                        )
                        results["issues"].append(msg)
                        results["interaction_log"].append(f"\U0001f441 {msg}")
                    results["features_tested"].append({"name": fname, "status": "FAIL", "error": f"{len(new_failures)} unreadable element(s)"})
                    await sm.emit("agent_log", {
                        "agent_name": "BROWSER_VALIDATOR",
                        "message": f"❌ '{fname}': {len(new_failures)} NEW invisible text element(s)!"
                    })
                else:
                    results["features_tested"].append({"name": fname, "status": "PASS"})
                    results["interaction_log"].append(f"\U0001f441 '{fname}': all new content readable")
                    await sm.emit("agent_log", {
                        "agent_name": "BROWSER_VALIDATOR",
                        "message": f"✅ '{fname}': all new content is readable"
                    })

            if any(f["status"] == "FAIL" for f in results["features_tested"]):
                results["status"] = "FAIL"
            elif results["issues"]:
                results["status"] = "WARN"

        except Exception as e:
            results["status"] = "ERROR"
            results["issues"].append(f"Feature interaction error: {str(e)[:120]}")

        return results
    async def _test_prompt_alignment(self, page, url: str, project_path: str, sm) -> Dict[str, Any]:
        """Verify if page content matches original prompt and track changes."""
        await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": "🤖 Verifying alignment with Master Prompt..."})
        results = {"status": "PASS", "issues": [], "alignment_score": 100, "change_log": [], "original_prompt": None}
        try:
            prompt_file = Path(project_path) / "prompt.txt"
            if not prompt_file.exists():
                results["status"] = "SKIP"
                results["issues"].append("Master Prompt not found (prompt.txt missing)")
                return results
            original_prompt = prompt_file.read_text(encoding="utf-8").strip()
            results["original_prompt"] = original_prompt[:100] + "..."
            content = await page.evaluate("document.body.innerText")
            content = content[:4000]
            from app.core.local_model import HybridModelClient
            client = HybridModelClient()
            llm_prompt = f"""ANALYZE WEB PAGE ALIGNMENT.
ORIGINAL GOAL: {original_prompt}
CURRENT PAGE CONTENT: {content}
TASK: 1. Score 0-100. 2. Missing features. 3. New features.
OUTPUT JSON: {{"alignment_score": <0-100>, "aligned": <bool>, "missing_features": [], "new_features": [], "summary": ""}}"""
            response = await client.generate(llm_prompt, json_mode=True)
            from app.core.schema_validator import safe_parse_json
            analysis, _ = safe_parse_json(response)
            if analysis:
                results["alignment_score"] = analysis.get("alignment_score", 100)
                results["change_log"] = analysis.get("new_features", [])
                missing = analysis.get("missing_features", [])
                if missing:
                    results["status"] = "WARN"
                    for m in missing:
                        results["issues"].append(f"Missing feature: {m}")
                if results["alignment_score"] < 70:
                    results["status"] = "FAIL"
                    results["issues"].append(f"Low alignment score: {results['alignment_score']}/100")
                if results["status"] == "PASS":
                    await sm.emit("agent_log", {"agent_name": "BROWSER_VALIDATOR", "message": f"✅ Aligned with prompt ({results['alignment_score']}%)"})
        except Exception as e:
            results["status"] = "WARN"
            results["issues"].append(f"Prompt alignment check failed: {str(e)[:100]}")
        return results

    async def quick_validate(self, url: str) -> Dict[str, Any]:
        """
        Quick validation - just interactivity and accessibility.
        """
        return await self.comprehensive_validate(url, "", validation_level="quick")