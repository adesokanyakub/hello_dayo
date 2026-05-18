"""Tool definitions and handlers for the Java Full-Stack Training Agent."""

import json
from typing import Any

TOOLS = [
    {
        "name": "update_student_progress",
        "description": (
            "Record the student's progress: mark a module or phase as complete, "
            "save a quiz/assessment score, or unlock the next module. "
            "Call this whenever the student finishes a lesson, passes an assessment, "
            "or reaches a project milestone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["complete_module", "complete_phase", "save_score", "unlock_next"],
                    "description": "The type of progress update to perform.",
                },
                "phase": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "description": "Phase number (1-8).",
                },
                "module": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 41,
                    "description": "Module number (1-41). Required for module-level actions.",
                },
                "score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Assessment score (0-100). Required for save_score action.",
                },
                "assessment_type": {
                    "type": "string",
                    "enum": ["quiz", "coding_challenge", "project_milestone"],
                    "description": "Type of assessment. Required for save_score action.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about the progress update (e.g., areas to revisit).",
                },
            },
            "required": ["action", "phase"],
        },
    },
    {
        "name": "evaluate_code_submission",
        "description": (
            "Deeply evaluate a student's Java code submission against the current exercise "
            "or project requirements. Checks correctness, code quality, Oracle/Spring best "
            "practices, security, performance, and provides a rubric-based score with "
            "targeted feedback. Use adaptive thinking for thorough analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Java code submitted by the student.",
                },
                "exercise_context": {
                    "type": "string",
                    "description": "Description of the exercise or project requirement the code addresses.",
                },
                "module": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 41,
                    "description": "The module number this submission belongs to.",
                },
                "submission_type": {
                    "type": "string",
                    "enum": ["exercise", "quiz_code", "project_milestone", "capstone"],
                    "description": "Category of submission for appropriate rubric selection.",
                },
                "language_version": {
                    "type": "string",
                    "default": "Java 21",
                    "description": "Target Java version (default: Java 21 LTS).",
                },
            },
            "required": ["code", "exercise_context", "module", "submission_type"],
        },
    },
    {
        "name": "get_student_profile",
        "description": (
            "Retrieve the student's full learning profile: current phase and module, "
            "overall completion percentage, assessment scores, strengths, areas needing "
            "review, and recommended next steps. Use this to personalize lesson delivery "
            "or generate an adaptive study plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_scores": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to include detailed assessment score history.",
                },
                "include_recommendations": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to include AI-generated study recommendations.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "generate_exercise",
        "description": (
            "Generate a fresh, contextually appropriate coding exercise or quiz question "
            "for the student's current module. Exercises are randomised so the student "
            "gets variety on repeat practice. Specify difficulty to scaffold up or down."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 41,
                    "description": "Module number to generate an exercise for.",
                },
                "exercise_type": {
                    "type": "string",
                    "enum": ["coding", "multiple_choice", "fill_in_blank", "debug_this", "design_challenge"],
                    "description": "Format of the exercise.",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced", "challenge"],
                    "description": "Difficulty level. Defaults to matching the student's current progress.",
                },
                "topic_focus": {
                    "type": "string",
                    "description": "Optional specific topic within the module to focus on.",
                },
                "use_oracle_context": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to frame the exercise in an Oracle ecosystem context.",
                },
            },
            "required": ["module", "exercise_type"],
        },
    },
]


