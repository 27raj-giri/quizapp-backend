from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from dotenv import load_dotenv
from groq import Groq
import os
import json
import random
import string
import hashlib

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.get("/")
def hello():
    return {"message": "Backend Working!"}

@app.post("/signup")
async def signup(data: dict):
    try:
        existing = supabase.table("profiles").select("*").eq("email", data['email']).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email already registered!")
        
        result = supabase.table("profiles").insert({
            "name": data['name'],
            "email": data['email'],
            "password": hash_password(data['password']),
            "college": data['college'],
            "state": data['state'],
            "university": data['university'],
            "stream": data['stream'],
            "year": data['year'],
        }).execute()
        
        profile = result.data[0]
        profile.pop('password', None)
        return {"status": "success", "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
async def login(data: dict):
    try:
        result = supabase.table("profiles").select("*").eq("email", data['email']).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Email not found!")
        
        profile = result.data[0]
        if profile['password'] != hash_password(data['password']):
            raise HTTPException(status_code=400, detail="Wrong password!")
        
        profile.pop('password', None)
        return {"status": "success", "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/profile/{profile_id}")
async def get_profile(profile_id: str):
    profile = supabase.table("profiles").select("*").eq("id", profile_id).execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Profile not found!")
    
    attempts = supabase.table("attempts").select("*").eq("profile_id", profile_id).order("created_at", desc=True).execute()
    
    p = profile.data[0]
    p.pop('password', None)
    
    return {
        "profile": p,
        "attempts": attempts.data
    }

@app.get("/leaderboard")
async def leaderboard():
    attempts = supabase.table("attempts").select("*").execute()
    
    scores = {}
    for attempt in attempts.data:
        pid = attempt.get('profile_id')
        if not pid:
            continue
        if pid not in scores:
            scores[pid] = {
                "profile_id": pid,
                "name": attempt.get('student_name'),
                "total_score": 0,
                "total_questions": 0,
                "attempts": 0
            }
        scores[pid]['total_score'] += attempt.get('score', 0)
        scores[pid]['total_questions'] += attempt.get('total', 0)
        scores[pid]['attempts'] += 1
    
    leaderboard = []
    for pid, data in scores.items():
        if data['total_questions'] > 0:
            data['percentage'] = round((data['total_score'] / data['total_questions']) * 100)
            leaderboard.append(data)
    
    leaderboard.sort(key=lambda x: x['percentage'], reverse=True)
    return {"leaderboard": leaderboard[:20]}

@app.post("/generate-student-quiz")
async def generate_student_quiz(data: dict):
    prompt = f"""Generate {data['numQuestions']} MCQ questions for {data['subject']} subject, {data['year']} {data['stream']} student of {data['university']}.

Return ONLY a JSON array. No extra text. No markdown. No backticks.
IMPORTANT: The "correct" field must be the FULL option text, not A/B/C/D.
Format:
[{{"question":"q","options":["Full option A","Full option B","Full option C","Full option D"],"correct":"Full option A","explanation":"reason","difficulty":"easy"}}]"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content.strip()

    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    questions = json.loads(text.strip())
    return {"questions": questions}

@app.post("/generate-teacher-quiz")
async def generate_teacher_quiz(data: dict):
    prompt = f"""Generate {data['numQuestions']} MCQ questions on topic: {data['topic']}. Difficulty: {data['difficulty']}.

Return ONLY a JSON array. No extra text. No markdown. No backticks.
IMPORTANT: The "correct" field must be the FULL option text, not A/B/C/D.
Format:
[{{"question":"q","options":["Full option A","Full option B","Full option C","Full option D"],"correct":"Full option A","explanation":"reason","difficulty":"easy"}}]"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content.strip()

    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    questions = json.loads(text.strip())
    code = generate_code()

    supabase.table("quizzes").insert({
        "topic": data['topic'],
        "difficulty": data['difficulty'],
        "questions": questions,
        "share_code": code
    }).execute()

    return {"questions": questions, "share_code": code}

@app.get("/quiz/{code}")
async def get_quiz_by_code(code: str):
    result = supabase.table("quizzes").select("*").eq("share_code", code).execute()
    if result.data:
        return result.data[0]
    return {"error": "Quiz not found"}

@app.post("/save-attempt")
async def save_attempt(data: dict):
    supabase.table("attempts").insert({
        "student_name": data['student_name'],
        "age": data.get('age'),
        "state": data.get('state'),
        "university": data.get('university'),
        "college": data.get('college'),
        "year": data.get('year'),
        "stream": data.get('stream'),
        "subject": data.get('subject'),
        "score": data['score'],
        "total": data['total'],
        "profile_id": data.get('profile_id')
    }).execute()
    return {"status": "saved"}

@app.post("/save-shared-attempt")
async def save_shared_attempt(data: dict):
    supabase.table("shared_attempts").insert({
        "quiz_id": data['quiz_id'],
        "student_name": data['student_name'],
        "score": data['score'],
        "total": data['total'],
        "answers": data['answers']
    }).execute()
    return {"status": "saved"}

@app.get("/teacher-dashboard/{code}")
async def teacher_dashboard(code: str):
    quiz = supabase.table("quizzes").select("*").eq("share_code", code).execute()
    if not quiz.data:
        return {"error": "Quiz not found"}

    quiz_id = quiz.data[0]['id']
    attempts = supabase.table("shared_attempts").select("*").eq("quiz_id", quiz_id).execute()

    return {
        "quiz": quiz.data[0],
        "attempts": attempts.data
    }

@app.post("/generate-adaptive-quiz")
async def generate_adaptive_quiz(data: dict):
    difficulty = data.get('difficulty', 'medium')
    subject = data['subject']
    university = data['university']
    stream = data['stream']
    year = data['year']
    count = data.get('count', 2)
    
    prompt = f"""Generate exactly {count} MCQ questions for {subject} subject.
University: {university}, Stream: {stream}, Year: {year}
Difficulty: {difficulty}

For {difficulty} difficulty:
- easy: Basic definitions, simple concepts, straightforward questions
- medium: Application based, moderate complexity
- hard: Advanced concepts, tricky questions, edge cases, complex analysis

Return ONLY a JSON array. No extra text. No markdown. No backticks.
IMPORTANT: The "correct" field must be the FULL option text, not A/B/C/D.
Format:
[{{"question":"q","options":["Full option A","Full option B","Full option C","Full option D"],"correct":"Full option A","explanation":"reason","difficulty":"{difficulty}"}}]"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content.strip()

    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    questions = json.loads(text.strip())
    return {"questions": questions, "difficulty": difficulty}