# 🎙️ System Design Podcast

AI-generated conversational podcast episodes that make system design concepts entertaining and easy to follow.

## What is this?

Two AI hosts break down system design topics in 5–10 minute episodes — like having two smart friends explain complex systems over coffee. No slides, no boring lectures. Just clear, conversational explanations with real-world examples.

## Episode Format

- **Length:** 5–10 minutes per episode
- **Style:** Two-host conversational (Host A leads, Host B asks great questions and adds energy)
- **Output:** MP3 audio + one architecture diagram per episode
- **Language:** English

## Topics

### 🏗️ Fundamentals (Season 1)
| # | Topic | Status |
|---|-------|--------|
| 1 | URL Shortener (TinyURL) | 🔜 |
| 2 | Rate Limiter | 🔜 |
| 3 | Consistent Hashing | 🔜 |
| 4 | Key-Value Store | 🔜 |
| 5 | Unique ID Generator | 🔜 |
| 6 | Web Crawler | 🔜 |
| 7 | Notification System | 🔜 |
| 8 | News Feed / Timeline | 🔜 |

### 🌐 Classic Designs (Season 2)
| # | Topic | Status |
|---|-------|--------|
| 9 | Chat System (WhatsApp) | 🔜 |
| 10 | Search Autocomplete | 🔜 |
| 11 | YouTube / Video Streaming | 🔜 |
| 12 | Google Drive / Dropbox | 🔜 |
| 13 | Twitter / Social Feed | 🔜 |
| 14 | Instagram / Photo Sharing | 🔜 |
| 15 | Uber / Ride Sharing | 🔜 |
| 16 | Yelp / Proximity Service | 🔜 |

### ⚡ Advanced Topics (Season 3)
| # | Topic | Status |
|---|-------|--------|
| 17 | Distributed Message Queue (Kafka) | 🔜 |
| 18 | Payment System (Stripe) | 🔜 |
| 19 | Hotel Reservation (Booking.com) | 🔜 |
| 20 | Distributed Cache (Redis) | 🔜 |
| 21 | Stock Exchange / Trading | 🔜 |
| 22 | S3 / Object Storage | 🔜 |
| 23 | Real-Time Gaming Leaderboard | 🔜 |
| 24 | Ad Click Event Aggregation | 🔜 |

### 🧠 Deep Dives (Season 4)
| # | Topic | Status |
|---|-------|--------|
| 25 | CAP Theorem — What It Actually Means | 🔜 |
| 26 | Database Sharding Strategies | 🔜 |
| 27 | CDN Architecture | 🔜 |
| 28 | Load Balancer Deep Dive | 🔜 |
| 29 | API Gateway & Rate Limiting | 🔜 |
| 30 | Event-Driven Architecture | 🔜 |
| 31 | Microservices vs Monolith — The Real Trade-offs | 🔜 |
| 32 | Consensus Algorithms (Raft, Paxos) | 🔜 |

## Tech Stack

- **Script Generation:** LLM (Claude/GPT) — generates conversational two-host dialogue
- **Text-to-Speech:** OpenAI `gpt-4o-mini-tts` — steerable voices with emotion/pacing control
- **Diagrams:** One architecture diagram per episode
- **Hosting:** GitHub repo + (future) RSS feed

## Voices

TBD — currently evaluating OpenAI TTS voices. See `voice-samples/` for auditions.

## Project Structure

```
system-design-podcast/
├── README.md
├── episodes/
│   └── 01-url-shortener/
│       ├── script.md          # Two-host dialogue script
│       ├── episode.mp3        # Final audio
│       └── diagram.png        # Architecture diagram
├── scripts/
│   ├── generate-script.sh     # Generate episode script from topic
│   ├── generate-audio.sh      # Convert script to audio
│   └── config.env.example     # Voice & model config
└── voice-samples/             # TTS voice audition clips
```

## Contributing

This is a personal learning project, but if you find it useful or want to suggest topics, open an issue!

## License

MIT
