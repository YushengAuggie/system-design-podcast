# 🎙️ System Design Podcast

AI-generated conversational podcast episodes that make system design concepts entertaining, interview-ready, and grounded in real-world engineering.

## What is this?

Two AI hosts break down system design topics in 5–10 minute episodes — like having two smart friends explain complex systems over coffee. Each episode covers the theory, how it shows up in interviews, and how real companies actually built it.

## Three Pillars

1. **🎯 Interview-Ready** — Every episode frames the topic as an interview problem: requirements gathering, estimation, high-level design, deep dives, trade-offs, and what to say (and NOT say)
2. **🔥 Modern & Relevant** — Beyond the classics: LLM serving, vector databases, feature flags, serverless, and the systems shaping 2025+
3. **🏭 Real Product Practices** — "How [Company] Actually Does It" segments with real engineering blog references, real trade-offs, real war stories

## Episode Format

Each episode follows a consistent 5-segment structure:

| Segment | Duration | Description |
|---------|----------|-------------|
| 🎯 The Problem | ~2 min | What are we designing? Why is it interesting? Set the hook. |
| 📋 Interview Framework | ~3 min | Requirements, back-of-envelope estimation, high-level architecture |
| 🔬 Deep Dive | ~3 min | The hard parts — scaling challenges, trade-offs, non-obvious decisions |
| 🏭 How They Actually Built It | ~2 min | Real company examples, eng blog insights, production war stories |
| 💡 Interview Tips | ~1 min | What impresses interviewers, common mistakes, key takeaways |

- **Total Length:** 5–10 minutes per episode
- **Style:** Two-host conversational (Host A leads, Host B asks sharp questions and adds energy)
- **Output:** MP3 audio + one architecture diagram per episode
- **Language:** English

## Voice Rotation

Different voice pairs for different seasons/vibes (OpenAI `gpt-4o-mini-tts`):

| Season | Host A | Host B | Vibe |
|--------|--------|--------|------|
| Fundamentals | Ash | Nova | Casual, approachable |
| Classic Designs | Echo | Coral | Energetic, warm |
| Advanced & Modern | Onyx | Shimmer | Deeper, polished |
| Deep Dives | Sage | Fable | Thoughtful, storytelling |

Voice pairs may also rotate episode-by-episode for variety.

## Topics

### Season 1 — 🏗️ Fundamentals
| # | Topic | Real-World Reference | Status |
|---|-------|---------------------|--------|
| 1 | URL Shortener (TinyURL/Bitly) | Bitly's redirect architecture | 🔜 |
| 2 | Rate Limiter | Cloudflare, Stripe API rate limiting | 🔜 |
| 3 | Consistent Hashing | Amazon DynamoDB, Discord | 🔜 |
| 4 | Key-Value Store | Redis, DynamoDB, etcd | 🔜 |
| 5 | Unique ID Generator | Twitter Snowflake, UUID strategies | 🔜 |
| 6 | Web Crawler | Googlebot, Common Crawl | 🔜 |
| 7 | Notification System | Apple/Firebase push, Slack | 🔜 |
| 8 | News Feed / Timeline | Facebook's TAO, ranking algorithms | 🔜 |

### Season 2 — 🌐 Classic Designs
| # | Topic | Real-World Reference | Status |
|---|-------|---------------------|--------|
| 9 | Chat System (WhatsApp/Slack) | WhatsApp's Erlang stack, Slack presence at scale | 🔜 |
| 10 | Search Autocomplete | Google Suggest, Elasticsearch | 🔜 |
| 11 | Video Streaming (YouTube/Netflix) | Netflix adaptive bitrate, YouTube transcoding pipeline | 🔜 |
| 12 | File Storage (Google Drive/Dropbox) | Dropbox's Magic Pocket, block-level sync | 🔜 |
| 13 | Social Feed (Twitter/X) | Twitter's fanout problem, Flock DB | 🔜 |
| 14 | Photo Sharing (Instagram) | Instagram sharding Postgres, Cassandra migration | 🔜 |
| 15 | Ride Sharing (Uber/Lyft) | Uber H3 geospatial indexing, surge pricing | 🔜 |
| 16 | Proximity Service (Yelp/Google Maps) | Quadtree, geohashing, Google S2 | 🔜 |

