import asyncio
from src.graph.models_graph import GlobalInputDocument, SourceType
from src.graph.graph_pipeline import UniversalGraphPipeline


async def main():
    docs = [
    GlobalInputDocument(
        source_type=SourceType.TEXT,
        document_id="tech_spec_001",
        title="System Architecture Documentation",
        text="""System Architecture Overview - Version 3.2

        The authentication service (AuthService v2.1) depends on the User Database (PostgreSQL 14) for credential validation. 
        This service also communicates with the Session Manager (Redis cluster) to maintain user state across multiple requests.

        The Payment Processing System consists of three core components: the Payment Gateway (Stripe integration), 
        the Transaction Validator (internal rule engine), and the Ledger Service (blockchain-based for audit trails). 
        The Payment Gateway depends on the Fraud Detection Service (ML model v4.0) for transaction screening before approval.

        Data Pipeline: The ETL process extracts raw data from the Message Queue (Kafka topics: user_events, transaction_logs), 
        transforms it using the Data Cleaner service, and loads into the Data Warehouse (Snowflake). 
        The Analytics Dashboard queries the Data Warehouse through the Query Optimizer layer.

        Microservices Communication: The Order Service communicates with Inventory Service via REST APIs (timeout: 30s, retry: 3). 
        The Inventory Service publishes stock updates to the Notification Service through a WebSocket connection. 
        All services log to the Centralized Logging Service (ELK stack) for debugging and monitoring.

        Dependencies: The Reporting Engine depends on both the Data Warehouse and the Cache Layer (Redis). 
        The Cache Layer reduces query latency by 85% for frequently accessed reports. The Scheduler Service triggers 
        daily batch jobs that depend on the Task Queue (Celery with RabbitMQ broker).""",
                metadata={
                    "source": "technical_docs",
                    "author": "Engineering Team",
                    "department": "Infrastructure",
                    "agent_id": "system_arch_001"
                }
            ),
            
            GlobalInputDocument(
                source_type=SourceType.TEXT,
                document_id="legal_002",
                title="Corporate Merger Agreement",
                text="""MERGER AGREEMENT - Acme Corp and Beta Industries

        This Agreement is made on January 15, 2025, between Acme Corporation (headquartered in New York, USA) 
        and Beta Industries (headquartered in London, UK).

        ARTICLE I - DEFINITIONS
        "Acquisition" means the purchase of Beta Industries by Acme Corp for $2.5 billion USD.
        "Effective Date" means March 1, 2025, upon regulatory approval.
        "Subsidiaries" includes all entities where either party owns >50% equity.

        ARTICLE II - TERMS OF MERGER
        Acme Corp agrees to acquire all outstanding shares of Beta Industries. Beta Industries will become 
        a wholly-owned subsidiary operating under the name "Acme-Beta Solutions". The Board of Directors will 
        consist of 7 members: 4 appointed by Acme Corp and 3 from Beta Industries' existing leadership.

        ARTICLE III - INTELLECTUAL PROPERTY
        All patents (USPTO #123456, #789012), trademarks (EUIPO #345678), and copyrights owned by Beta Industries 
        shall transfer to Acme Corp. Beta Industries grants Acme Corp an exclusive license to use its proprietary 
        AI algorithms for fraud detection in North American markets.

        ARTICLE IV - EMPLOYMENT AGREEMENTS
        Key executives from Beta Industries (CEO Jane Smith, CTO Michael Chen) will join Acme Corp as 
        Senior Vice Presidents with 5-year contracts. All other employees (approximately 2,500 people) 
        will be offered equivalent positions at Acme Corp.

        ARTICLE V - REGULATORY APPROVALS
        This merger requires approval from the Federal Trade Commission (FTC), European Commission (EC), 
        and Competition Commission of India (CCI). The parties agree to file all necessary documentation 
        within 90 days of signing.

        SIGNATORIES:
        - John Doe, CEO of Acme Corporation
        - Jane Smith, CEO of Beta Industries
        - Witnessed by: Sarah Johnson, Legal Counsel""",
                metadata={
                    "source": "legal_documents",
                    "document_type": "contract",
                    "jurisdiction": "international",
                    "agent_id": "legal_doc_002"
                }
            ),
            
            GlobalInputDocument(
                source_type=SourceType.TEXT,
                document_id="news_003",
                title="Healthcare AI Partnership Announcement",
                text="""HealthTech Innovators Announce Strategic Partnership

        BOSTON, MA - March 10, 2025 - MedAI Solutions (NASDAQ: MDAI) announced today a strategic partnership 
        with University Medical Center (UMC) to deploy AI-powered diagnostic tools across their 12 hospital network.

        Under the 5-year agreement valued at $45 million, MedAI Solutions will provide its flagship product 
        'DiagnosisGPT' to all UMC facilities. The AI system analyzes medical imaging (X-rays, CT scans, MRIs) 
        to detect early signs of pneumonia, tumors, and fractures with 94.7% accuracy.

        "This partnership represents a major milestone in our mission to democratize healthcare AI," said 
        Dr. Emily Zhang, Chief Technology Officer at MedAI Solutions. "UMC's clinical expertise combined 
        with our technology will save thousands of lives."

        University Medical Center will contribute anonymized patient data (over 2 million imaging studies) 
        to train MedAI's next-generation models. In return, MedAI Solutions will provide free software licenses 
        to UMC's research department and co-author any resulting scientific publications.

        The implementation will be overseen by a joint steering committee comprising:
        - Dr. Robert Chen (UMC, Chief Medical Information Officer)
        - Dr. Sarah Williams (MedAI, VP of Clinical Affairs)
        - Professor David Kumar (Independent ethics advisor)

        Regulatory compliance will be managed by MedAI's legal team (led by Jennifer Lopez) and UMC's 
        Office of Research Compliance (directed by Dr. Michael Brown). The system is expected to go live 
        in Q3 2025 after FDA approval (submission #FDA-2025-0892).""",
                metadata={
                    "source": "news_release",
                    "industry": "healthcare",
                    "publication_date": "2025-03-10",
                    "agent_id": "news_003"
                }
            )
        ]   
    pipeline = UniversalGraphPipeline()
    result = await pipeline.run(dataset_id="batch_001", documents=docs)
    print(result)


def run_main():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(main())
        return None

    return loop.create_task(main())


if __name__ == "__main__":
    run_main()
