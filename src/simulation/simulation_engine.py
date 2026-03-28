import asyncio
from typing import List, Dict, Callable
import json
import uuid
from .world_state import SharedWorldState, MessageBus
from ..agents.Agent import Agent
from ..agents.config_agents import PersonalityType, Belief, AgentMemory
from ..simulation.config_world import WorldEvent


class SimulationSociety:
    """
    Manages the lifecycle: Setup → Debate Rounds → Consensus → Output
    """
    
    def __init__(self,world_state:SharedWorldState, message_bus: MessageBus,max_rounds:int =10, consensus_threshold:float=0.7):
        self.world_state = world_state
        self.message_bus = message_bus
        self.agents: List[Agent] = []
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold
        
        
    def recruit_agents(self, agent_configs:List[Dict], llm_backend:Callable):
        """Spawn agents with specific roles"""
        for config in agent_configs:
            agent = Agent(
                agent_id=str(uuid.uuid4()),
                name=config['name'],
                domain_expertise=config['domain_expertise'],
                personality=[PersonalityType(p) for p in config['personality']],
                llm_backend=llm_backend,
                initial_beliefs=[Belief(**b) for b in config.get('initial_beliefs', [])]
            )
            self.agents.append(agent)
            self.message_bus.register(agent.agent_id)
            
            
    async def run_simulation(self, topic:str) -> Dict:
        """
        Main execution loop
        """
        print(f"🌍 Starting simulation on: {topic}")
        print(f"👥 Society size: {len(self.agents)} agents")
        # Phase 1: Initial Perception (agents observe world)
        print("\n--- Phase 1: Perception ---")
        initial_beliefs = {}
        for agent in self.agents:
            visible_world= self.world_state.get_observable_state(agent.domain_expertise)
            beliefs = agent.perceive(visible_world)
            initial_beliefs[agent.agent_id] = beliefs
            print(f"{agent.name} perceives: {len(beliefs)} beliefs")
            
        # Phase 2: Debate Rounds
        print("\n--- Phase 2: Debate Rounds ---")
        round_opinions = []
        for round_num in range(self.max_rounds):
            print(f"\n  Round {round_num + 1}/{self.max_rounds}")
            round_opinion_map = {}
            for agent in self.agents:
                # Get messages from other agents
                messages = await self.message_bus.get_messages(agent.agent_id, timeout=0.5)
                other_opinions = [m['content'] for m in messages if m['type']=='opinion']
                # Each agent forms an opinion based on beliefs and received messages
                opinion = agent.deliberate(topic, other_opinions)
                round_opinion_map[agent.agent_id] = opinion
                # Broadcast opinion to others
                await self.message_bus.broadcast(agent.agent_id, opinion, msg_type="opinion")
                
                # Handle potential coalitions based on opinions and trust
                if round_num > 0:
                    await self._handle_coalitions(agent, other_opinions)
                
            round_opinions.append(round_opinion_map)
            
            # Check for consensus (simplified: if 80% agree on the same stance)
            consensus_score = self._calculate_consensus(round_opinion_map)
            print(f"  Consensus score: {consensus_score:.2f}")
            
            
            if consensus_score >= self.consensus_threshold:
                print(f"    ✓ Early convergence achieved")
                break
        # Phase 3: Synthesis
        print("\n--- Phase 3: Synthesis ---")
        final_opinion = self._synthesize_society_opinion(round_opinions, topic)
        
        return final_opinion
            
   
    async def _handle_coalitions(self, agent:Agent, other_opinions: List[Dict]):
        """Agents with similar views might form private coalitions"""
        for opinion in other_opinions:
            other_id = opinion['agent_id']
            # High trust + agreement = potential coalition
            trust = agent.memory.relationships.get(other_id, 0.5)
            if trust > 0.7 and opinion['stance'] == 'agree':
                # Private message to ally
                await self.message_bus.direct_message(
                    agent.agent_id, 
                    other_id,
                    {"type": "coalition_probe", "topic": "alignment_check"}
                )
        
    def _calculate_consensus(self, opinions:Dict[str,Dict])->float:
        """
        Measure agreement - not just voting, but reasoning similarity
        """
        if len(opinions) < 0:
            return 0.0
        stances = [o['stances'] for o in opinions.values()]
        confidences = [o['confidence'] for o in opinions.values()]
        # Simple consensus metric: % agreement on stance weighted by confidence
        stances_counts = {}
        for stance, conf in zip(stances,confidences):
            stances_counts[stance] = stances_counts.get(stance, 0) + conf
            
        max_agreement = max(stances_counts.values()) if stances_counts else 0
        total_confidence = sum(confidences)
        return max_agreement / total_confidence if total_confidence > 0 else 0.0
    
    
    def _synthesize_society_opinion(self, all_rounds:List[Dict], topic:str)->Dict:
        """
        Generate the final output - NOT a summary, but a synthesized opinion
        """
        final_round = all_rounds[-1]
        # Identify opinion clusters
        clusters = self._cluster_opinions(final_round)
        # Weight by expertise relevance to topic
        weighted_clusters = self._weight_by_relevance(clusters, topic)
        # Construct meta-opinion 
        majority_view = max(weighted_clusters, key = lambda x :x['weight'])
        minority_view = [c for c in weighted_clusters if c != majority_view]
        
        # Confidence calibration
        overall_confidence = self._calibrate_confidence(majority_view, minority_view, len(all_rounds))
        
        return {
            "society_opinion": {
                "assessment": majority_view['synthesized_reasoning'],
                "confidence": overall_confidence,
                "key_drivers": majority_view['key_arguments'],
                "risks_identified": self._extract_risks(final_round),
                "opportunities_identified": self._extract_opportunities(final_round),
            },
            "dissent": {
                "alternative_views": [
                    {
                        "view": m['synthesized_reasoning'],
                        "support": m['weight'],
                        "why_different": m.get('different_assumptions', [])
                    }
                    for m in minority_view[:2]  # Top 2 dissenting views
                ],
                "uncertainty_areas": self._identify_gaps(final_round)
            },
            "meta": {
                "rounds_to_convergence": len(all_rounds),
                "agent_participation": len(final_round),
                "debate_intensity": self._measure_debate_intensity(all_rounds),
                "knowledge_gaps": self._find_knowledge_gaps(final_round, topic)
            },
            "recommendations": self._generate_recommendations(majority_view, minority_view)
        }
        
        
    def _cluster_opinions(self, opinions:Dict)->List[Dict]:
        """Group similar opinions (simplified - use embeddings in production)"""
        # In production: use sentence embeddings + clustering
        # Here: simple stance-based grouping
        groups = {}
        for agent_id, op in opinions.items():
            key = op['stance'] + str(sorted(op.get('key_arguments', [])))
            if key not in groups:
                groups[key] = []
            groups[key].append((agent_id, op))
            
        return [{
            'weight': sum(o['confidence'] for o in group),
            'opinions': group,
            'synthesized_reasoning': self._merge_reasoning(group),
            'key_arguments': list(set(arg for o in group for arg in o.get('key_arguments', [])))
            
        } for group in groups.values()]
        
        
    def _merge_reasoning(self, opinions: List[Dict])-> str:
        """Synthesize multiple reasonings into coherent narrative"""
        # In production: use LLM to synthesize
        # Here: concatenation with markers
        themes = {}
        for op in opinions:
            for arg in op.get('key_arguments', []):
                themes[arg] = themes.get(arg, 0) + op['confidence']
        # Sort themes by weight
        sorted_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]
        return f"Society converges on: {', '.join([arg for arg, _ in sorted_themes])}"
    
    def _weight_by_relevance(self, clusters:List[Dict], topic:str)->List[Dict]:
        """Weight opinion clusters by relevance of agent expertise to topic"""
        # In production: use LLM to assess relevance
        # Here: simple keyword matching
        for cluster in clusters:
            relevance_score = 0
            for agent_id, op in cluster['opinions']:
                agent = next((a for a in self.agents if a.agent_id == agent_id), None)
                if agent:
                    expertise_match = any(domain in topic for domain in agent.domain_expertise)
                    relevance_score += expertise_match * op['confidence']
            cluster['weight'] *= (1 + relevance_score)  # Boost weight by relevance
        return clusters
    
    def _calibrate_confidence(self, majority: Dict, minorities: List[Dict], rounds: int) -> float:
        """Lower confidence if strong dissent or quick convergence (groupthink risk)"""
        base_conf = majority['weight'] / sum(m['weight'] for m in [majority] + minorities)
        
        # Penalty for quick convergence (might be echo chamber)
        if rounds < 3:
            base_conf *= 0.8
            
        # Penalty for strong dissent
        if minorities and max(m['weight'] for m in minorities) > majority['weight'] * 0.5:
            base_conf *= 0.85
            
        return round(base_conf, 2)
    
    def _extract_risks(self, opinions:Dict)->List[str]:
        """Aggregate risks identified during the simulation"""
        all_risks = []
        for op in opinions.values():
            all_risks.extend(op.get('concerns', []))
            
        # Deduplicate and rank by frequency
        from collections import Counter
        return [risk for risk, _ in Counter(all_risks).most_common(5)]
    
    
    def _extract_opportunities(self, opinions:Dict)->List[str]:
        """Aggregate opportunities identified during the simulation"""
        all_opps = []
        for op in opinions.values():
            all_opps.extend(op.get('opportunities', []))
            
        # Deduplicate and rank by frequency
        from collections import Counter
        return [opp for opp, _ in Counter(all_opps).most_common(5)]
    
    def _identify_gaps(self, opinions:Dict)->List[str]:
        """Identify areas of high uncertainty or disagreement"""
        gaps = []
        for op in opinions.values():
            if op['confidence'] < 0.5:
                gaps.append(f"Low confidence in {op.get('agent_name')}'s assessment")
        return gaps
    
    def _measure_debate_intensity(self, rounds: List[Dict]) -> str:
        """How much disagreement there was"""
        stance_changes = 0
        for i in range(1, len(rounds)):
            prev_stances = set(o['stance'] for o in rounds[i-1].values())
            curr_stances = set(o['stance'] for o in rounds[i].values())
            if prev_stances != curr_stances:
                stance_changes += 1
                
        if stance_changes > len(rounds) * 0.7:
            return "high (significant disagreement)"
        elif stance_changes > len(rounds) * 0.3:
            return "moderate (some convergence)"
        return "low (early consensus)"
    
    def _find_knowledge_gaps(self, opinions: Dict, topic: str) -> List[str]:
        """What expertise was missing"""
        covered_domains = set()
        for op in opinions.values():
            covered_domains.update(op.get('expertise', []))
            
        # Infer needed domains from topic (simplified)
        needed = set()
        if 'market' in topic or 'finance' in topic:
            needed.add('finance')
        if 'tech' in topic or 'AI' in topic:
            needed.add('technology')
            
        return list(needed - covered_domains)
    
    def _generate_recommendations(self, majority: Dict, minorities: List[Dict]) -> List[Dict]:
        """Actionable output based on society opinion"""
        recs = []
        
        # Primary recommendation
        recs.append({
            "action": f"Proceed with caution: {majority['synthesized_reasoning'][:100]}...",
            "confidence": "high" if majority['weight'] > 0.7 else "moderate",
            "contingencies": [f"Watch for: {r}" for r in self._extract_risks({})[:3]]
        })
        
        # Alternative paths from dissent
        for minority in minorities[:1]:
            recs.append({
                "action": f"Alternative: {minority['synthesized_reasoning'][:100]}...",
                "confidence": "speculative",
                "trigger": "If majority assumptions prove false"
            })
            
        return recs