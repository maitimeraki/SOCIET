"""Integration tests: round → VerdictSynthesizer → SocietyMemory commit flow."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.simulation.verdict import VerdictSynthesizer
from src.simulation.society_memory import SocietyMemory
from src.simulation.pair_turn import RoundResult, AgentTurn, CommPair
from src.persona.agent import Stance


def _make_turn(agent_id: str, agent_name: str, content: str, stance: str, confidence: float) -> AgentTurn:
    return AgentTurn(
        agent_id=agent_id,
        agent_name=agent_name,
        content=content,
        stance=stance,
        confidence=confidence,
        references=["EntityA", "EntityB"],
    )


def _make_pair(a_name: str, b_name: str) -> CommPair:
    return CommPair(agent_a=a_name, agent_b=b_name)


class TestVerdictSynthesizerFromRound:
    """test_verdict_synthesizer_from_round — fixture round of 5 turns flows through VerdictSynthesizer."""

    def test_produces_debate_verdict_with_cluster_details(self):
        # 5 turns: 3 POSITIVE, 2 NEGATIVE
        turns = [
            _make_turn("a1", "Alice", "AI will help humanity", "POSITIVE", 0.9),
            _make_turn("a2", "Bob", "AI poses real risks", "NEGATIVE", 0.8),
            _make_turn("a3", "Carol", "I support AI development", "POSITIVE", 0.85),
            _make_turn("a4", "Dave", "We should be cautious about AI", "NEGATIVE", 0.75),
            _make_turn("a5", "Eve", "AI has great potential", "POSITIVE", 0.9),
        ]
        pairs = [
            _make_pair("Alice", "Bob"),
            _make_pair("Carol", "Dave"),
        ]
        round_result = RoundResult(round_num=1, turns=turns, pairs=pairs)

        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(rounds=[round_result], profiles=[])

        assert verdict.overall_stance is not None
        assert isinstance(verdict.overall_stance, Stance)
        assert 0.0 <= verdict.confidence_score <= 1.0
        assert len(verdict.cluster_details) > 0

        # POSITIVE cluster should dominate (3 turns vs 2)
        assert Stance.POSITIVE in verdict.cluster_details
        assert verdict.cluster_details[Stance.POSITIVE].count == 3

        # NEGATIVE cluster should exist
        assert Stance.NEGATIVE in verdict.cluster_details
        assert verdict.cluster_details[Stance.NEGATIVE].count == 2

        assert verdict.rounds_executed == 1
        assert verdict.summary != ""

    def test_empty_rounds_returns_neutral_verdict(self):
        synthesizer = VerdictSynthesizer()
        verdict = synthesizer.synthesize(rounds=[], profiles=[])

        assert verdict.overall_stance == Stance.NEUTRAL
        assert verdict.confidence_score == 0.0
        assert verdict.cluster_details == {}


class TestSocietyMemoryCommitsRound:
    """test_society_memory_commits_round — mocked driver verifies the round lands in the graph."""

    @staticmethod
    def _mock_graph():
        mock_tx = AsyncMock()
        mock_session = AsyncMock()
        mock_session.begin_transaction = AsyncMock(return_value=mock_tx)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_driver = MagicMock()
        mock_driver.session = MagicMock(return_value=mock_session)
        return mock_driver, mock_session, mock_tx

    @pytest.mark.asyncio
    async def test_commit_round_writes_opinions_and_reactions(self):
        mock_driver, mock_session, mock_tx = self._mock_graph()

        turns = [
            _make_turn("a1", "Alice", "AI is great", "POSITIVE", 0.9),
            _make_turn("a2", "Bob", "AI is risky", "NEGATIVE", 0.8),
        ]
        pairs = [_make_pair("Alice", "Bob")]
        round_result = RoundResult(round_num=1, turns=turns, pairs=pairs)

        service = SocietyMemory(mock_driver, "neo4j")
        receipt = await service.commit_round(
            round_result=round_result,
            dataset_id="test-ds-42",
            query_hash="qh42",
            profile_map={},
        )

        # session() called with the configured database name
        mock_driver.session.assert_called_once_with(database="neo4j")

        # opinions written inside the round's transaction, scoped to the dataset
        opinion_kwargs = mock_tx.run.call_args_list[0].kwargs
        assert opinion_kwargs["dataset_id"] == "test-ds-42"
        assert opinion_kwargs["query_hash"] == "qh42"
        assert len(opinion_kwargs["opinions"]) == 2

        # one opinion per speaker, one reaction edge per direction
        assert receipt["failed"] is False
        assert receipt["opinions"] == 2
        assert receipt["edges"] == 2
        mock_tx.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_multiple_rounds_writes_once_per_round(self):
        mock_driver, mock_session, mock_tx = self._mock_graph()

        round1 = RoundResult(
            round_num=1,
            turns=[
                _make_turn("a1", "Alice", "AI helps", "POSITIVE", 0.9),
                _make_turn("a2", "Bob", "AI helps too", "POSITIVE", 0.8),
            ],
            pairs=[_make_pair("Alice", "Bob")],
        )
        round2 = RoundResult(
            round_num=2,
            turns=[
                _make_turn("a1", "Alice", "AI still helps", "POSITIVE", 0.85),
                _make_turn("a2", "Bob", "AI now seems harmful", "NEGATIVE", 0.7),
            ],
            pairs=[_make_pair("Alice", "Bob")],
        )

        service = SocietyMemory(mock_driver, "neo4j")
        receipt1 = await service.commit_round(
            round_result=round1, dataset_id="multi-round",
            query_hash="qh", profile_map={},
        )
        receipt2 = await service.commit_round(
            round_result=round2, dataset_id="multi-round",
            query_hash="qh", profile_map={},
        )

        # one session (and one committed transaction) per round
        assert mock_driver.session.call_count == 2
        assert mock_tx.commit.await_count == 2
        assert (receipt1["round"], receipt2["round"]) == (1, 2)
