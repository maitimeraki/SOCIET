> Draft for counsel review. Not legal advice.

# Subprocessors

{{legal_entity_name}} uses the subprocessors below to operate the service. Each
entry states the purpose and links to the provider's data processing addendum
(DPA). Entries marked **conditional** are used only when the deployment
configures that provider.

| Subprocessor | Purpose | Conditional | DPA |
| --- | --- | --- | --- |
| Anthropic | LLM inference for debates, verdicts, and fallback | No | [DPA link pending counsel review] |
| OpenAI | LLM inference for extraction or fallback | Yes | [DPA link pending counsel review] |
| NVIDIA NIM | LLM inference for graph extraction (default development provider) | No | [DPA link pending counsel review] |
| OpenRouter | LLM inference for extraction | Yes | [DPA link pending counsel review] |
| DeepInfra | LLM inference for extraction | Yes | [DPA link pending counsel review] |
| Amazon S3 or MinIO | Object storage for uploaded files | No (MinIO when self-hosted) | [DPA link pending counsel review] |
| PostgreSQL | Primary application database | No | [DPA link pending counsel review] |
| Redis | Job queue and caching | No | [DPA link pending counsel review] |
| Neo4j | Knowledge graph storage | No | [DPA link pending counsel review] |
| Stripe | Payments, subscriptions, and the billing portal | No | [DPA link pending counsel review] |
| Transactional email provider | Account notices and service messages | Yes | [DPA link pending counsel review] |
| Sentry | Error reporting | Yes | [DPA link pending counsel review] |
| OpenTelemetry collector | Distributed tracing | Yes | [DPA link pending counsel review] |

Contact for subprocessor questions: {{legal_contact_email}}.
