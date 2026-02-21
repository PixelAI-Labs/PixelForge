# 🚀 Deployment Guide

## Requirements

- Python 3.10+
- Node.js 18+
- NVIDIA GPU with CUDA 11+ (required)
- 8GB+ VRAM recommended

---

## Backend Setup

python -m venv .venv  
source .venv/bin/activate  
pip install -r requirements.txt  

---

## Frontend Setup

cd frontend  
npm install  
npm run dev  

---

## Environment Variables

MONGODB_URI=mongodb://localhost:27017  
JWT_SECRET=change-me  
NEXT_PUBLIC_API_BASE=http://localhost:8000  

---

## Notes

- An NVIDIA GPU with CUDA is required. The system will not start without one.
- Model loaded once at startup.
