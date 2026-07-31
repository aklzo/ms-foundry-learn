"""プロジェクト入力(元 Streamlit フォーム)と共有状態+役割固有ツール。

元アプリの BaseTool 2 つに対応する:

- ``AnalyzeProjectRequirements``(ToolConfig.name = analyze_project、CEO 専用)
- ``CreateTechnicalSpecification``(ToolConfig.name = create_technical_spec、CTO 専用)

どちらも Agency Swarm の **shared context**(``self.context``)を介して
「CEO の分析 → CTO の仕様」の順序を強制していた。移植では
:class:`ProjectState` をクロージャで束縛した関数ツールに置き換える
(research-handoff の FactStore と同じ型)。

挙動互換の注意 2 点(移植はコードレビュー):

1. 元の analyze は **project_description / budget_range を保存しない**うえ、
   分析結果は完全に canned(complexity=high / timeline=6 months / ...)。
   「分析ツール」は実際には共有状態に印を付けるだけの順序制御装置だった。
   挙動互換を優先しそのまま保存する。
2. 元は順序違反で ``ValueError`` を **raise** し、Agency Swarm がその文言を
   モデルに返していた。MAF はツール例外を "Error: Function failed." に丸める
   (include_detailed_errors 既定 False)ため、移植では **raise せず同じ文言を
   return** してモデルに見える情報量を揃える。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

# 元 Streamlit フォームの選択肢(analyze_project の Literal と共有)
PROJECT_TYPES = (
    "Web Application",
    "Mobile App",
    "API Development",
    "Data Analytics",
    "AI/ML Solution",
    "Other",
)
BUDGET_RANGES = ("$10k-$25k", "$25k-$50k", "$50k-$100k", "$100k+")
TIMELINES = ("1-2 months", "3-4 months", "5-6 months", "6+ months")
PRIORITIES = ("High", "Medium", "Low")

ProjectType = Literal[
    "Web Application", "Mobile App", "API Development", "Data Analytics", "AI/ML Solution", "Other"
]
BudgetRange = Literal["$10k-$25k", "$25k-$50k", "$50k-$100k", "$100k+"]
ArchitectureType = Literal["monolithic", "microservices", "serverless", "hybrid"]
ScalabilityRequirement = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ProjectInfo:
    """元 Streamlit フォームの 8 項目。"""

    name: str
    description: str
    project_type: str = "Web Application"
    timeline: str = "3-4 months"
    budget: str = "$25k-$50k"
    priority: str = "High"
    technical_requirements: str = ""
    special_considerations: str = ""

    def to_message_dict(self) -> dict[str, str]:
        """元アプリの project_info dict(キー名・順序も原文どおり)。
        トップレベルのメッセージには元同様 ``str()`` した形で埋め込む。"""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.project_type,
            "timeline": self.timeline,
            "budget": self.budget,
            "priority": self.priority,
            "technical_requirements": self.technical_requirements,
            "special_considerations": self.special_considerations,
        }


@dataclass
class ProjectState:
    """Agency 全体で共有する状態(元 Agency Swarm の shared context 相当)。

    トップレベル 5 ターンと入れ子の会話すべてから同じインスタンスが見える。
    """

    analysis: dict[str, Any] | None = None
    technical_specification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        # キー名は元アプリの context キー(project_analysis / technical_specification)
        return {
            "project_analysis": self.analysis,
            "technical_specification": self.technical_specification,
        }


def make_analyze_project_tool(state: ProjectState) -> Callable[..., str]:
    """CEO 専用: 元 AnalyzeProjectRequirements(canned 分析+順序制御)。"""

    def analyze_project(
        project_name: str,
        project_description: str,
        project_type: ProjectType,
        budget_range: BudgetRange,
    ) -> str:
        """Analyzes project requirements and feasibility.

        Args:
            project_name: Name of the project.
            project_description: Project description and goals.
            project_type: Type of project.
            budget_range: Budget range for the project.
        """
        if state.analysis is not None:
            # 元: raise ValueError(同文言)。モジュール docstring の注意 2 参照。
            return (
                "Error: Project analysis already exists. "
                "Please proceed with technical specification."
            )
        # 元実装どおりの canned 分析(project_description / budget_range は未保存)
        state.analysis = {
            "name": project_name,
            "type": project_type,
            "complexity": "high",
            "timeline": "6 months",
            "budget_feasibility": "within range",
            "requirements": ["Scalable architecture", "Security", "API integration"],
        }
        return "Project analysis completed. Please proceed with technical specification."

    return analyze_project


def make_create_technical_spec_tool(state: ProjectState) -> Callable[..., str]:
    """CTO 専用: 元 CreateTechnicalSpecification(分析必須の順序制御付き)。"""

    def create_technical_spec(
        architecture_type: ArchitectureType,
        core_technologies: str,
        scalability_requirements: ScalabilityRequirement,
    ) -> str:
        """Creates technical specifications based on project analysis.

        Args:
            architecture_type: Proposed architecture type.
            core_technologies: Comma-separated list of main technologies and frameworks.
            scalability_requirements: Scalability needs.
        """
        if state.analysis is None:
            # 元: raise ValueError(同文言)
            return (
                "Error: Please analyze project requirements first "
                "using AnalyzeProjectRequirements tool."
            )
        state.technical_specification = {
            "project_name": state.analysis["name"],
            "architecture": architecture_type,
            "technologies": core_technologies.split(","),
            "scalability": scalability_requirements,
        }
        return f"Technical specification created for {state.analysis['name']}."

    return create_technical_spec


def project_tools_for(key: str, state: ProjectState) -> list[Callable[..., str]]:
    """役割固有ツール(元アプリで tools= を持つのは CEO と CTO だけ)。"""
    if key == "ceo":
        return [make_analyze_project_tool(state)]
    if key == "cto":
        return [make_create_technical_spec_tool(state)]
    return []
