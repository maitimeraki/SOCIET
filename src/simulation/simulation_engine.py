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
        
        
    def _cluster_opinions(self, opinions:Dict)->List[Dict]:
        """Group similar opinions (simplified - use embeddings in production)"""
        # In production: use sentence embeddings + clustering
        # Here: simple stance-based grouping
        