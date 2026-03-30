import os
from typing import AsyncGenerator, Optional
from langchain_openai import ChatOpenAI
from openai import OpenAI
from langchain_community.llms import HuggingFaceHub, Ollama
from src.llm.config_llm import get_llm_config
from langchain.schema import HumanMessage, SystemMessage
from src.llm.config_llm import LLMConfig
import asyncio


class LLMClient:
    """Unified interface for multiple LLM providers"""
    # Available providers
    PROVIDERS = ["openai", "huggingface", "ollama"]
    def __init__(self):
        self._openai = None
        self._huggingface = None
        self._ollama = None
        self._ollama_models_cache = None
        
    def _get_openai(self):
        if not self._openai and LLMConfig.openai_api_key:
            self._openai = ChatOpenAI(
                model=LLMConfig.default_model,
                temperature=0.7,
                api_key=LLMConfig.openai_api_key,
                max_retries=2
            )
        return self._openai
    
    def _get_huggingface(self):
        if not self._huggingface and LLMConfig.huggingface_api_key:
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = LLMConfig.huggingface_api_key
            self._huggingface = HuggingFaceHub(
                repo_id="Qwen/Qwen3.5-9B",
                task="text-generation",
                temperature=0.7,
                max_new_tokens=512
            )
        return self._huggingface

    async def _get_ollama(self, model_name: str = None):
        """Get or initialize Ollama client with specified model"""
        model = model_name or getattr(LLMConfig, 'ollama_model', "qwen3.5:4b")
        # Corrected logic: check if it exists BEFORE checking its attributes
        if self._ollama is None or self._ollama.model != model:
            try:
                self._ollama = Ollama(
                model=model,
                base_url=getattr(LLMConfig, 'ollama_base_url', "http://localhost:11434"),
                temperature=0.7,
                # 'num_predict' is the correct param for LangChain Ollama
                # num_predict=512 
                # REMOVE: api_key, model_name (these caused your crash)
            )
            except Exception as e:
                print(f"Failed to initialize Ollama with model {model}: {e}")
                return None
        return self._ollama

    async def generate(
        self, 
        system_prompt: str, 
        user_prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Generate response with optional provider and model selection
        
        Args:
            system_prompt: System instruction
            user_prompt: User query
            provider: "openai", "huggingface", or "ollama"
            model_name: Specific model name (for Ollama)
            temperature: Override default temperature
        """
        provider = provider or getattr(LLMConfig, 'default_llm_provider', "ollama")
        
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Available: {self.PROVIDERS}")
        
        try:
            if provider == "openai":
                return await self._generate_openai(system_prompt, user_prompt)
            elif provider == "huggingface":
                return await self._generate_huggingface(system_prompt, user_prompt)
            elif provider == "ollama":
                return await self._generate_ollama(system_prompt, user_prompt, model, temperature)
                
        except Exception as e:
            # Intelligent fallback chain
            print(f"Provider {provider} failed: {e}")
            
            # Try fallback providers in order
            fallback_order = ["ollama", "openai", "huggingface"]
            fallback_order.remove(provider)
            
            for fallback_provider in fallback_order:
                try:
                    print(f"Falling back to {fallback_provider}...")
                    if fallback_provider == "openai" and LLMConfig.openai_api_key:
                        return await self._generate_openai(system_prompt, user_prompt)
                    elif fallback_provider == "huggingface" and LLMConfig.huggingface_api_key:
                        return await self._generate_huggingface(system_prompt, user_prompt)
                    elif fallback_provider == "ollama":
                        return await self._generate_ollama(system_prompt, user_prompt, model_name, temperature)
                except Exception as fallback_e:
                    print(f"Fallback to {fallback_provider} also failed: {fallback_e}")
                    continue
            
            raise Exception(f"All providers failed. Last error: {e}")
    
    async def _generate_openai(self, system: str, user: str, temperature: float = None) -> str:
        """Generate using OpenAI"""
        llm = self._get_openai()
        if not llm:
            raise ValueError("OpenAI not configured. Please set OPENAI_API_KEY")
        
        # Override temperature if specified
        if temperature is not None:
            llm.temperature = temperature
        
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user)
        ]
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: llm.invoke(messages)
        )
        return response.content
    
    
    async def _generate_huggingface(self, system: str, user: str) -> str:
        """Generate using HuggingFace Hub"""
        llm = self._get_huggingface()
        if not llm:
            raise ValueError("HuggingFace not configured. Please set HUGGINGFACEHUB_API_TOKEN")
        
        # Format for instruction-tuned models
        full_prompt = f"<s>[INST] {system}\n\n{user} [/INST]"
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: llm.invoke(full_prompt)
        )
        return response.strip()
    
    async def _generate_ollama(self, system: str, user: str, model_name: str = None, temperature: float = None) -> str:
        """Generate using local Ollama model"""
        model = model_name or getattr(LLMConfig, 'ollama_model', "qwen3.5:4b")
        llm = await self._get_ollama(model)
        
        if not llm:
            raise ValueError(f"Ollama not available with model {model}. Please ensure Ollama is running and model is pulled.")
        
        # Override temperature if specified
        if temperature is not None:
            llm.temperature = temperature
        
        # Format prompt for Ollama (similar to Llama chat format)
        full_prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{user}"
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: llm.invoke(full_prompt)
        )
        return response.strip()
    async def stream_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens for real-time viewing
        
        Args:
            system_prompt: System instruction
            user_prompt: User query  
            provider: "openai", "huggingface", or "ollama"
            model_name: Specific model name (for Ollama)
        """
        provider = provider or getattr(LLMConfig, 'default_llm_provider', "ollama")
        
        if provider == "openai":
            async for chunk in self._stream_openai(system_prompt, user_prompt):
                yield chunk
        elif provider == "ollama":
            async for chunk in self._stream_ollama(system_prompt, user_prompt, model_name):
                yield chunk
        elif provider == "huggingface":
            # HuggingFace Hub doesn't support streaming well, fallback to regular generate
            result = await self._generate_huggingface(system_prompt, user_prompt)
            yield result
        else:
            raise ValueError(f"Streaming not supported for provider: {provider}")
        
        
    async def _stream_openai(self, system: str, user: str) -> AsyncGenerator[str, None]:
        """Stream from OpenAI"""
        llm = self._get_openai()
        if not llm:
            result = await self.generate(system, user, provider="openai")
            yield result
            return
        
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user)
        ]
        
        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(
            None,
            lambda: llm.stream(messages)
        )
        
        for chunk in stream:
            if chunk.content:
                yield chunk.content
                
                
    async def _stream_ollama(self, system: str, user: str, model_name: str = None) -> AsyncGenerator[str, None]:
        """Stream from Ollama"""
        model = model_name or getattr(LLMConfig, 'ollama_model', "llama2")
        llm = self._get_ollama(model)
        
        if not llm:
            result = await self.generate(system, user, provider="ollama", model_name=model)
            yield result
            return
        
        full_prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{user}"
        
        loop = asyncio.get_event_loop()
        
        # Ollama supports streaming natively
        try:
            stream = await loop.run_in_executor(
                None,
                lambda: llm.stream(full_prompt)
            )
            
            for chunk in stream:
                if chunk:
                    yield chunk
        except Exception as e:
            print(f"Ollama streaming failed: {e}, falling back to non-streaming")
            result = await self._generate_ollama(system, user, model)
            yield result
                
    def get_available_providers(self) -> dict:
        """Check which providers are available/configured"""
        return {
            "openai": bool(LLMConfig.openai_api_key),
            "huggingface": bool(LLMConfig.huggingface_api_key),
            "ollama": self._check_ollama_available()
        }
        
    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running locally"""
        try:
            import requests
            base_url = getattr(LLMConfig, 'ollama_base_url', "http://localhost:11434")
            response = requests.get(f"{base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False




# Create a global LLM client instance for reuse
global_llm_client = LLMClient()

