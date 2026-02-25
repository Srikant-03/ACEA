"""
Metrics Collector — Structured Performance & Observability Metrics

Collects timing, token usage, iteration counts, and quality scores
throughout a pipeline run. Serializable for checkpoint persistence
and report generation.
"""

import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and aggregates pipeline metrics.
    
    Usage:
        mc = MetricsCollector()
        mc.start_timer("architect")
        ... work ...
        mc.stop_timer("architect")
        mc.record("files_generated", 15)
        summary = mc.summary()
    """
    
    def __init__(self):
        self._timers: Dict[str, float] = {}       # Active timers (start timestamps)
        self._durations: Dict[str, float] = {}     # Completed durations (seconds)
        self._counters: Dict[str, int] = {}        # Incrementable counters
        self._gauges: Dict[str, Any] = {}          # Point-in-time values
        self._events: List[Dict[str, Any]] = []    # Timestamped events
        self._start_time: float = time.time()
    
    def start_timer(self, name: str):
        """Start a named timer."""
        self._timers[name] = time.time()
    
    def stop_timer(self, name: str) -> float:
        """Stop a named timer and record duration. Returns duration in seconds."""
        if name not in self._timers:
            return 0.0
        
        duration = time.time() - self._timers.pop(name)
        
        # Accumulate if same timer started multiple times
        if name in self._durations:
            self._durations[name] += duration
        else:
            self._durations[name] = duration
        
        return duration
    
    def record(self, key: str, value: Any):
        """Record a gauge value (overwrites previous)."""
        self._gauges[key] = value
    
    def increment(self, key: str, amount: int = 1):
        """Increment a counter."""
        self._counters[key] = self._counters.get(key, 0) + amount
    
    def event(self, name: str, details: Optional[Dict] = None):
        """Record a timestamped event."""
        self._events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(time.time() - self._start_time, 2),
            "details": details or {}
        })
    
    def summary(self) -> Dict[str, Any]:
        """Get complete metrics summary."""
        total_elapsed = time.time() - self._start_time
        
        return {
            "total_elapsed_seconds": round(total_elapsed, 2),
            "timers": {k: round(v, 2) for k, v in self._durations.items()},
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "events": self._events[-50:],  # Last 50 events
            "collected_at": datetime.now().isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for checkpoint persistence."""
        return {
            "start_time": self._start_time,
            "timers": dict(self._timers),
            "durations": dict(self._durations),
            "counters": dict(self._counters),
            "gauges": {k: v for k, v in self._gauges.items() if not callable(v)},
            "events": self._events[-100:]
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MetricsCollector":
        """Restore MetricsCollector from serialized state."""
        mc = cls()
        mc._start_time = data.get("start_time", time.time())
        mc._timers = data.get("timers", {})
        mc._durations = data.get("durations", {})
        mc._counters = data.get("counters", {})
        mc._gauges = data.get("gauges", {})
        mc._events = data.get("events", [])
        return mc


# Singleton
_collector = None

def get_metrics_collector() -> MetricsCollector:
    """Get singleton MetricsCollector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector

def reset_metrics_collector():
    """Reset the metrics collector (for new pipeline runs)."""
    global _collector
    _collector = MetricsCollector()
    return _collector