### Season 3 — ⚡ Advanced & Modern
| # | Topic | Real-World Reference | Status |
|---|-------|---------------------|--------|
| 17 | Distributed Message Queue | Kafka vs Pulsar, LinkedIn's Kafka origin story | 🔜 |
| 18 | Payment System | Stripe's idempotency, double-entry ledger | 🔜 |
| 19 | Hotel Reservation System | Booking.com's availability engine, overbooking | 🔜 |
| 20 | Distributed Cache | Redis Cluster, Memcached at Facebook (mcrouter) | 🔜 |
| 21 | Stock Exchange / Trading | LMAX Disruptor, order matching engines | 🔜 |
| 22 | Object Storage (S3) | AWS S3 internals, erasure coding | 🔜 |
| 23 | Real-Time Gaming Leaderboard | Redis sorted sets, Discord activities | 🔜 |
| 24 | Ad Click Event Aggregation | Google Ads pipeline, lambda vs kappa architecture | 🔜 |
| 25 | LLM Serving Platform | GPU scheduling, KV cache, vLLM, batching strategies | 🔜 |
| 26 | Vector Database | Pinecone, Weaviate, HNSW/IVF indexing | 🔜 |
| 27 | Feature Flag System | LaunchDarkly, Unleash, gradual rollouts | 🔜 |
| 28 | Real-Time ML Inference Pipeline | TikTok recommendation, feature stores | 🔜 |
| 29 | CI/CD Platform | GitHub Actions, Bazel remote caching | 🔜 |
| 30 | Container Orchestrator | Kubernetes internals, Borg heritage | 🔜 |
| 31 | Serverless Platform | AWS Lambda cold starts, Firecracker microVMs | 🔜 |

### Season 4 — 🧠 Deep Dives
| # | Topic | Real-World Reference | Status |
|---|-------|---------------------|--------|
| 32 | CAP Theorem — What It Actually Means | Jepsen tests, real partition stories | 🔜 |
| 33 | Database Sharding Strategies | Vitess (YouTube), Citus, Pinterest shard migration | 🔜 |
| 34 | CDN Architecture | Cloudflare's Anycast, Netflix Open Connect | 🔜 |
| 35 | Load Balancer Deep Dive | Maglev (Google), Envoy, L4 vs L7 | 🔜 |
| 36 | API Gateway & Rate Limiting | Kong, Envoy, Ambassador patterns | 🔜 |
| 37 | Event-Driven Architecture | CQRS, event sourcing, Walmart's Kafka migration | 🔜 |
| 38 | Microservices vs Monolith | Amazon's 2-pizza teams, Shopify's modular monolith | 🔜 |
| 39 | Consensus Algorithms (Raft/Paxos) | etcd, CockroachDB, TiKV | 🔜 |
| 40 | Multi-Region Active-Active | CockroachDB, Spanner, DynamoDB Global Tables | 🔜 |

## Tech Stack

- **Script Generation:** LLM (Claude/GPT) — generates conversational two-host dialogue
- **Text-to-Speech:** OpenAI `gpt-4o-mini-tts` — steerable voices with emotion/pacing control
- **Diagrams:** One architecture diagram per episode (Mermaid/Excalidraw)
- **Hosting:** GitHub repo + (future) RSS feed / podcast platform

## Project Structure

```
system-design-podcast/
├── README.md
├── episodes/
│   └── 01-url-shortener/
│       ├── script.md          # Two-host dialogue script
│       ├── episode.mp3        # Final audio
│       ├── diagram.png        # Architecture diagram
│       └── references.md      # Eng blog links, papers cited
├── scripts/
│   ├── generate-script.sh     # Generate episode script from topic
│   ├── generate-audio.sh      # Convert script to multi-voice audio
│   └── config.env.example     # Voice & model config
├── templates/
│   └── episode-template.md    # Standard episode script template
└── voice-samples/             # TTS voice audition clips
```

## Contributing

This is a personal learning project, but if you find it useful or want to suggest topics, open an issue!

## License

MIT
