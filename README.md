# ScholarHub

A collaborative academic research platform that helps researchers manage projects, discover papers, write documents, and collaborate with AI assistance.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![React](https://img.shields.io/badge/react-18-blue.svg)
![TypeScript](https://img.shields.io/badge/typescript-5-blue.svg)

## Features

### Project Management
- Create and manage research projects with team collaboration
- Invite members with role-based permissions (Owner, Admin, Member)
- Track project progress with activity feeds and notifications

### Paper Discovery
- Search across multiple academic databases (Semantic Scholar, OpenAlex, CORE, CrossRef, PubMed)
- AI-powered paper recommendations based on project context
- Save papers to your project library with citations

### Discussion AI (Beta)
- Multi-model AI assistant powered by OpenRouter
- Support for GPT-5.2, Claude Opus 4.5, Gemini 2.5, DeepSeek V3, and more
- Tool-based orchestration for intelligent context retrieval
- Real-time collaborative discussions with WebSocket support

### Document Writing
- LaTeX editor with live preview and PDF compilation
- Conference templates (IEEE, ACM, Springer, etc.)
- AI-powered writing assistance and document review
- Real-time collaborative editing with Y.js

### Meetings & Transcription
- Record and transcribe research meetings
- AI-generated meeting summaries
- Link discussions to specific meeting segments

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + TypeScript + Vite |
| Backend | FastAPI + Python 3.11 |
| Database | PostgreSQL 15 + pgvector |
| Cache | Redis 7 |
| Real-time | Hocuspocus (Y.js) for collaborative editing |
| Document Server | OnlyOffice |
| AI | OpenRouter |
| Containerization | Docker Compose |

## Project Structure

```
ScholarHub/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/v1/            # API endpoints
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # Business logic
│   │   │   ├── ai_service.py
│   │   │   ├── discussion_ai/
│   │   │   └── paper_discovery/
│   │   └── main.py
│   ├── alembic/               # Database migrations
│   └── Dockerfile
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   └── Dockerfile
├── collab-server/             # Hocuspocus Y.js server
├── nginx/                     # Nginx reverse proxy config
├── docker-compose.yml         # Development compose
└── docker-compose.prod.yml    # Production compose
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Environment Setup

1. Clone the repository:
```bash
git clone https://github.com/hasan1417/ScholarHub.git
cd ScholarHub
```

2. Create environment files:
```bash
# Backend environment
cp backend/.env.example backend/.env

# Frontend environment
cp frontend/.env.example frontend/.env
```

3. Configure your environment variables in the `.env` files:
   - Database credentials
   - OpenAI API key
   - OpenRouter API key (optional, for multi-model support)
   - JWT secrets

### Running with Docker

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Run database migrations
docker compose exec backend alembic upgrade head
```

The application will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Key Features Explained

### Discussion AI

The Discussion AI uses a tool-based orchestration system that allows the AI to:
- Search for papers across multiple databases
- Access project references and context
- Review meeting transcripts
- Generate citations and suggestions

```
User: /find papers about transformer architectures
AI: [Searches databases] → [Returns relevant papers with citations]
```

### Real-time Collaboration

- WebSocket-based messaging for instant updates
- Y.js CRDT for conflict-free document editing
- Live presence indicators

### Paper Discovery Pipeline

```
Query → Multiple APIs → Deduplication → Ranking → Results
         ├── Semantic Scholar
         ├── OpenAlex
         ├── CORE
         ├── CrossRef
         └── PubMed
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [React](https://reactjs.org/) - Frontend library
- [OpenRouter](https://openrouter.ai/) - Multi-model AI API
- [Y.js](https://yjs.dev/) - CRDT for real-time collaboration
- [Hocuspocus](https://hocuspocus.dev/) - Y.js WebSocket backend

## Support

If you encounter any issues or have questions:
- Open an issue on [GitHub Issues](https://github.com/hasan1417/ScholarHub/issues)
- Check existing issues for solutions

---

Built with care for the research community.
