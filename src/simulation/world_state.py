from typing import Dict, List
import asyncio
from dataclasses import asdict, is_dataclass
from src.simulation.config_world import WorldEvent


class SharedWorldState:
    """
    The "objective" reality that all agents observe,
    Can be modified by external data or agent actions
    """
    def __init__(self):
        self.current_time = 0  # Simulation tick
        self.events: List[WorldEvent] = []
        self.economic_indicators = {}
        self.social_trends = {}
        self.technological_landscape = {}
        self.regulatory_environment = {}
        
    def inject_event(self, event: WorldEvent):
        """External events or user inputs enter here"""
        self.events.append(event)
        self._propagate_effects(event)
        
    def _propagate_effects(self, event: WorldEvent):
        """Events have cascading effects (simplified)"""
        if event.event_type == "economic":
            self.economic_indicators['volatility'] = event.severity
        elif event.event_type == "technological":
            self.technological_landscape['disruption_level'] = event.severity
            
    def get_observable_state(self, agent_expertise: List[str]) -> Dict:
        """
        Agents see different slices of reality based on expertise
        (Information asymmetry - forces communication)
        """
        visible_events = []
        for e in self.events:
            if any(d in agent_expertise for d in e.affected_domains):
                if is_dataclass(e):
                    visible_events.append(asdict(e))
                elif isinstance(e, dict):
                    visible_events.append(e)
                else:
                    visible_events.append(
                        {
                            "event_type": getattr(e, "event_type", "unknown"),
                            "description": getattr(e, "description", ""),
                            "severity": getattr(e, "severity", 0.0),
                            "affected_domains": getattr(e, "affected_domains", []),
                            "timestamp": getattr(e, "timestamp", ""),
                        }
                    )

        visible = {"time": self.current_time, "events": visible_events, "indicators": {}}

        if "finance" in agent_expertise:
            visible["indicators"]["economic"] = self.economic_indicators
        if "tech" in agent_expertise or "technology" in agent_expertise:
            visible["indicators"]["technology"] = self.technological_landscape

        return visible
    
    
class MessageBus:
    """
    Async pub/sub for agent communication
    Supports: broadcasts, direct messages, group channels
    """
    def __init__(self):
        self.subscribers: Dict[str, asyncio.Queue] = {}
        self.message_history: List[Dict] = []
        
    def register(self, agent_id: str):
        self.subscribers[agent_id] = asyncio.Queue()
        
    async def broadcast(self, sender: str, message: Dict, msg_type: str = "opinion"):
        """Send to all agents"""
        envelope = {
            "sender": sender,
            "type": msg_type,  # opinion, question, evidence, challenge
            "content": message,
            "timestamp": asyncio.get_event_loop().time()
        }
        self.message_history.append(envelope)
        
        for agent_id, queue in self.subscribers.items():
            if agent_id != sender:  # Don't echo to self
                await queue.put(envelope)
                
    async def direct_message(self, sender: str, recipient: str, message: Dict):
        """Private communication (coalition forming)"""
        envelope = {
            "sender": sender,
            "recipient": recipient,
            "type": "private",
            "content": message,
            "timestamp": asyncio.get_event_loop().time()
        }
        if recipient in self.subscribers:
            await self.subscribers[recipient].put(envelope)
            
    async def get_messages(self, agent_id: str, timeout: float = 0.1) -> List[Dict]:
        """Poll for messages"""
        messages = []
        queue = self.subscribers.get(agent_id)
        if not queue:
            return messages
            
        try:
            while True:
                msg = await asyncio.wait_for(queue.get(), timeout=timeout)
                messages.append(msg)
        except asyncio.TimeoutError:
            pass
        return messages