def handle_tool_call(tool_name: str, tool_input: dict[str, Any], progress_tracker) -> str:
    """Dispatch tool calls to the appropriate handler and return a JSON string result."""
    handlers = {
        "update_student_progress": _handle_update_progress,
        "evaluate_code_submission": _handle_evaluate_code,
        "get_student_profile": _handle_get_profile,
        "generate_exercise": _handle_generate_exercise,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return handler(tool_input, progress_tracker)


def _handle_update_progress(tool_input: dict[str, Any], progress_tracker) -> str:
    action = tool_input["action"]
    phase = tool_input["phase"]
    module = tool_input.get("module")
    score = tool_input.get("score")
    assessment_type = tool_input.get("assessment_type")
    notes = tool_input.get("notes", "")

    if action == "complete_module" and module:
        progress_tracker.mark_module_complete(phase, module, notes=notes)
        return json.dumps({
            "status": "success",
            "message": f"Module {module} (Phase {phase}) marked complete.",
            "overall_progress": progress_tracker.get_completion_percentage(),
        })

    if action == "complete_phase":
        progress_tracker.mark_phase_complete(phase, notes=notes)
        return json.dumps({
            "status": "success",
            "message": f"Phase {phase} marked complete. Great milestone!",
            "overall_progress": progress_tracker.get_completion_percentage(),
        })

    if action == "save_score" and score is not None and assessment_type:
        progress_tracker.save_assessment_score(
            phase=phase,
            module=module,
            assessment_type=assessment_type,
            score=score,
            notes=notes,
        )
        passed = score >= 70
        return json.dumps({
            "status": "success",
            "message": f"Score {score:.1f}% saved for {assessment_type}.",
            "passed": passed,
            "feedback": "Well done — above the 70% pass threshold!" if passed else "Below 70% — review the material and try again.",
        })

    if action == "unlock_next":
        next_info = progress_tracker.unlock_next(phase, module)
        return json.dumps({"status": "success", **next_info})

    return json.dumps({"status": "error", "message": "Invalid action or missing required parameters."})


def _handle_evaluate_code(tool_input: dict[str, Any], progress_tracker) -> str:
    # The actual LLM-based evaluation happens in agent.py using adaptive thinking.
    # This handler returns a structured prompt that the agent will use as evaluation context.
    code = tool_input["code"]
    context = tool_input["exercise_context"]
    module = tool_input["module"]
    submission_type = tool_input["submission_type"]
    language_version = tool_input.get("language_version", "Java 21")

    loc = len([line for line in code.splitlines() if line.strip()])
    has_oracle_jdbc = "OracleDataSource" in code or "oracle.jdbc" in code
    has_spring = "@SpringBootApplication" in code or "@RestController" in code or "@Service" in code
    has_ai = "LangChain4j" in code or "SpringAI" in code or "AnthropicClient" in code

    return json.dumps({
        "status": "ready_for_evaluation",
        "submission_metadata": {
            "module": module,
            "submission_type": submission_type,
            "language_version": language_version,
            "lines_of_code": loc,
            "detected_frameworks": {
                "oracle_jdbc": has_oracle_jdbc,
                "spring": has_spring,
                "ai_integration": has_ai,
            },
        },
        "exercise_context": context,
        "code_snippet_preview": code[:200] + ("..." if len(code) > 200 else ""),
        "instruction": (
            "Evaluate the full code against the exercise context using the assessment rubric. "
            "Score out of 100 across: correctness (40), code quality (20), "
            "Oracle/Spring best practices (20), security (10), performance (10). "
            "Provide specific line-level feedback and a suggested improvement."
        ),
    })


def _handle_get_profile(tool_input: dict[str, Any], progress_tracker) -> str:
    include_scores = tool_input.get("include_scores", True)
    include_recommendations = tool_input.get("include_recommendations", True)

    profile = progress_tracker.get_full_profile(
        include_scores=include_scores,
        include_recommendations=include_recommendations,
    )
    return json.dumps(profile)


def _handle_generate_exercise(tool_input: dict[str, Any], progress_tracker) -> str:
    module = tool_input["module"]
    exercise_type = tool_input["exercise_type"]
    difficulty = tool_input.get("difficulty", "intermediate")
    topic_focus = tool_input.get("topic_focus", "")
    use_oracle_context = tool_input.get("use_oracle_context", True)

    MODULE_TOPICS = {
        1: "Java Environment Setup & JDK Tools",
        2: "Java Syntax & Data Types",
        3: "Control Flow (if/switch/loops)",
        4: "Methods & Variable Scope",
        5: "Arrays & Basic Algorithms",
        6: "Classes, Objects & Constructors",
        7: "Encapsulation, Inheritance & Polymorphism",
        8: "Abstract Classes & Interfaces",
        9: "Exception Handling",
        10: "Generics & Type Safety",
        11: "Collections Framework (List, Set, Map, Queue)",
        12: "Streams API & Lambda Expressions",
        13: "Java I/O & NIO.2",
        14: "Concurrency & Virtual Threads (Java 21)",
        15: "Java 21 Features (Records, Sealed Classes, Pattern Matching)",
        16: "Oracle DB 23ai Architecture & SQL Foundations",
        17: "PL/SQL Programming",
        18: "Oracle JDBC & Connection Pooling (UCP)",
        19: "JPA & Hibernate with Oracle",
        20: "Spring Data JPA & Repositories",
        21: "Spring Core: IoC, DI & Bean Lifecycle",
        22: "Spring Boot 3 Auto-Configuration",
        23: "Spring MVC & RESTful APIs",
        24: "Spring Security 6 & JWT",
        25: "Testing: JUnit 5, Mockito, Spring Test",
        26: "Web Fundamentals for Java Developers",
        27: "React.js Basics for Backend Developers",
        28: "Oracle APEX Development",
        29: "Full-Stack Integration",
        30: "Microservices & Spring Cloud",
        31: "Oracle Cloud Infrastructure (OCI)",
        32: "Docker, Kubernetes & OKE",
        33: "CI/CD Pipelines",
        34: "Performance Tuning & Observability",
        35: "AI/ML Fundamentals for Java Developers",
        36: "LangChain4j Framework",
        37: "Spring AI",
        38: "Oracle AI Vector Search",
        39: "Claude API Integration in Java",
        40: "Building RAG Applications",
        41: "AI Agents & Multi-Step Workflows",
    }

    topic = MODULE_TOPICS.get(module, f"Module {module}")
    oracle_suffix = " Set the scenario in an Oracle enterprise environment." if use_oracle_context else ""
    focus_suffix = f" Focus specifically on: {topic_focus}." if topic_focus else ""

    return json.dumps({
        "status": "generate",
        "exercise_spec": {
            "module": module,
            "topic": topic,
            "exercise_type": exercise_type,
            "difficulty": difficulty,
            "oracle_context": use_oracle_context,
        },
        "generation_prompt": (
            f"Generate a {difficulty} {exercise_type} exercise for Module {module}: {topic}.{oracle_suffix}{focus_suffix} "
            f"Include: clear problem statement, starter code or options (as appropriate), "
            f"expected output or acceptance criteria, and hints (collapsed/spoiler style). "
            f"Make it practical and realistic — a scenario a Java developer would encounter in production."
        ),
    })
