"""ScriptedAgent での多段会話フロー(run_agency 全体)のオフラインテスト。

Port 13 の要点 (a)(c): 実行時にエージェントが相談相手を選び(fake では計画
どおり)、agent-as-tool の再帰呼び出しで応答が呼び出し元の応答に統合される
ことを、通信ログの完全な期待列で固定する。
"""

import json

from conftest import ConsultingAgent, ScriptedAgent, sample_project

from services_agency_maf.agency import Agency
from services_agency_maf.flows import AGENT_KEYS, COMMUNICATION_FLOWS
from services_agency_maf.runner import TAB_TITLES, AgencyReport, run_agency

DEV_REPLY = "Effort: 12 weeks with 2 engineers."
CS_REPLY = "Clients want weekly demos."


def make_agency() -> tuple[Agency, dict[str, object]]:
    """CEO→CTO→Dev の 2 ホップ連鎖+PM の 2 相談を含む 5 役の fake Agency。"""
    agency = Agency()
    fakes = {
        "ceo": ConsultingAgent(
            "ceo", [("cto", "Prepare the technical specification for Project Phoenix.")]
        ),
        "cto": ConsultingAgent("cto", [("developer", "Estimate implementation effort.")]),
        "product_manager": ConsultingAgent(
            "product_manager",
            [("developer", "Which features fit 3-4 months?"), ("client_manager", "Feedback?")],
        ),
        "developer": ScriptedAgent(DEV_REPLY),
        "client_manager": ScriptedAgent(CS_REPLY),
    }
    for key, fake in fakes.items():
        agency.register(key, fake)
        if isinstance(fake, ConsultingAgent):
            fake.bind(agency.talk_tools(key))
    return agency, fakes


async def test_communication_log_records_full_expected_sequence() -> None:
    agency, _ = make_agency()
    await run_agency(agency, sample_project())

    assert [(e.sender, e.recipient, e.depth) for e in agency.log.events] == [
        ("user", "ceo", 0),
        ("ceo", "cto", 1),
        ("cto", "developer", 2),  # 2 ホップ連鎖(CEO のターンの中の CTO の相談)
        ("user", "cto", 0),
        ("cto", "developer", 1),
        ("user", "product_manager", 0),
        ("product_manager", "developer", 1),
        ("product_manager", "client_manager", 1),
        ("user", "developer", 0),
        ("user", "client_manager", 0),
    ]
    assert not any(event.blocked for event in agency.log.events)


async def test_all_agent_pairs_stay_within_graph() -> None:
    agency, _ = make_agency()
    await run_agency(agency, sample_project())
    assert set(agency.log.agent_pairs()) <= set(COMMUNICATION_FLOWS)


async def test_replies_integrate_up_the_call_chain() -> None:
    """agent-as-tool の核: developer の返答が CTO の応答に、CTO の応答が
    CEO の応答に入れ子で統合される。"""
    agency, _ = make_agency()
    report = await run_agency(agency, sample_project())

    ceo_text = report.responses["ceo"]
    assert "cto=" in ceo_text
    assert DEV_REPLY in ceo_text  # 2 ホップ先の返答まで届く
    assert DEV_REPLY in report.responses["cto"]
    assert CS_REPLY in report.responses["product_manager"]


async def test_run_agency_runs_five_turns_in_original_order() -> None:
    agency, _ = make_agency()
    turn_order: list[str] = []
    report = await run_agency(
        agency, sample_project(), on_turn=lambda key, _text: turn_order.append(key)
    )

    assert turn_order == list(AGENT_KEYS)
    assert tuple(report.responses.keys()) == AGENT_KEYS


async def test_entry_prompts_are_faithful_to_original() -> None:
    agency, fakes = make_agency()
    await run_agency(agency, sample_project())

    ceo_prompt = fakes["ceo"].received[0]
    assert "Analyze this project using the AnalyzeProjectRequirements tool:" in ceo_prompt
    assert "Project Name: Project Phoenix" in ceo_prompt
    assert "Use these exact values with the tool" in ceo_prompt

    # CTO は相談(depth1)とトップレベルの 2 回呼ばれる
    cto_top_prompt = fakes["cto"].received[1]
    assert "CreateTechnicalSpecification tool" in cto_top_prompt

    pm_prompt = fakes["product_manager"].received[0]
    assert "Analyze project management aspects:" in pm_prompt
    assert "'name': 'Project Phoenix'" in pm_prompt  # 元どおり str(dict) 埋め込み
    assert "Additional instructions:" in pm_prompt
    assert "product-market fit" in pm_prompt

    dev_top_prompt = fakes["developer"].received[-1]
    assert "based on CTO's specifications" in dev_top_prompt
    assert "costs of cloud services" in dev_top_prompt

    cs_top_prompt = fakes["client_manager"].received[-1]
    assert "client success aspects" in cs_top_prompt
    assert "go-to-market strategy" in cs_top_prompt


async def test_report_serializes_and_renders() -> None:
    agency, _ = make_agency()
    report = await run_agency(agency, sample_project())

    payload = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))
    assert set(payload.keys()) == {"project", "responses", "communications", "state"}
    assert len(payload["communications"]) == 10
    assert payload["project"]["name"] == "Project Phoenix"

    markdown = report.to_markdown()
    for title in TAB_TITLES.values():
        assert f"## {title}" in markdown
    assert "## Communication Log" in markdown
    assert "cto -> developer" in markdown
    assert "## Shared Project State" in markdown


async def test_report_type() -> None:
    agency, _ = make_agency()
    report = await run_agency(agency, sample_project())
    assert isinstance(report, AgencyReport)


async def test_shared_state_visible_across_turns() -> None:
    """CEO ターンで analyze された状態が CTO ターンのツールから見える
    (元 Agency Swarm の shared context)。fake が直接ツールを叩いて再現。"""
    from services_agency_maf.project import project_tools_for

    agency = Agency()

    class CeoWithTool(ScriptedAgent):
        def __init__(self) -> None:
            super().__init__("analysis done")
            (self.analyze,) = project_tools_for("ceo", agency.state)

        async def run(self, message: str):
            self.analyze(
                project_name="Phoenix",
                project_description="d",
                project_type="Web Application",
                budget_range="$25k-$50k",
            )
            return await super().run(message)

    class CtoWithTool(ScriptedAgent):
        def __init__(self) -> None:
            super().__init__("spec done")
            (self.create,) = project_tools_for("cto", agency.state)
            self.tool_results: list[str] = []

        async def run(self, message: str):
            self.tool_results.append(
                self.create(
                    architecture_type="monolithic",
                    core_technologies="python",
                    scalability_requirements="low",
                )
            )
            return await super().run(message)

    cto = CtoWithTool()
    agency.register("ceo", CeoWithTool())
    agency.register("cto", cto)
    for key in ("product_manager", "developer", "client_manager"):
        agency.register(key, ScriptedAgent("ok"))

    report = await run_agency(agency, sample_project())

    assert cto.tool_results == ["Technical specification created for Phoenix."]
    assert report.state["project_analysis"]["name"] == "Phoenix"
    assert report.state["technical_specification"]["architecture"] == "monolithic"
