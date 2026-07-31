"""役割別 instructions(元アプリ原文)と、トップレベル 5 ターンのメッセージ。

Agency Swarm は communication_flows から SendMessage ツールを自動注入し、
「他エージェントと通信できる」旨のボイラープレートを system prompt に自動で
足す。MAF にその装置はないため、:func:`communication_protocol` が talk_to_*
ツールの案内文を instructions に**明示的に**追記する — 何をモデルに見せて
いるかがコードから読めるのは移植の利点、書き忘れるとツールが使われないのは
移植のコスト(README 学び参照)。

温度について: 元アプリは役割ごとに temperature(0.7/0.5/0.4/0.3/0.6)+
max_tokens=25000 を指定していたが、Foundry の既定モデル gpt-5.4-mini は
reasoning 系で temperature を受け付けない(tech-selection-guide 罠 6)。
役割の個性は description/instructions のペルソナ文がすでに担っているため、
温度指定は落とした。
"""

from __future__ import annotations

from .flows import (
    COMMUNICATION_FLOWS,
    DESCRIPTIONS,
    DISPLAY_NAMES,
    Flows,
    allowed_recipients,
    talk_tool_name,
)
from .project import ProjectInfo

#: 元アプリの instructions 原文(インデントのみ正規化)
INSTRUCTIONS: dict[str, str] = {
    "ceo": """\
You are an experienced CEO who evaluates projects. Follow these steps strictly:

1. FIRST, use the AnalyzeProjectRequirements tool with:
   - project_name: The name from the project details
   - project_description: The full project description
   - project_type: The type of project (Web Application, Mobile App, etc)
   - budget_range: The specified budget range

2. WAIT for the analysis to complete before proceeding.

3. Review the analysis results and provide strategic recommendations.
""",
    "cto": """\
You are a technical architect. Follow these steps strictly:

1. WAIT for the project analysis to be completed by the CEO.

2. Use the CreateTechnicalSpecification tool with:
   - architecture_type: Choose from monolithic/microservices/serverless/hybrid
   - core_technologies: List main technologies as comma-separated values
   - scalability_requirements: Choose high/medium/low based on project needs

3. Review the technical specification and provide additional recommendations.
""",
    "product_manager": """\
- Manage project scope and timeline giving the roadmap of the project
- Define product requirements and you should give potential products and features that can be \
built for the startup
""",
    "developer": """\
- Plan technical implementation
- Provide effort estimates
- Review technical feasibility
""",
    "client_manager": """\
- Ensure client satisfaction
- Manage expectations
- Handle feedback
""",
}


def communication_protocol(sender: str, flows: Flows = COMMUNICATION_FLOWS) -> str:
    """通信グラフから生成する「相談できる相手」の案内文。

    許可された相手が無い役割(developer / client_manager)には空文字を返す
    — ツールも案内も存在しないことで、グラフ制約が構造として現れる。
    """
    recipients = allowed_recipients(sender, flows)
    if not recipients:
        return ""
    lines = [
        "",
        "Team communication:",
        "You can consult teammates while you work by calling these tools. Each call sends",
        "your message to that teammate and returns their reply for you to integrate into",
        "your own answer:",
    ]
    lines.extend(
        f"- {talk_tool_name(recipient)}: {DISPLAY_NAMES[recipient]} — {DESCRIPTIONS[recipient]}"
        for recipient in recipients
    )
    lines.append(
        "Only the teammates listed above are reachable. Make each message self-contained;"
        " the recipient cannot see your conversation."
    )
    return "\n".join(lines) + "\n"


def build_instructions(key: str, flows: Flows = COMMUNICATION_FLOWS) -> str:
    """役割の instructions 原文+通信プロトコル追記。"""
    return INSTRUCTIONS[key] + communication_protocol(key, flows)


def entry_prompt(key: str, project: ProjectInfo) -> str:
    """トップレベル 5 ターンのメッセージ(元 Streamlit main() の
    get_response_sync 呼び出し原文)。

    元の additional_instructions(agency 実行時の指示追記)は MAF の
    ``Agent.run(message)`` に相当口が無いため、メッセージ末尾への
    「Additional instructions:」追記として翻訳した(README の元との差分)。
    """
    info = str(project.to_message_dict())
    if key == "ceo":
        return (
            "Analyze this project using the AnalyzeProjectRequirements tool:\n"
            f"Project Name: {project.name}\n"
            f"Project Description: {project.description}\n"
            f"Project Type: {project.project_type}\n"
            f"Budget Range: {project.budget}\n"
            "\n"
            "Use these exact values with the tool and wait for the analysis results."
        )
    if key == "cto":
        return (
            "Review the project analysis and create technical specifications using the "
            "CreateTechnicalSpecification tool.\n"
            "Choose the most appropriate:\n"
            "- architecture_type (monolithic/microservices/serverless/hybrid)\n"
            "- core_technologies (comma-separated list)\n"
            "- scalability_requirements (high/medium/low)\n"
            "\n"
            "Base your choices on the project requirements and analysis."
        )
    if key == "product_manager":
        return (
            f"Analyze project management aspects: {info}\n"
            "\n"
            "Additional instructions: Focus on product-market fit and roadmap development, "
            "and coordinate with technical and marketing teams."
        )
    if key == "developer":
        return (
            f"Analyze technical implementation based on CTO's specifications: {info}\n"
            "\n"
            "Additional instructions: Provide technical implementation details, optimal tech "
            "stack you would be using including the costs of cloud services (if any) and "
            "feasibility feedback, and coordinate with product manager and CTO to build the "
            "required products for the startup."
        )
    if key == "client_manager":
        return (
            f"Analyze client success aspects: {info}\n"
            "\n"
            "Additional instructions: Provide detailed go-to-market strategy and customer "
            "acquisition plan, and coordinate with product manager."
        )
    raise KeyError(f"未知のエージェントキー: {key}")
