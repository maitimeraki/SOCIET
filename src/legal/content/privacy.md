> Draft for counsel review. Not legal advice.

# Privacy Policy

{{legal_entity_name}} ("we", "us", "our") operates the service described in our
Terms of Service. This Privacy Policy explains what personal data we process,
why, where it is stored, how long we keep it, and the rights you have.

## 1. Controller and contact

The controller of your personal data is {{legal_entity_name}}. Privacy
questions and requests: {{legal_contact_email}}.

## 2. Data we process

| Data | What it includes | Where it is stored |
| --- | --- | --- |
| Account | Email address, password hash (never the plaintext password), role, plan, timestamps, and age confirmation where collected | PostgreSQL |
| Sessions and network data | Session identifiers, IP address, user agent, session timestamps | PostgreSQL |
| Audit records | Action, target, IP address, timestamp, and supporting metadata for security-relevant events | PostgreSQL |
| Uploads | The original files you upload, their names, sizes, MIME types, and content hashes | S3-compatible object storage (S3 or MinIO) |
| Extracted text | Text extracted from your uploads for processing | PostgreSQL |
| Derived graph data | Entities, relationships, and other graph structures derived from your material | Neo4j |
| Job and run records | Your queries, job status, debates, verdicts, confidence scores, run events, and model-usage telemetry (token counts and internal cost estimates) | PostgreSQL |
| Billing data | Stripe customer and subscription identifiers, plan, subscription status, and billing-period dates. Card details are handled by Stripe, not stored by us | PostgreSQL and Stripe |
| Consent records | The legal document version and content hash you accepted, timestamp, IP address, and user agent | PostgreSQL |
| Operational telemetry | Logs, metrics, traces, and error reports used to operate and secure the service | Our infrastructure and, where configured, Sentry and an OpenTelemetry collector |

## 3. Why we process it and our lawful basis

| Activity | Data used | Lawful basis |
| --- | --- | --- |
| Creating and operating your account and the service | Account, uploads, extracted text, derived graph data, job/run records | Performance of a contract |
| Running debates and generating verdicts | Your query, agent prompts derived from the graph, relevant graph context, job/run records, model-usage telemetry | Performance of a contract |
| Authenticating sessions and securing the service | Sessions, IP address, user agent, audit records | Performance of a contract and our legitimate interests in security and abuse prevention |
| Billing, invoicing, and tax | Billing data | Performance of a contract and compliance with legal obligations |
| Recording your acceptance of legal documents | Consent records | Compliance with legal obligations and our legitimate interests in demonstrating compliance |
| Operating, monitoring, and debugging the service | Operational telemetry | Our legitimate interests in running a secure and reliable service |
| Retention and deletion | All of the above | Our legitimate interests and compliance with legal obligations |

Where we rely on legitimate interests, we balance those interests against your
rights and freedoms. You may object as described in section 7.

## 4. Subprocessors and service providers

We use the following subprocessors. Conditional entries are used only when the
operator configures that provider. Each entry links to the provider's data
processing addendum (DPA).

| Subprocessor | Purpose | DPA |
| --- | --- | --- |
| Anthropic | LLM inference for debates, verdicts, and fallback | [DPA link pending counsel review] |
| OpenAI | LLM inference for extraction or fallback, when configured | [DPA link pending counsel review] |
| NVIDIA NIM | LLM inference for graph extraction (default development provider) | [DPA link pending counsel review] |
| OpenRouter | LLM inference for extraction, when configured | [DPA link pending counsel review] |
| DeepInfra | LLM inference for extraction, when configured | [DPA link pending counsel review] |
| Amazon S3 or MinIO | Object storage for uploaded files (MinIO when self-hosted) | [DPA link pending counsel review] |
| PostgreSQL | Primary application database | [DPA link pending counsel review] |
| Redis | Job queue and caching | [DPA link pending counsel review] |
| Neo4j | Knowledge graph storage | [DPA link pending counsel review] |
| Stripe | Payments, subscriptions, and the billing portal | [DPA link pending counsel review] |
| Transactional email provider (when configured) | Account notices and service messages | [DPA link pending counsel review] |
| Sentry (when configured) | Error reporting | [DPA link pending counsel review] |
| OpenTelemetry collector (when configured) | Distributed tracing | [DPA link pending counsel review] |

A current list with the same purposes is published in our Subprocessors
document. We require subprocessors to protect personal data under written
terms.

## 5. International transfers

Our subprocessors may process personal data in the United States and other
countries. Where required, we rely on appropriate safeguards, such as the
standard contractual clauses in the provider's DPA. You can contact us for more
information about the safeguards that apply to a particular transfer.

## 6. Retention

- **Runs and job records** are kept for 365 days.
- **Raw uploaded files** are kept for 30 days. After that, the file object is
  deleted, while its metadata and extracted text are retained as part of the
  account's records until the retention period above or account deletion.
- **Audit records** are kept for 365 days.
- **Account, session, consent, and billing records** are kept while your account
  is active, and for as long as needed to meet legal, tax, and accounting
  obligations after it is deleted.

Retention periods are enforced by scheduled purge jobs where the deployment has
configured them; otherwise they are applied operationally by the operator.

## 7. Your rights

Depending on where you live, you may have the right to:

- access the personal data we hold about you;
- receive a portable copy of it;
- correct inaccurate data;
- delete your account and its data;
- restrict or object to certain processing;
- withdraw consent where processing is based on consent;
- complain to a data protection supervisory authority.

**Export.** You can download an export of your account data from the account
settings in the product. The export is delivered as a time-limited download
link.

**Delete.** You can delete your account from the account settings. Deletion
disables the account immediately, revokes active sessions, and queues a purge
of the account's data. Some records may be retained where the law requires it.

**Other requests.** Email {{legal_contact_email}}. We may need to verify your
identity before acting on a request.

## 8. AI processing

- **Extraction.** The text extracted from your uploads is sent to the
  configured extraction provider to build the knowledge graph. That provider
  may be NVIDIA NIM, OpenRouter, OpenAI, DeepInfra, or a self-hosted
  Ollama/LocalAI deployment, depending on configuration.
- **Debate and verdict.** Your query, the agent prompts derived from your
  graph, and the relevant graph context are sent to the configured LLM
  provider. The configured fallback chain may send a request to a different
  provider than the primary one, for example when the primary provider is
  unavailable.
- **Training.** We do not use your content to train our own models. Where a
  provider's terms permit, we require no-training commitments via a DPA. A
  provider's own terms and DPA govern what it does with a request.
- **Retention by providers.** Provider-side retention is governed by the
  applicable provider DPA.

## 9. Children

The service is not directed to anyone under 18, and we do not knowingly collect
personal data from children. If you believe a child has provided us personal
data, contact us and we will take appropriate steps.

## 10. Changes to this policy

We may update this Privacy Policy from time to time. We will publish the new
version with its version date and, for material changes, ask you to accept it
before you continue using the service. The version and content hash you accepted
are recorded.

## 11. Contact

Privacy questions, rights requests, or complaints: {{legal_contact_email}}.
