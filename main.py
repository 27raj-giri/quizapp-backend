from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from dotenv import load_dotenv
from groq import Groq
import os
import json
import random
import string

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

@app.get("/")
def hello():
    return {"message": "Backend Working!"}

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
        "age": data['age'],
        "state": data['state'],
        "university": data['university'],
        "college": data['college'],
        "year": data['year'],
        "stream": data['stream'],
        "subject": data['subject'],
        "score": data['score'],
        "total": data['total']
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