"""Persistent progress tracking for the Java Full-Stack Training Agent."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROGRESS_DIR = Path.home() / ".java_training"
PROGRESS_FILE = PROGRESS_DIR / "progress.json"

PHASE_MODULE_MAP: dict[int, list[int]] = {
    1: [1, 2, 3, 4, 5],
    2: [6, 7, 8, 9, 10],
    3: [11, 12, 13, 14, 15],
    4: [16, 17, 18, 19, 20],
    5: [21, 22, 23, 24, 25],
    6: [26, 27, 28, 29],
    7: [30, 31, 32, 33, 34],
    8: [35, 36, 37, 38, 39, 40, 41],
}

PHASE_NAMES = {
    1: "Java Foundations",
    2: "Object-Oriented Programming",
    3: "Advanced Java",
    4: "Oracle DB 23ai & Persistence",
    5: "Spring Framework",
    6: "Frontend & Oracle APEX",
    7: "Enterprise Java & OCI",
    8: "AI Integration",
}

TOTAL_MODULES = 41


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_progress() -> dict[str, Any]:
    return {
        "student_name": "",
        "started_at": _now_iso(),
        "last_active": _now_iso(),
        "current_phase": 1,
        "current_module": 1,
        "completed_modules": [],
        "completed_phases": [],
        "assessment_scores": [],
        "notes": {},
        "total_study_minutes": 0,
        "session_count": 0,
    }


class ProgressTracker:
    def __init__(self) -> None:
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()
        self._data["session_count"] = self._data.get("session_count", 0) + 1
        self._save()

    def _load(self) -> dict[str, Any]:
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return _default_progress()

    def _save(self) -> None:
        self._data["last_active"] = _now_iso()
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ── Progress mutations ────────────────────────────────────────────────────

    def mark_module_complete(self, phase: int, module: int, notes: str = "") -> None:
        if module not in self._data["completed_modules"]:
            self._data["completed_modules"].append(module)
        if notes:
            self._data["notes"][f"module_{module}"] = notes
        self._update_current_position()
        self._save()

    def mark_phase_complete(self, phase: int, notes: str = "") -> None:
        if phase not in self._data["completed_phases"]:
            self._data["completed_phases"].append(phase)
        if notes:
            self._data["notes"][f"phase_{phase}"] = notes
        self._update_current_position()
        self._save()

    def save_assessment_score(
        self,
        phase: int,
        module: int | None,
        assessment_type: str,
        score: float,
        notes: str = "",
    ) -> None:
        entry: dict[str, Any] = {
            "phase": phase,
            "module": module,
            "assessment_type": assessment_type,
            "score": score,
            "passed": score >= 70,
            "timestamp": _now_iso(),
        }
        if notes:
            entry["notes"] = notes
        self._data["assessment_scores"].append(entry)
        self._save()

    def unlock_next(self, phase: int, module: int | None) -> dict[str, Any]:
        all_modules = PHASE_MODULE_MAP.get(phase, [])
        if module and module in all_modules:
            idx = all_modules.index(module)
            if idx + 1 < len(all_modules):
                next_mod = all_modules[idx + 1]
                self._data["current_module"] = next_mod
                self._save()
                return {"unlocked": f"Module {next_mod}", "type": "module"}
        # Move to next phase
        next_phase = phase + 1
        if next_phase <= 8:
            next_mod = PHASE_MODULE_MAP[next_phase][0]
            self._data["current_phase"] = next_phase
            self._data["current_module"] = next_mod
            self._save()
            return {
                "unlocked": f"Phase {next_phase}: {PHASE_NAMES[next_phase]}",
                "type": "phase",
                "first_module": next_mod,
            }
        return {"unlocked": "Curriculum complete — Capstone Project!", "type": "complete"}

    def _update_current_position(self) -> None:
        completed = set(self._data["completed_modules"])
        for phase, modules in PHASE_MODULE_MAP.items():
            for mod in modules:
                if mod not in completed:
                    self._data["current_phase"] = phase
                    self._data["current_module"] = mod
                    return
        self._data["current_phase"] = 8
        self._data["current_module"] = 41

    def set_student_name(self, name: str) -> None:
        self._data["student_name"] = name
        self._save()

    def add_study_time(self, minutes: int) -> None:
        self._data["total_study_minutes"] = self._data.get("total_study_minutes", 0) + minutes
        self._save()

    # ── Read operations ───────────────────────────────────────────────────────

    def get_completion_percentage(self) -> float:
        completed = len(self._data["completed_modules"])
        return round((completed / TOTAL_MODULES) * 100, 1)

    def get_current_position(self) -> dict[str, Any]:
        phase = self._data["current_phase"]
        module = self._data["current_module"]
        return {
            "phase": phase,
            "phase_name": PHASE_NAMES.get(phase, f"Phase {phase}"),
            "module": module,
            "overall_progress": self.get_completion_percentage(),
        }

    def get_phase_progress(self) -> list[dict[str, Any]]:
        completed_modules = set(self._data["completed_modules"])
        completed_phases = set(self._data["completed_phases"])
        result = []
        for phase, modules in PHASE_MODULE_MAP.items():
            done = sum(1 for m in modules if m in completed_modules)
            result.append({
                "phase": phase,
                "name": PHASE_NAMES[phase],
                "modules_total": len(modules),
                "modules_done": done,
                "phase_complete": phase in completed_phases,
                "pct": round((done / len(modules)) * 100),
            })
        return result

    def get_assessment_summary(self) -> dict[str, Any]:
        scores = self._data["assessment_scores"]
        if not scores:
            return {"total": 0, "average": 0.0, "pass_rate": 0.0, "by_type": {}}

        by_type: dict[str, list[float]] = {}
        for entry in scores:
            t = entry["assessment_type"]
            by_type.setdefault(t, []).append(entry["score"])

        avg_by_type = {t: round(sum(v) / len(v), 1) for t, v in by_type.items()}
        all_scores = [e["score"] for e in scores]
        passed = sum(1 for e in scores if e.get("passed", False))

        return {
            "total": len(scores),
            "average": round(sum(all_scores) / len(all_scores), 1),
            "pass_rate": round((passed / len(scores)) * 100, 1),
            "by_type": avg_by_type,
        }

    def get_full_profile(
        self, include_scores: bool = True, include_recommendations: bool = True
    ) -> dict[str, Any]:
        position = self.get_current_position()
        phase_progress = self.get_phase_progress()
        assessment = self.get_assessment_summary() if include_scores else {}

        profile: dict[str, Any] = {
            "student_name": self._data.get("student_name", "Student"),
            "started_at": self._data.get("started_at"),
            "last_active": self._data.get("last_active"),
            "session_count": self._data.get("session_count", 1),
            "total_study_minutes": self._data.get("total_study_minutes", 0),
            "current_position": position,
            "phase_progress": phase_progress,
            "completed_modules_count": len(self._data["completed_modules"]),
            "total_modules": TOTAL_MODULES,
            "overall_completion_pct": self.get_completion_percentage(),
        }

        if include_scores:
            profile["assessment_summary"] = assessment
            recent = sorted(
                self._data["assessment_scores"],
                key=lambda x: x.get("timestamp", ""),
                reverse=True,
            )[:5]
            profile["recent_scores"] = recent

        if include_recommendations:
            profile["recommendations"] = self._generate_recommendations()

        return profile

    def _generate_recommendations(self) -> list[str]:
        recommendations = []
        scores = self._data["assessment_scores"]
        position = self.get_current_position()

        if scores:
            recent_avg = sum(e["score"] for e in scores[-3:]) / min(len(scores), 3)
            if recent_avg < 70:
                recommendations.append(
                    f"Your recent average is {recent_avg:.0f}% — consider reviewing the current module before moving on."
                )
            elif recent_avg >= 90:
                recommendations.append(
                    "Excellent scores! You're ready to tackle more advanced exercises in the next module."
                )

        pct = self.get_completion_percentage()
        if pct < 25:
            recommendations.append(
                "You're building the foundation — consistency is key. Aim for at least 30 minutes a day."
            )
        elif pct < 50:
            recommendations.append(
                "Solid progress through the core Java modules. Oracle DB integration is coming up — practice SQL on LiveSQL."
            )
        elif pct < 75:
            recommendations.append(
                "Past the halfway mark! Spring Framework and enterprise patterns will open many career doors."
            )
        else:
            recommendations.append(
                "Almost there! The AI Integration phase sets you apart — finish strong with the Capstone."
            )

        return recommendations

    @property
    def student_name(self) -> str:
        return self._data.get("student_name", "")

    @property
    def current_phase(self) -> int:
        return self._data["current_phase"]

    @property
    def current_module(self) -> int:
        return self._data["current_module"]

    def reset(self) -> None:
        self._data = _default_progress()
        self._save()
