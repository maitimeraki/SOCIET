import json
import uuid
from typing import List, Callable, Optional, Dict
from .config_agents import PersonalityType, Belief, AgentMemory


class Agent:
    """
    An agent with persistent identity, beliefs, and social relationships
    """
    def __init__(self, agent_id:str,
    name:str, 
    domain_expertise:List[str], # e.g., ["finance", "tech", "regulation"]
    personality:List[PersonalityType],
    llm_backend:Callable, # Function to call LLM (GPT-4, Claude, etc.)
    initial_beliefs:Optional[List[Belief]]=None
    ):
        self.agent_id = agent_id
        self.name = name
        self.domain_expertise = domain_expertise
        self.personality = personality
        self.llm_backend = llm_backend
        self.memory = AgentMemory()
        # Load initial beliefs into long-term memory
        if initial_beliefs:
            for belief in initial_beliefs:
                self.memory.long_term[belief.statement] = belief
                
        # Current imotional State (for simplicity, a single value from -1 to 1)
        self.mood = "neutral"  # excited, worried, curious, stubborn
        
        
    def perceive(self, world_state:Dict)->List[Belief]:
        """
        Agent observes world state and forms beliefs
        Not just raw data - interpretation through personality lens
        """
        bias = self._get_perception_bias()
        prompt = f"""
        You are {self.name}, a specialist in {', '.join(self.domain_expertise)}.
        Your personality traits: {[p.value for p in self.personality]}.
        Current mood: {self.mood}.
        
        Perception bias: {bias}
        
        Observe this world state and form 2-3 beliefs about what it means.
        For each belief, provide confidence (0.0-1.0) and reasoning.
        
        World State: {json.dumps(world_state, indent=2)}
        
        Format: JSON list of {{statement, confidence, reasoning}}
        """
        
        response = self.llm_backend(prompt)
        new_beliefs = self._parse_beliefs(response)
        
        # Store new beliefs in long-term memory
        for belief in new_beliefs:
            key = f"{self.agent_id}_{belief.statement[:50]}"
            self.memory.long_term[key] = belief
            
        return new_beliefs
        
        
    def deliberate(self, topic:str, other_opinions:List[Dict])->Dict:
        """
        Form an opinion on a topic, considering what others think
        This is where the "society" aspect emerges
        """
        # Check relationships with agents who have spoken
        trust_map={}
        for opinion in other_opinions:
            agent_id= opinion['agent_id']
            trust_map[agent_id] = self.memory.relationships.get(agent_id, 0.5)  # Default neutral trust
            
        # Personality affects how we process others' views
        receptiveness = self._calculate_receptiveness(other_opinions, trust_map)
        
        prompt = f"""
        You are {self.name}. Topic: {topic}
        
        Your core beliefs: {[b.statement for b in self.memory.long_term.values()]}
        Your personality: {[p.value for p in self.personality]}
        
        Other agents' opinions: {json.dumps(other_opinions)}
        Your trust in each: {trust_map}
        Your receptiveness today: {receptiveness}
        
        Form your opinion. You may:
        - Agree but add nuance
        - Disagree with specific counter-arguments  
        - Synthesize a new perspective
        - Ask a challenging question
        
        Return: {{
            "stance": "agree|disagree|synthesize|question",
            "opinion": "your detailed reasoning",
            "confidence": 0.0-1.0,
            "key_arguments": ["arg1", "arg2"],
            "concerns": ["risk1", "risk2"]  # if pessimist/skeptic
            "opportunities": ["opp1", "opp2"]  # if optimist/innovator
        }}
        """
        
        response = self.llm_backend(prompt)
        opinion = json.loads(response)
        # Update mood based on content (emotional contagion)
        self._update_mood(opinion)
        
        return {
            **opinion,
            "agent_id": self.agent_id,
            "agent_name": self.name,
            "expertise": self.domain_expertise
        }
            
            
    def _parse_beliefs(self, llm_response:str)->List[Belief]:
        """Convert LLM output into structured beliefs"""
        try:
            belief_dicts = json.loads(llm_response)
            beliefs = []
            for b in belief_dicts:
                belief = Belief(
                    statement=b['statement'],
                    confidence=b['confidence'],
                    evidence=[b.get('reasoning', '')]
                )
                beliefs.append(belief)
            return beliefs
        except Exception as e:
            print(f"Error parsing beliefs: {e}")
            return []
        
        
    def _get_perception_bias(self)->str:
        """How personality affects observation"""
        if PersonalityType.OPTIMIST in self.personality:
            return "focus on opportunities, growth potential, and positive outcomes"
        elif PersonalityType.PESSIMIST in self.personality:
            return "focus on risks, threats, negative signals, and failures"
        elif PersonalityType.SKEPTIC in self.personality:
            return "challenge assumptions and look for contradictions"
        # elif PersonalityType.INNOVATOR in self.personality:
        #     return "look for novel combinations and unconventional insights"
        # elif PersonalityType.CONSERVATIVE in self.personality:
        #     return "favor status quo and established patterns"
        else:
            return "neutral perspective"
        
        
    def _calculate_receptiveness(self, opinion:List[Dict], trust_map:Dict)-> str:
        """How open to influence based on personality and trust"""
        avg_trust = sum(trust_map.values()) / len(trust_map) if trust_map else 0.5
        if PersonalityType.CONSERVATIVE in self.personality:
            return f"Low (conservative): {avg_trust * 0.5}"
        elif PersonalityType.INNOVATOR in self.personality:
            return f"High (open to new ideas): {min(1.0, avg_trust * 1.3)}"
        return f"Moderate: {avg_trust}"
    
    
    def _update_mood(self, opinion:Dict):
        """Emotional state affects future reasoning"""
        if opinion.get('concerns') and len(opinion['concerns'])>2:
            self.mood = "worried"
        elif opinion.get('opportunities') and len(opinion['opportunities'])>2:
            self.mood = "excited"
        elif opinion.get('stance')=='disagree':
            self.mood = 'challenging'
        else:
            self.mood = "neutral"