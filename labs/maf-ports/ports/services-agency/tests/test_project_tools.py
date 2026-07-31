"""役割固有ツール(analyze_project / create_technical_spec)と共有状態の
オフラインテスト。元 BaseTool 2 つの shared context 意味論を固定する。"""

from services_agency_maf.project import (
    ProjectState,
    make_analyze_project_tool,
    make_create_technical_spec_tool,
    project_tools_for,
)


def test_analyze_stores_canned_analysis() -> None:
    state = ProjectState()
    analyze = make_analyze_project_tool(state)
    result = analyze(
        project_name="Project Phoenix",
        project_description="AI note sharing SaaS",
        project_type="Web Application",
        budget_range="$25k-$50k",
    )

    assert result == "Project analysis completed. Please proceed with technical specification."
    assert state.analysis == {
        "name": "Project Phoenix",
        "type": "Web Application",
        "complexity": "high",
        "timeline": "6 months",
        "budget_feasibility": "within range",
        "requirements": ["Scalable architecture", "Security", "API integration"],
    }


def test_analyze_preserves_original_quirk_description_not_stored() -> None:
    """元実装のコードレビュー所見: description / budget_range は保存されない
    (canned 分析)。挙動互換のため保存する。"""
    state = ProjectState()
    make_analyze_project_tool(state)(
        project_name="X",
        project_description="This text goes nowhere",
        project_type="Other",
        budget_range="$100k+",
    )
    assert "This text goes nowhere" not in str(state.analysis)
    assert "$100k+" not in str(state.analysis)


def test_analyze_twice_returns_error_and_keeps_first() -> None:
    state = ProjectState()
    analyze = make_analyze_project_tool(state)
    analyze(
        project_name="First",
        project_description="d",
        project_type="Other",
        budget_range="$10k-$25k",
    )
    result = analyze(
        project_name="Second",
        project_description="d",
        project_type="Other",
        budget_range="$10k-$25k",
    )

    assert result.startswith("Error:")
    assert "already exists" in result
    assert state.analysis is not None and state.analysis["name"] == "First"


def test_create_spec_before_analysis_returns_error() -> None:
    state = ProjectState()
    create = make_create_technical_spec_tool(state)
    result = create(
        architecture_type="microservices",
        core_technologies="python,react",
        scalability_requirements="high",
    )

    assert result.startswith("Error:")
    assert "analyze project requirements first" in result
    assert state.technical_specification is None


def test_create_spec_after_analysis_stores_spec() -> None:
    state = ProjectState()
    make_analyze_project_tool(state)(
        project_name="Phoenix",
        project_description="d",
        project_type="Web Application",
        budget_range="$25k-$50k",
    )
    result = make_create_technical_spec_tool(state)(
        architecture_type="serverless",
        core_technologies="python, fastapi ,react",
        scalability_requirements="medium",
    )

    assert result == "Technical specification created for Phoenix."
    assert state.technical_specification == {
        "project_name": "Phoenix",
        "architecture": "serverless",
        # 元実装どおり素の split(",")(strip しない癖も保存)
        "technologies": ["python", " fastapi ", "react"],
        "scalability": "medium",
    }


def test_state_to_dict_uses_original_context_keys() -> None:
    state = ProjectState()
    assert state.to_dict() == {
        "project_analysis": None,
        "technical_specification": None,
    }


def test_project_tools_assignment_matches_original() -> None:
    """ツールを持つのは CEO(analyze)と CTO(create spec)だけ。"""
    state = ProjectState()
    assert [t.__name__ for t in project_tools_for("ceo", state)] == ["analyze_project"]
    assert [t.__name__ for t in project_tools_for("cto", state)] == ["create_technical_spec"]
    for key in ("product_manager", "developer", "client_manager"):
        assert project_tools_for(key, state) == []
