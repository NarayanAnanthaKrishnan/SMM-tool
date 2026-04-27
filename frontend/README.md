Frontend (Next.js + TypeScript + Tailwind)

Quick start (in frontend/):

1. Install dependencies
   npm install

2. Run dev server
   npm run dev

Notes
- The frontend is configured to use the existing backend endpoints at the same origin. During local development, run the backend server at the repository root (uvicorn app:app --reload --port 8000) and then run the frontend dev server (npm run dev) which proxies to the same host if you use relative fetch URLs.
- Tailwind dark mode uses the 'class' strategy. You can toggle by adding 'dark' class to document.documentElement.
